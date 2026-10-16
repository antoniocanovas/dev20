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
            content: "A new quotation: the customer is asked",
            trigger: ".o_mercas_touch_new_draft",
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
        {
            content: "Invoice the sale",
            trigger: ".o_mercas_touch_invoice_sale",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_done_invoice:contains(to collect)",
        },
        {
            content: "And collect it: the payment opens with the invoice and its amount",
            trigger: ".o_mercas_touch_collect_invoice",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_invoice input:checked",
        },
        {
            trigger: ".o_mercas_touch_amount:value(18)",
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

registry.category("web_tour.tours").add("mercas_touch_purchase_tour", {
    steps: () => [
        {
            content: "Open the purchase with its function key",
            trigger: ".o_mercas_touch_home",
            run: "press F2",
        },
        {
            content: "A new purchase: the supplier is asked",
            trigger: ".o_mercas_touch_new_draft",
            run: "click",
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

const addPearLine = (qty) => [
    {
        trigger: ".o_mercas_touch_product:contains(Tour Pear)",
        run: "click",
    },
    {
        trigger: ".o_mercas_touch_lot:contains(TOUR-LOT)",
        run: "click",
    },
    {
        trigger: ".o_mercas_touch_qty",
        run: `edit ${qty}`,
    },
    {
        trigger: ".o_mercas_touch_add",
        run: "click",
    },
];

registry.category("web_tour.tours").add("mercas_touch_price_tour", {
    steps: () => [
        {
            trigger: ".o_mercas_touch_mode_sale",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_new_draft",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_partner:contains(Tour Customer)",
            run: "click",
        },
        ...addPearLine(10),
        ...addPearLine(5),
        {
            content: "Change the price of the second line from the ticket",
            trigger: ".o_mercas_touch_line:eq(1) .o_mercas_touch_line_price",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_price_editor:contains(Line 2 of 2)",
        },
        {
            content: "The first key replaces the price",
            trigger: ".o_mercas_touch_numpad_key:text(3)",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_price_edit_input:value(3)",
        },
        {
            trigger: ".o_mercas_touch_price_edit_subtotal:contains(15.00)",
        },
        {
            content: "Previous line",
            trigger: ".o_mercas_touch_price_prev",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_price_editor:contains(Line 1 of 2)",
        },
        {
            content: "With the keyboard: Enter writes it and goes to the next line",
            trigger: ".o_mercas_touch_price_edit_input",
            run: "edit 2.5 && press Enter",
        },
        {
            trigger: ".o_mercas_touch_price_editor:contains(Line 2 of 2)",
        },
        {
            trigger: ".o_mercas_touch_price_edit_input:value(3)",
        },
        {
            content: "Past the last line, the editor closes",
            trigger: ".o_mercas_touch_price_next",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_body:not(:has(.o_mercas_touch_price_editor))",
        },
        {
            trigger: ".o_mercas_touch_total:contains(40.00)",
        },
        {
            trigger: ".o_mercas_touch_sell:enabled",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_done:contains(delivered)",
        },
    ],
});

registry.category("web_tour.tours").add("mercas_touch_quotation_tour", {
    steps: () => [
        {
            content: "The sale starts from the quotations in draft",
            trigger: ".o_mercas_touch_mode_sale",
            run: "click",
        },
        {
            content: "Resume the quotation made in the backend",
            trigger: ".o_mercas_touch_draft:contains(Tour Customer):contains(1 line)",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_line:contains(TOUR-LOT):contains(7)",
        },
        {
            trigger: ".o_mercas_touch_order_name",
        },
        ...addPearLine(4),
        {
            content: "Each change is saved in the quotation",
            trigger: ".o_mercas_touch_save_state:contains(Saved in)",
        },
        {
            content: "Leave it, to go on later",
            trigger: ".o_mercas_touch_back",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_draft:contains(Tour Customer):contains(2 lines)",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_line:eq(1):contains(4)",
        },
        {
            trigger: ".o_mercas_touch_sell:enabled",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_done:contains(delivered)",
        },
        {
            content: "A new sale starts again from the quotations",
            trigger: ".o_mercas_touch_new",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_new_draft",
        },
        {
            trigger: ".o_mercas_touch_body:not(:has(.o_mercas_touch_draft))",
        },
    ],
});

const addPurchaseLine = (qty, lotName) => [
    {
        trigger: ".o_mercas_touch_product:contains(Tour Pear)",
        run: "click",
    },
    {
        trigger: ".o_mercas_touch_qty",
        run: `edit ${qty}`,
    },
    {
        trigger: ".o_mercas_touch_lot_name",
        run: `edit ${lotName}`,
    },
    {
        trigger: ".o_mercas_touch_add",
        run: "click",
    },
    {
        trigger: `.o_mercas_touch_line:contains(${lotName})`,
    },
    {
        trigger: ".o_mercas_touch_save_state:contains(Saved in)",
    },
];

registry.category("web_tour.tours").add("mercas_touch_purchase_drafts_tour", {
    steps: () => [
        {
            content: "The purchase starts from the purchases in draft",
            trigger: ".o_mercas_touch_mode_purchase",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_new_draft",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_partner:contains(Tour Supplier)",
            run: "click",
        },
        ...addPurchaseLine(30, "DRAFT-A"),
        {
            content: "Go to another purchase without closing this one",
            trigger: ".o_mercas_touch_back",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_draft:contains(Backend Supplier)",
            run: "click",
        },
        ...addPurchaseLine(12, "DRAFT-B"),
        {
            trigger: ".o_mercas_touch_back",
            run: "click",
        },
        {
            content: "The first purchase is there as it was left",
            trigger: ".o_mercas_touch_draft:contains(Tour Supplier):contains(1 line)",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_line:contains(DRAFT-A):contains(30)",
        },
        {
            trigger: ".o_mercas_touch_purchase:enabled",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_done_lots:contains(DRAFT-A)",
        },
    ],
});

registry.category("web_tour.tours").add("mercas_touch_to_invoice_tour", {
    steps: () => [
        {
            trigger: ".o_mercas_touch_mode_sale",
            run: "click",
        },
        {
            content: "The sales still to invoice",
            trigger: ".o_mercas_touch_draft_filter_to_invoice",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_draft:contains(Tour Customer)",
            run: "click",
        },
        {
            content: "Its summary, with its lines",
            trigger: ".o_mercas_touch_summary_lines:contains(TOUR-LOT)",
        },
        {
            trigger: ".o_mercas_touch_invoice_sale",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_done_invoice:contains(to collect)",
        },
        {
            trigger: ".o_mercas_touch_back_to_list",
            run: "click",
        },
        {
            content: "Invoiced, it isn't to invoice anymore",
            trigger: ".o_mercas_touch_draft_filters .btn-primary:contains(To invoice)",
        },
        {
            trigger: ".o_mercas_touch_body:not(:has(.o_mercas_touch_draft))",
        },
        {
            content: "All the sales",
            trigger: ".o_mercas_touch_draft_filter_all",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_draft:contains(Tour Customer) .text-bg-success",
        },
        {
            content: "The purchases to invoice",
            trigger: ".o_mercas_touch_tabs button[title='Purchase']",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_draft_filter_to_invoice",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_draft:contains(Tour Supplier)",
            run: "click",
        },
        {
            trigger: ".o_mercas_touch_invoice_purchase",
            run: "click",
        },
        {
            content: "The bill opens in a dialog to review it",
            trigger: ".modal .o_form_view",
        },
    ],
});
