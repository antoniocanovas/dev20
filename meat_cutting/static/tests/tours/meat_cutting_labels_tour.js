import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("meat_cutting_labels_tour", {
    steps: () => [
        {
            content: "The main menu goes back to Odoo",
            trigger: ".o_meat_cutting_home .o_meat_cutting_odoo_home",
        },
        {
            content: "Open Labels",
            trigger: ".o_meat_cutting_mode_labels",
            run: "click",
        },
        {
            content: "Type the lot of the label",
            trigger: ".o_meat_cutting_search_input",
            run: "edit L001 && press Enter",
        },
        {
            content: "The piece opens in Labels, with its cut label first",
            trigger: ".o_meat_cutting_relabel_format.btn-primary:contains(Cut Label)",
        },
        {
            content: "Choose the label of the stock",
            trigger: ".o_meat_cutting_relabel_format:contains(Piece Label)",
            run: "click",
        },
        {
            content: "Edit it",
            trigger: ".o_meat_cutting_screen button:contains(Edit label)",
            run: "click",
        },
        {
            content: "Add a note",
            trigger: ".modal #o_meat_cutting_label_note",
            run: "edit Keep cold",
        },
        {
            content: "Save",
            trigger: ".modal .o_meat_cutting_label_save",
            run: "click",
        },
        {
            content: "Back to the main menu with the grid",
            trigger: ".o_meat_cutting_home_button:not(:disabled)",
            run: "click",
        },
        {
            content: "The main menu is shown again",
            trigger: ".o_meat_cutting_home .o_meat_cutting_mode_labels",
        },
    ],
});
