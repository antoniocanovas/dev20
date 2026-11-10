import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("scrap_repair_tour", {
    steps: () => [
        {
            trigger: ".o_scrap_touch_mode_resale",
            run: "click",
        },
        {
            content: "The vehicles on sale",
            trigger: ".o_scrap_touch_draft_filter_on_sale",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_on_sale .o_scrap_touch_vehicle:contains(TOURREP1)",
            run: "click",
        },
        {
            content: "Repair it: a repair order, in a dialog",
            trigger: ".o_scrap_touch_repair",
            run: "click",
        },
        {
            trigger: ".modal-title:contains(TOURREP1)",
        },
        {
            trigger: ".modal .o_form_view .o_field_widget[name=lot_id] input:value(TOURREP1)",
        },
        {
            trigger: ".modal .btn-close",
            run: "click",
        },
        {
            content: "Its repair not done yet, on the button",
            trigger: ".o_scrap_touch_repair .o_scrap_touch_open_repair",
        },
    ],
});
