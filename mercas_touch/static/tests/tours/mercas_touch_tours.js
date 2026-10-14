import { registry } from "@web/core/registry";

// Data made by the Python test: a customer, a supplier, a pear tracked by lots with a lot in
// stock (TOUR-LOT) and a box product

registry.category("web_tour.tours").add("mercas_touch_sale_tour", {
    steps: () => [
        {
            content: "Open the sale",
            trigger: ".o_mercas_touch_mode_sale",
            run: "click",
        },
        {
            content: "Search the customer",
            trigger: ".o_mercas_touch_partner_search",
            run: "edit Tour Customer",
        },
        {
            trigger: ".o_mercas_touch_partner:contains(Tour Customer)",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_partner_name:contains(Tour Customer)",
        },
        {
            content: "Choose the product",
            trigger: ".o_mercas_touch_product:contains(Tour Pear)",
            run: "click",
        },
        {
            content: "Choose its lot",
            trigger: ".o_mercas_touch_lot:contains(TOUR-LOT)",
            run: "click",
        },
        {
            content: "Type the quantity with the keypad",
            trigger: ".o_mercas_touch_numpad_key:text(1)",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_numpad_key:text(2)",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_qty:value(12)",
        },
        {
            content: "Change the price",
            trigger: ".o_mercas_touch_price",
            run: "edit 1.5",
        },
        {
            content: "Two boxes",
            trigger: ".o_mercas_touch_box_qty button[title='One box more']",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_box_qty button[title='One box more']",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_box_qty_input:value(2)",
        },
        {
            trigger: ".o_mercas_touch_add",
            run: "click",
        },
        {
            content: "The line is in the ticket",
            trigger: ".o_mercas_touch_line:contains(TOUR-LOT):contains(12)",
        },
        {
            trigger: ".o_mercas_touch_total_boxes:text(2)",
        },
        {
            content: "Sell and deliver",
            trigger: ".o_mercas_touch_sell:enabled",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_done:contains(delivered)",
        },
        {
            content: "The customer now holds the boxes",
            trigger: ".o_mercas_touch_partner_badges:contains(Tour Box)",
        },
    ],
});

registry.category("web_tour.tours").add("mercas_touch_purchase_tour", {
    steps: () => [
        {
            content: "Open the purchase with its function key",
            trigger: ".o_mercas_touch_home",
            run: "press F2",
        },
        {
            trigger: ".o_mercas_touch_partner_search",
            run: "edit Tour Supplier",
        },
        {
            trigger: ".o_mercas_touch_partner:contains(Tour Supplier)",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_product:contains(Tour Pear)",
            run: "click",
        },
        {
            content: "No lots to choose: a new one is made",
            trigger: ".o_mercas_touch_qty",
            run: "edit 80",
        },
        {
            trigger: ".o_mercas_touch_price",
            run: "edit 0.9",
        },
        {
            trigger: ".o_mercas_touch_lot_name",
            run: "edit TOUR-NEW",
        },
        {
            content: "One box, to print its label",
            trigger: ".o_mercas_touch_box_qty button[title='One box more']",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_add",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_purchase:enabled",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_done_lots:contains(TOUR-NEW)",
        },
        {
            content: "Print the box labels of the new lot",
            trigger: ".o_mercas_touch_print_labels",
            run: "click",
        },
        {
            trigger: ".modal .o_data_row:contains(TOUR-NEW)",
        },
        {
            trigger: ".modal button[name=action_print]",
            run: "click",
        },
        {
            content: "The wizard closes once the labels are downloaded",
            trigger: "body:not(:has(.modal)) .o_mercas_touch_done",
        },
        {
            content: "Go to the lots",
            trigger: ".o_mercas_touch_tabs button[title='Lots']",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_lot_search",
            run: "edit TOUR-NEW",
        },
        {
            trigger: ".o_mercas_touch_lot_card:contains(TOUR-NEW) .o_mercas_touch_scrap_lot",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_scrap_qty",
            run: "edit 5",
        },
        {
            trigger: ".o_mercas_touch_confirm_scrap",
            run: "click",
        },
        {
            content: "The scrap is in the lot",
            trigger: ".o_mercas_touch_lot_card:contains(TOUR-NEW):contains(Scrapped 5)",
        },
    ],
});

registry.category("web_tour.tours").add("mercas_touch_payment_tour", {
    steps: () => [
        {
            trigger: ".o_mercas_touch_mode_payment",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_partner_search",
            run: "edit Tour Customer",
        },
        {
            trigger: ".o_mercas_touch_partner:contains(Tour Customer)",
            run: "click",
        },
        {
            content: "Choose the invoice: its amount is proposed",
            trigger: ".o_mercas_touch_invoice input",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_amount:value(100)",
        },
        {
            content: "Collect only a part",
            trigger: ".o_mercas_touch_numpad_clear",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_numpad_key:text(6)",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_numpad_key:text(0)",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_register_payment",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_done:contains(registered)",
        },
    ],
});
