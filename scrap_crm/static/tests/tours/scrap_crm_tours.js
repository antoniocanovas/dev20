import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("scrap_crm_available_tour", {
    steps: () => [
        {
            content: "What is available for the opportunity",
            trigger: ".o_form_view button[name=action_scrap_available_parts]",
            run: "click",
        },
        {
            content: "In stock, of the brand and the template of the opportunity",
            trigger: ".o_scrap_crm_available_mode_stock.btn-primary",
        },
        {
            trigger: ".o_scrap_crm_available_brand option:selected:contains(Tour Brand):not(:visible)",
        },
        {
            trigger: ".o_scrap_crm_available_template option:selected:contains(Tour Engine):not(:visible)",
        },
        {
            content: "The engine dismantled, not the cars",
            trigger: ".o_scrap_crm_available_product:contains(Tour Engine)",
        },
        {
            trigger: ".o_scrap_touch_grid:not(:has(.o_scrap_crm_available_product:contains(Tour Car)))",
        },
        {
            content: "With a link to open it in a new tab",
            trigger: ".o_scrap_crm_available_item:has(.o_scrap_crm_available_product:contains(Tour Engine)) a.o_scrap_crm_available_open_tab[target=_blank][href^='/odoo/product.template/']",
        },
        {
            content: "Its photos, from its picture",
            trigger: ".o_scrap_crm_available_item:has(.o_scrap_crm_available_product:contains(Tour Engine)) .o_scrap_crm_available_photo_count:contains(2)",
        },
        {
            trigger: ".o_scrap_crm_available_product:contains(Tour Engine) .o_scrap_crm_available_photo",
            run: "click",
        },
        {
            trigger: ".o_scrap_crm_available_gallery_position:contains(1 / 2)",
        },
        {
            content: "The next one",
            trigger: ".o_scrap_crm_available_gallery_next",
            run: "click",
        },
        {
            trigger: ".o_scrap_crm_available_gallery_position:contains(2 / 2)",
        },
        {
            content: "Back to the list, the product not opened",
            trigger: ".o_scrap_crm_available_gallery_close",
            run: "click",
        },
        {
            trigger: ".o_scrap_crm_available:not(:has(.o_scrap_crm_available_gallery)):not(:has(.modal))",
        },
        {
            content: "Searched by its name",
            trigger: ".o_scrap_crm_available_search",
            run: "edit nothing at all",
        },
        {
            trigger: ".o_scrap_crm_available_none",
        },
        {
            trigger: ".o_scrap_crm_available_search",
            run: "edit tourav1",
        },
        {
            content: "Assembled: the car with the engine asked for still to dismantle",
            trigger: ".o_scrap_crm_available_mode_assembled",
            run: "click",
        },
        {
            trigger: ".o_scrap_crm_available_product:contains(TOURAV1) .o_scrap_crm_available_pending:contains(Tour Engine)",
        },
        {
            content: "Back to the opportunity",
            trigger: ".o_scrap_crm_available_back",
            run: "click",
        },
        {
            trigger: ".o_form_view .o_field_widget[name=name] textarea, .o_form_view .o_field_widget[name=name] input",
        },
    ],
});
