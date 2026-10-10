import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("meat_cutting_screen_tour", {
    steps: () => [
        {
            content: "Search something that does not exist",
            trigger: ".o_meat_cutting_search_input",
            run: "edit zzz",
        },
        {
            content: "Nothing matches",
            trigger: ".o_meat_cutting_no_match",
        },
        {
            content: "Search the lot (case insensitive)",
            trigger: ".o_meat_cutting_search_input",
            run: "edit l001",
        },
        {
            content: "Pick the receipt",
            trigger: ".o_meat_cutting_tile:contains(WH/IN)",
            run: "click",
        },
        {
            content: "Pick the carcass (single lot: no lot step)",
            trigger: ".o_meat_cutting_tile:contains(Pork Carcass)",
            run: "click",
        },
        {
            content: "Pick the cutting method (the carcass has two BoMs)",
            trigger: ".o_meat_cutting_bom:contains(Standard)",
            run: "click",
        },
        {
            content: "The cutting method is shown",
            trigger: ".o_meat_cutting_bom_name:contains(Standard)",
        },
        {
            content: "Label printing is disabled by default",
            trigger: "#o_meat_cutting_autoprint:not(:checked)",
        },
        {
            content: "Type the weight",
            trigger: ".o_meat_cutting_weight_input",
            run: "edit 2,5",
        },
        {
            content: "Press the loin cut",
            trigger: ".o_meat_cutting_component:contains(Pork Loin)",
            run: "click",
        },
        {
            content: "The weighed cut is listed",
            trigger: ".o_meat_cutting_lines li:contains(Pork Loin):contains(2.5)",
        },
        {
            content: "The cut counts its weighed pieces and can be weighed again",
            trigger: ".o_meat_cutting_weighed:contains(Pork Loin):contains(1 pcs):not(:disabled)",
        },
        {
            content: "The piece is packed",
            trigger: ".o_meat_cutting_lines li:contains(Pork Loin) .o_meat_cutting_package",
        },
        {
            content: "Freeze the loin",
            trigger: ".o_meat_cutting_lines li:contains(Pork Loin) .o_meat_cutting_line_freeze",
            run: "click",
        },
        {
            content: "The frozen product is produced",
            trigger: ".o_meat_cutting_lines li:contains(Frozen Pork Loin) .o_meat_cutting_line_freeze.btn-info",
        },
        {
            content: "Edit the label of the cut",
            trigger: ".o_meat_cutting_lines li:contains(Pork Loin) .o_meat_cutting_edit_label",
            run: "click",
        },
        {
            content: "Change the product name printed",
            trigger: ".modal #o_meat_cutting_label_product_name",
            run: "edit Iberian Loin",
        },
        {
            content: "Save the label",
            trigger: ".modal .o_meat_cutting_label_save",
            run: "click",
        },
        {
            content: "The edited label is flagged",
            trigger: ".o_meat_cutting_lines li:contains(Pork Loin) .o_meat_cutting_edit_label.btn-warning",
        },
        {
            content: "Open the label formats",
            trigger: ".o_meat_cutting_format_button",
            run: "click",
        },
        {
            content: "Pick a label format",
            trigger: ".o_meat_cutting_format:contains(Cut Label)",
            run: "click",
        },
        {
            content: "The chosen format is shown",
            trigger: ".o_meat_cutting_format_button:contains(Cut Label)",
        },
        {
            content: "Finish the session",
            trigger: ".o_meat_cutting_footer button:contains(Finish)",
            run: "click",
        },
        {
            content: "Confirm",
            trigger: ".modal .modal-footer .btn-primary",
            run: "click",
        },
        {
            content: "Session validated",
            trigger: ".o_meat_cutting_screen .alert-success",
        },
    ],
});
