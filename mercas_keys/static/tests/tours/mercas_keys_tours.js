import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("mercas_keys_tour", {
    steps: () => [
        {
            content: "Open the sales from the unified screen",
            trigger: ".o_mercas_mode_btn:contains(Sales)",
            run: "click",
        },
        {
            trigger: ".o_list_view .o_breadcrumb:contains(Sales)",
        },
        {
            content: "F2 opens the purchases",
            trigger: ".o_list_view",
            run: "press F2",
        },
        {
            trigger: ".o_list_view .o_breadcrumb:contains(Purchases)",
        },
        {
            content: "The systray menu opens the modes too",
            trigger: ".o_mercas_topbar_icon",
            run: "click",
        },
        {
            trigger: ".o-dropdown-item:contains(Payments)",
            run: "click",
        },
        {
            trigger: ".o_list_view .o_breadcrumb:contains(Payments)",
        },
    ],
});
