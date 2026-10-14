import { _t } from "@web/core/l10n/translation";

export const MODES = [
    { fkey: "F1", label: _t("Sales"),    resModel: "sale.order",      domain: [["state", "not in", ["cancel"]]] },
    { fkey: "F2", label: _t("Purchases"), resModel: "purchase.order",  domain: [["state", "not in", ["cancel"]]] },
    { fkey: "F3", label: _t("Invoices"), resModel: "account.move",    domain: [["move_type", "in", ["out_invoice", "in_invoice", "out_refund"]]] },
    { fkey: "F4", label: _t("Payments"), resModel: "account.payment", domain: [["state", "!=", "cancel"]] },
];

export function addLineAndFocusProduct() {
    const addBtn = document.querySelector(
        ".o_field_one2many .o_field_x2many_list_row_add a"
    );
    if (!addBtn) return;
    addBtn.click();

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            const rows = document.querySelectorAll(".o_field_one2many .o_data_row");
            if (!rows.length) return;
            const lastRow = rows[rows.length - 1];
            // Odoo 20 groups the product with its description in one column
            lastRow.querySelector('td[name="product_id"], td[name="product_and_description"]')?.click();
        });
    });
}

export function modeAction(mode) {
    return {
        type: "ir.actions.act_window",
        name: mode.label,
        res_model: mode.resModel,
        views: [[false, "list"], [false, "form"]],
        domain: mode.domain,
        target: "current",
    };
}
