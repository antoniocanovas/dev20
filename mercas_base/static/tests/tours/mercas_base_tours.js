import { registry } from "@web/core/registry";

// Sale order made by the Python test, with a line of a lot of SMOKE-LOT in stock
registry.category("web_tour.tours").add("mercas_base_sale_order_tour", {
    steps: () => [
        {
            content: "Date of the last change of the quantity",
            trigger: ".o_field_mercas_product_qty_datetime_icon i",
            run: "click",
        },
        {
            trigger: ".o_popover:contains(Cantidad actualizada el)",
        },
        {
            content: "Stock of the line, with its lots",
            trigger: ".o_field_widget .oi[data-icon=area_chart], .o_widget_qty_at_date_widget .oi",
            run: "click",
        },
        {
            trigger: ".o_popover:contains(Lots / Serial Numbers):contains(SMOKE-LOT)",
        },
    ],
});
