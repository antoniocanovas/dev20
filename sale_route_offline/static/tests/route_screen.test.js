import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { expect, queryAllTexts, runAllTimers, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { OfflinePlugin } from "@web/core/offline/offline_plugin";
import {
    contains,
    getService,
    mockOffline,
    mountWebClient,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";

defineMailModels();

const ROUTE_DATA = {
    generated_at: "2026-10-13 07:00:00",
    currency_id: 1,
    has_discount: true,
    customers: [
        {
            id: 7,
            name: "Bar Pepe",
            street: "Calle Mayor 1",
            city: "30001 Murcia",
            phone: "",
            overdue: 120,
            not_due: 30,
            credit_limit: 100,
            price_key: 1,
            tax_key: 0,
            invoices: [],
            orders: [],
            usual_products: [
                { product_id: 3, qty: 2, discount: 0, count: 4, price: 10, tax_percent: 21 },
            ],
        },
        {
            id: 8,
            name: "Café Lola",
            street: "",
            city: "30002 Murcia",
            phone: "",
            overdue: 0,
            not_due: 0,
            credit_limit: false,
            price_key: 1,
            tax_key: 0,
            invoices: [],
            orders: [],
            usual_products: [],
        },
    ],
    products: [
        { id: 3, name: "Coffee 1kg", default_code: "C1", uom_name: "Units", categ_id: 1, image_unique: "x" },
        { id: 4, name: "Sugar 1kg", default_code: "S1", uom_name: "Units", categ_id: 2, image_unique: "x" },
        { id: 5, name: "Tea", default_code: "", uom_name: "Units", categ_id: 1, image_unique: "x" },
    ],
    categories: [
        { id: 1, name: "Drinks" },
        { id: 2, name: "Groceries" },
    ],
    prices: { 1: { 3: 10, 4: 2, 5: 5 } },
    taxes: { 0: { 3: 21, 4: 10, 5: 21 } },
    journals: [{ id: 5, name: "Cash", type: "cash" }],
};

/**
 * @param {Object} [params]
 * @param {Function} [params.routeData] returns the route data, given the server state
 */
function mockRouteServer({ routeData = () => ROUTE_DATA } = {}) {
    // What the server received: {uuid: revision}, and how many times the route data was read
    const server = { saved: {}, confirmed: false, routeDataCalls: 0 };
    onRpc("res.partner", "get_route_data", () => {
        server.routeDataCalls++;
        return routeData(server);
    });
    onRpc("res.partner", "get_route_sync_status", ({ args }) =>
        Object.fromEntries(args[0].filter((uuid) => uuid in server.saved).map((uuid) => [uuid, server.saved[uuid]]))
    );
    onRpc("sale.order", "save_from_tablet", ({ args }) => {
        const [vals] = args;
        expect.step(["save_from_tablet", vals.revision, vals.confirm, vals.lines]);
        if (vals.order_id) {
            expect(vals.order_id).toBe(41);
        }
        server.saved[vals.offline_uuid] = vals.revision;
        server.confirmed ||= vals.confirm;
        return { id: 1, name: "S00001", state: vals.confirm ? "sale" : "draft" };
    });
    return server;
}

async function openRouteScreen() {
    await mountWebClient();
    await getService("action").doAction("sale_route_offline.route");
    await animationFrame();
}

async function openCustomer() {
    await contains(".o_sale_route_customers").click();
    await contains(".o_sale_route_customer:first").click();
}

/** New order of the usual products, up to the review screen. */
async function reviewNewOrder() {
    await contains(".o_sale_route_new_order").click();
    await contains(".o_sale_route_usual_qty").click();
    expect(".o_sale_route_qty_input").toHaveValue("2");
    // 2 x 10 = 20, discount 0, 21% tax
    expect(".o_sale_route_order_total").toHaveText(/^\$\s24\.20$/);
    await contains(".o_sale_route_review").click();
    expect(".o_sale_route_review_lines tbody tr").toHaveCount(1);
    expect(".o_sale_route_review_overdue").toHaveCount(1, { message: "the customer has overdue debt" });
}

const USUAL_LINES = [{ product_id: 3, qty: 2, discount: 0 }];

test("home: install the app on this device", async () => {
    mockRouteServer();
    await mountWebClient();
    patchWithCleanup(getService("pwa"), {
        isAvailable: true,
        show: () => expect.step("install"),
    });
    await getService("action").doAction("sale_route_offline.route");
    await animationFrame();
    expect(".o_sale_route_odoo_home").toHaveCount(1);
    await contains(".o_sale_route_pwa_install").click();
    expect.verifySteps(["install"]);
});

test("customers: search and debt", async () => {
    mockRouteServer();
    await openRouteScreen();
    expect(".o_sale_route_stale").toHaveCount(1);
    await contains(".o_sale_route_customers").click();
    expect(queryAllTexts(".o_sale_route_customer .fs-5")).toEqual(["Bar Pepe", "Café Lola"]);
    expect(".o_sale_route_overdue").toHaveCount(1);

    await contains(".o_sale_route_search_input").edit("cafe", { confirm: false });
    expect(queryAllTexts(".o_sale_route_customer .fs-5")).toEqual(["Café Lola"]);
});

test("online: save a quotation, review it and confirm it", async () => {
    mockRouteServer();
    await openRouteScreen();
    await openCustomer();
    await reviewNewOrder();
    await contains(".o_sale_route_save_quotation").click();
    expect.verifySteps([["save_from_tablet", 1, false, USUAL_LINES]]);
    expect(getService(OfflinePlugin).hasScheduledCalls).toBe(false);
    expect(".o_sale_route_today_order").toHaveCount(1);
    expect(".o_sale_route_today_order").toHaveText(/Quotation/);
    expect(".o_sale_route_waiting").toHaveCount(0);

    // Later on: review today's order and confirm it
    await contains(".o_sale_route_open_order").click();
    await contains(".o_sale_route_confirm_order").click();
    expect.verifySteps([["save_from_tablet", 2, true, USUAL_LINES]]);
    expect(".o_sale_route_today_order").toHaveCount(1);
    expect(".o_sale_route_today_order").toHaveText(/Confirmed/);

    // A confirmed order can only be seen
    await contains(".o_sale_route_open_order").click();
    expect(".o_sale_route_confirmed").toHaveCount(1);
    expect(".o_sale_route_confirm_order").toHaveCount(0);
});

test("recent orders: invoice status, dates, and change a quotation", async () => {
    mockRouteServer();
    patchWithCleanup(ROUTE_DATA.customers[0], {
        orders: [
            {
                id: 41,
                name: "S00041",
                date: "2026-10-10 09:00:00",
                state: "Quotation",
                state_code: "draft",
                invoice_status: "Nothing to invoice",
                invoice_status_code: "no",
                delivery_date: "2026-10-15 10:00:00",
                commitment_date: "2026-10-16 10:00:00",
                amount_total: 60.5,
                currency_id: 1,
                offline_uuid: false,
                offline_revision: 0,
                lines: [
                    { line_id: 90, product_id: 4, name: "Sugar 1kg", qty: 5, uom_name: "Units", price_unit: 2, discount: 0, tax_percent: 10, subtotal: 10 },
                ],
            },
            {
                id: 40,
                name: "S00040",
                date: "2026-10-01 09:00:00",
                state: "Sales Order",
                state_code: "sale",
                invoice_status: "Fully Invoiced",
                invoice_status_code: "invoiced",
                delivery_date: "2026-10-02 10:00:00",
                commitment_date: false,
                amount_total: 24.2,
                currency_id: 1,
                offline_uuid: false,
                offline_revision: 0,
                lines: [],
            },
        ],
    });
    await openRouteScreen();
    await openCustomer();
    expect(".o_sale_route_recent_order").toHaveCount(2);
    expect(queryAllTexts(".o_sale_route_invoice_status")).toEqual(["Nothing to invoice", "Fully Invoiced"]);
    expect(".o_sale_route_recent_order:first .o_sale_route_order_dates div").toHaveCount(2);
    expect(".o_sale_route_recent_order:last .o_sale_route_order_dates div").toHaveCount(1);
    expect(".o_sale_route_edit_quotation").toHaveCount(1, { message: "only quotations can be changed" });

    await contains(".o_sale_route_edit_quotation").click();
    // Its line, then the usual products of the customer
    expect(queryAllTexts(".o_sale_route_line .fw-bold.text-truncate")).toEqual(["Sugar 1kg", "Coffee 1kg"]);
    await contains(".o_sale_route_line:first button[title='More']").click();
    await contains(".o_sale_route_review").click();
    await contains(".o_sale_route_confirm_order").click();
    expect.verifySteps([["save_from_tablet", 1, true, [{ product_id: 4, qty: 6, discount: 0, line_id: 90 }]]]);
    expect(".o_sale_route_today_order").toHaveText(/S00041/);
});

test("online: the recent orders are read again once the order is confirmed", async () => {
    const quotation = {
        id: 41,
        name: "S00041",
        date: "2026-10-10 09:00:00",
        state: "Quotation",
        state_code: "draft",
        invoice_status: "Nothing to invoice",
        invoice_status_code: "no",
        delivery_date: false,
        commitment_date: false,
        amount_total: 11,
        currency_id: 1,
        offline_uuid: false,
        offline_revision: 0,
        lines: [
            { line_id: 90, product_id: 4, name: "Sugar 1kg", qty: 5, uom_name: "Units", price_unit: 2, discount: 0, tax_percent: 10, subtotal: 10 },
        ],
    };
    const server = mockRouteServer({
        routeData: ({ confirmed }) => {
            const order = confirmed
                ? { ...quotation, state: "Sales Order", state_code: "sale", invoice_status: "To Invoice", invoice_status_code: "to invoice" }
                : quotation;
            return { ...ROUTE_DATA, customers: [{ ...ROUTE_DATA.customers[0], orders: [order] }] };
        },
    });
    await openRouteScreen();
    await openCustomer();
    expect(".o_sale_route_recent_order .badge:first").toHaveText("Quotation");
    const calls = server.routeDataCalls;

    await contains(".o_sale_route_edit_quotation").click();
    await contains(".o_sale_route_review").click();
    await contains(".o_sale_route_confirm_order").click();
    expect.verifySteps([["save_from_tablet", 1, true, [{ product_id: 4, qty: 5, discount: 0, line_id: 90 }]]]);
    await animationFrame();
    expect(server.routeDataCalls).toBe(calls + 1);
    expect(".o_sale_route_recent_order .badge:first").toHaveText("Sales Order");
    expect(".o_sale_route_invoice_status").toHaveText("To Invoice");
    expect(".o_sale_route_edit_quotation").toHaveCount(0);
});

test.tags("mobile");
test("catalog: choose the category in a list on small screens", async () => {
    mockRouteServer();
    await openRouteScreen();
    await openCustomer();
    await contains(".o_sale_route_new_order").click();
    await contains(".o_sale_route_open_catalog").click();
    expect(".o_sale_route_catalog_panel").not.toBeVisible();
    await contains(".o_sale_route_category_select").select("2");
    expect(queryAllTexts(".o_sale_route_catalog_name")).toEqual(["Sugar 1kg"]);
    await contains(".o_sale_route_catalog_add").click();
    await contains(".o_sale_route_catalog_done").click();
    expect(queryAllTexts(".o_sale_route_line .fw-bold.text-truncate")).toEqual(["Coffee 1kg", "Sugar 1kg"]);
});

test.tags("desktop");
test("catalog: add products by category", async () => {
    mockRouteServer();
    await openRouteScreen();
    await openCustomer();
    await contains(".o_sale_route_new_order").click();
    await contains(".o_sale_route_open_catalog").click();
    expect(".o_sale_route_catalog_card").toHaveCount(3);

    await contains(".o_sale_route_category:contains(Groceries)").click();
    expect(queryAllTexts(".o_sale_route_catalog_name")).toEqual(["Sugar 1kg"]);
    await contains(".o_sale_route_catalog_card").click();
    await contains(".o_sale_route_catalog_card button[title='More']").click();
    expect(".o_sale_route_catalog_qty_input").toHaveValue("2");

    await contains(".o_sale_route_category:contains(Drinks)").click();
    await contains(".o_sale_route_product_search_input").edit("tea", { confirm: false });
    expect(queryAllTexts(".o_sale_route_catalog_name")).toEqual(["Tea"]);
    await contains(".o_sale_route_catalog_add").click();
    await contains(".o_sale_route_catalog_card button[title='Less']").click();
    expect(".o_sale_route_catalog_add").toHaveCount(1, { message: "back to 0: out of the order" });

    await contains(".o_sale_route_catalog_done").click();
    expect(queryAllTexts(".o_sale_route_line .fw-bold.text-truncate")).toEqual(["Coffee 1kg", "Sugar 1kg"]);
    // 2 x 2 = 4 + 10% tax
    expect(".o_sale_route_order_total").toHaveText(/^\$\s4\.40$/);
});

test("offline: the order is queued, and its confirmation replaces it in the queue", async () => {
    const setOffline = mockOffline();
    const server = mockRouteServer();
    await openRouteScreen();
    await runAllTimers(); // let the offline plugin do its first sync, with nothing to sync

    await setOffline(true);
    expect(".o_sale_route_offline_badge").toHaveCount(1);
    expect(".o_sale_route_prepare").toBeEnabled({ message: "buttons are available offline" });
    await openCustomer();
    await reviewNewOrder();
    await contains(".o_sale_route_save_quotation").click();

    // Nothing reached the server: the order waits in the queue of the offline plugin
    expect.verifySteps([]);
    const offline = getService(OfflinePlugin);
    expect(offline.hasScheduledCalls).toBe(true);
    expect(".o_sale_route_today_order .o_sale_route_waiting").toHaveCount(1);

    await contains(".o_sale_route_open_order").click();
    await contains(".o_sale_route_confirm_order").click();
    expect.verifySteps([]);

    // The sync menu lists one call for the order, without breaking on its unknown status
    await contains(".o_menu_systray .o_offline_systray").click();
    expect(".o_offline_systray_content .o-dropdown-item").toHaveCount(1);
    expect(".o_offline_systray_content .o-dropdown-item").toHaveText(/Order of Bar Pepe/);

    const calls = server.routeDataCalls;
    await setOffline(false);
    await runAllTimers();
    await expect.waitForSteps([["save_from_tablet", 2, true, USUAL_LINES]]);
    expect(offline.hasScheduledCalls).toBe(false);

    // Once the queue is sent, the screen checks it and reads the route data again
    await runAllTimers();
    await animationFrame();
    expect(".o_sale_route_today_order .o_sale_route_waiting").toHaveCount(0);
    expect(server.routeDataCalls).toBe(calls + 1);
});
