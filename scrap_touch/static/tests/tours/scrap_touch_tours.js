import { registry } from "@web/core/registry";

// Data made by the Python test: a supplier and a vehicle tracked by serial number (its license
// plate)

/** Steps to type `keys` with the keypad. */
function numpad(keys) {
    return [...keys].map((key) => ({
        trigger: `.o_scrap_touch_numpad_key:contains(${key})`,
        run: "click",
    }));
}

/** Steps to add a vehicle line with its license plate, as typed, and its price. */
function addVehicle(typed, plate, price) {
    return [
        {
            content: `Choose the vehicle ${plate}`,
            trigger: ".o_scrap_touch_product:contains(Tour Vehicle)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_lot_name",
            run: `edit ${typed}`,
        },
        ...numpad(price),
        {
            trigger: `.o_scrap_touch_price:value(${price})`,
        },
        {
            trigger: ".o_scrap_touch_add",
            run: "click",
        },
        {
            trigger: `.o_scrap_touch_line_lot:contains(${plate})`,
        },
        {
            content: "Saved in draft",
            trigger: ".o_scrap_touch_save_state .text-success",
        },
    ];
}

/** Steps to open an entry (the scrap entry by default) and start a new purchase. */
function newPurchase(mode = "entry") {
    return [
        {
            content: `Open the ${mode}`,
            trigger: `.o_scrap_touch_mode_${mode}`,
            run: "click",
        },
        {
            content: "A new purchase: the supplier is asked",
            trigger: ".o_scrap_touch_new_draft",
            run: "click",
        },
    ];
}

registry.category("web_tour.tours").add("scrap_touch_entry_tour", {
    steps: () => [
        ...newPurchase(),
        {
            content: "Search the supplier",
            trigger: ".o_scrap_touch_partner_search",
            run: "edit Tour Scrap",
        },
        {
            trigger: ".o_scrap_touch_partner:contains(Tour Scrap Supplier)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_partner_name:contains(Tour Scrap Supplier)",
        },
        ...addVehicle("1234 abc", "1234ABC", "1250"),
        ...addVehicle("5678-bcd", "5678BCD", "800"),
        ...addVehicle("9999xyz", "9999XYZ", "500"),
        {
            content: "Two lines can't have the same license plate",
            trigger: ".o_scrap_touch_product:contains(Tour Vehicle)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_lot_name",
            run: "edit 1234-ABC",
        },
        ...numpad("1"),
        {
            trigger: ".o_scrap_touch_add",
            run: "click",
        },
        {
            trigger: ".o_notification:contains(1234ABC)",
        },
        {
            content: "Leave that line",
            trigger: ".o_scrap_touch_cancel_entry",
            run: "click",
        },
        {
            content: "Change the price of the second vehicle",
            trigger: ".o_scrap_touch_line:contains(5678BCD) [role=button]",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_price:value(800)",
        },
        {
            trigger: ".o_scrap_touch_numpad_clear",
            run: "click",
        },
        ...numpad("900"),
        {
            trigger: ".o_scrap_touch_add:contains(Update line)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_line:contains(5678BCD):contains(900)",
        },
        {
            content: "Remove the third vehicle",
            trigger: ".o_scrap_touch_line:contains(9999XYZ) .o_scrap_touch_remove_line",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_ticket:not(:has(.o_scrap_touch_line:contains(9999XYZ)))",
        },
        {
            trigger: ".o_scrap_touch_total:contains(2,150)",
        },
        {
            trigger: ".o_scrap_touch_save_state .text-success",
        },
        {
            content: "Leave the purchase: it stays in draft",
            trigger: ".o_scrap_touch_back",
            run: "click",
        },
        {
            content: "Resume it from the drafts",
            trigger: ".o_scrap_touch_draft:contains(Tour Scrap Supplier):contains(2 vehicles)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_line:contains(1234ABC)",
        },
        {
            trigger: ".o_scrap_touch_line:contains(5678BCD):contains(900)",
        },
        {
            content: "Purchase and receive",
            trigger: ".o_scrap_touch_purchase",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_done_lines:contains(1234ABC):contains(5678BCD)",
        },
        {
            content: "Another purchase of the same supplier",
            trigger: ".o_scrap_touch_new",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_ticket:not(:has(.o_scrap_touch_line))",
        },
        {
            content: "Back to the drafts: the purchase isn't there anymore",
            trigger: ".o_scrap_touch_back",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_body:not(:has(.o_scrap_touch_draft:contains(Tour Scrap Supplier)))",
        },
    ],
});

registry.category("web_tour.tours").add("scrap_touch_new_partner_tour", {
    steps: () => [
        ...newPurchase(),
        {
            content: "Search a supplier that doesn't exist yet",
            trigger: ".o_scrap_touch_partner_search",
            run: "edit Brand New Yard",
        },
        {
            content: "Create it",
            trigger: ".o_scrap_touch_new_partner",
            run: "click",
        },
        {
            content: "The name is the one searched",
            trigger: ".modal .o_scrap_touch_new_partner_name input:value(Brand New Yard)",
        },
        {
            trigger: ".modal .o_field_widget[name=city] input",
            run: "edit Cartagena",
        },
        {
            content: "Save",
            trigger: ".modal .o_form_button_save",
            run: "click",
        },
        {
            content: "The purchase goes on with the new supplier",
            trigger: ".o_scrap_touch_partner_name:contains(Brand New Yard)",
        },
        ...addVehicle("4321 zzz", "4321ZZZ", "300"),
        {
            content: "Purchase only: the vehicle is received later",
            trigger: ".o_scrap_touch_purchase_only",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_done_to_receive",
        },
        {
            trigger: ".o_scrap_touch_done_lines:contains(4321ZZZ)",
        },
        {
            content: "Back to the list",
            trigger: ".o_scrap_touch_back",
            run: "click",
        },
        {
            content: "The purchases to receive",
            trigger: ".o_scrap_touch_draft_filter_to_receive",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_draft:contains(Brand New Yard) .o_scrap_touch_badge_to_receive",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_summary_title",
        },
        {
            content: "Receive the vehicle",
            trigger: ".o_scrap_touch_receive",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_states:contains(Received)",
        },
        {
            trigger: ".o_scrap_touch_back_to_list",
            run: "click",
        },
        {
            content: "Nothing left to receive",
            trigger: ".o_scrap_touch_draft_filter_to_receive.btn-primary",
        },
        {
            trigger: ".o_scrap_touch_body:not(:has(.o_scrap_touch_draft:contains(Brand New Yard)))",
        },
    ],
});

registry.category("web_tour.tours").add("scrap_touch_resale_tour", {
    steps: () => [
        ...newPurchase("resale"),
        {
            trigger: ".o_scrap_touch_partner_search",
            run: "edit Tour Scrap",
        },
        {
            trigger: ".o_scrap_touch_partner:contains(Tour Scrap Supplier)",
            run: "click",
        },
        ...addVehicle("7777 rst", "7777RST", "2500"),
        {
            content: "Leave it in draft",
            trigger: ".o_scrap_touch_back",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_draft:contains(Tour Scrap Supplier)",
        },
        {
            content: "The scrap entry doesn't list it",
            trigger: ".o_scrap_touch_tabs button:contains(F1)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_draft_filter_draft.btn-primary",
        },
        {
            trigger: ".o_scrap_touch_body:not(:has(.o_scrap_touch_draft:contains(Tour Scrap Supplier)))",
        },
        {
            content: "Back to the purchase/sale entry",
            trigger: ".o_scrap_touch_tabs button:contains(F2)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_draft:contains(Tour Scrap Supplier)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_purchase",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_done_lines:contains(7777RST)",
        },
    ],
});

// Data made by the Python test: a vehicle to dismantle received 12 days ago, late to
// decontaminate (10 days), and a vehicle to repair and sell
registry.category("web_tour.tours").add("scrap_touch_cat_tour", {
    steps: () => [
        {
            content: "The main menu shows the vehicles late",
            trigger: ".o_scrap_touch_mode_decontamination .o_scrap_touch_mode_late:contains(1)",
            run: "click",
        },
        {
            content: "Pending, the nearest limit first",
            trigger: ".o_scrap_touch_vehicle_filter_pending.btn-primary",
        },
        {
            trigger: ".o_scrap_touch_vehicle:contains(TOUR001) .o_scrap_touch_deadline.text-bg-danger:contains(2 days late)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_vehicle_location:contains(TOUR001)",
        },
        {
            content: "It can't be dismantled before it is decontaminated",
            trigger: ".o_scrap_touch_stage_scrap:not(:has(.o_scrap_touch_dismantle))",
        },
        {
            content: "Decontaminate it: the waste products of the company",
            trigger: ".o_scrap_touch_stage_decontamination .o_scrap_touch_decontaminate",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_part:contains(Tour Oil)",
            run: "click",
        },
        {
            content: "As much as taken out, on the keypad",
            trigger: ".o_scrap_touch_numpad_key:contains(3)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_waste_quantity:value(3)",
        },
        {
            trigger: ".o_scrap_touch_part_option_discarded",
            run: "click",
        },
        {
            content: "Into the waste zone by default",
            trigger: ".o_scrap_touch_part_location:contains(Zona de desecho)",
        },
        {
            trigger: ".o_scrap_touch_confirm_part:enabled",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_parts:contains(Tour Oil)",
        },
        {
            content: "Again, as many times as needed: one more litre, typed on the keyboard",
            trigger: ".o_scrap_touch_part:contains(Tour Oil)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_waste_quantity:focus",
            run: "edit 1",
        },
        {
            trigger: ".o_scrap_touch_part_option_discarded",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_confirm_part:enabled",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_parts tbody:has(tr:nth-child(2))",
        },
        {
            content: "Corrected: 2 litres instead of 1",
            trigger: ".o_scrap_touch_parts tr:first-child .o_scrap_touch_edit_part",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_part_option_discarded.btn-danger",
        },
        {
            trigger: ".o_scrap_touch_waste_quantity:focus",
            run: "edit 2",
        },
        {
            trigger: ".o_scrap_touch_confirm_part:enabled:contains(Update)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_parts tr:first-child td:first-child:contains(2)",
        },
        {
            content: "Decontaminated",
            trigger: ".o_scrap_touch_finish",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_dismantled",
        },
        {
            trigger: ".o_scrap_touch_close_dismantle",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_stage_decontamination .o_scrap_touch_deadline.text-bg-success",
        },
        {
            content: "Now it can be dismantled",
            trigger: ".o_scrap_touch_stage_scrap .o_scrap_touch_dismantle",
        },
        {
            trigger: ".o_scrap_touch_back_to_vehicles",
            run: "click",
        },
        {
            content: "Not pending anymore",
            trigger: ".o_scrap_touch_body:not(:has(.o_scrap_touch_vehicle:contains(TOUR001)))",
        },
        {
            content: "It is pending dismantling",
            trigger: ".o_scrap_touch_tabs button:contains(F4)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_vehicle:contains(TOUR001)",
            run: "click",
        },
        {
            content: "Dismantle it: the components of its bill of materials",
            trigger: ".o_scrap_touch_stage_scrap .o_scrap_touch_dismantle",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_part:contains(Tour Wheel) .o_scrap_touch_part_qty:contains(2)",
            run: "click",
        },
        {
            content: "One by one: both wheels",
            trigger: ".o_scrap_touch_part_quantity:contains(1)",
        },
        {
            trigger: ".o_scrap_touch_part_plus",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_part_quantity:contains(2)",
        },
        {
            content: "An option is required",
            trigger: ".o_scrap_touch_confirm_part:disabled",
        },
        {
            content: "Dismantled in good condition, in one tap",
            trigger: ".o_scrap_touch_part_option_good",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_part_option_good.btn-success",
        },
        {
            content: "Into the location of the vehicle by default, or another one",
            trigger: ".o_scrap_touch_part_location:contains(TOUR001)",
        },
        {
            trigger: ".o_scrap_touch_change_location",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_location_search",
            run: "edit Tour Shelf",
        },
        {
            trigger: ".o_scrap_touch_location:contains(Tour Shelf)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_part_location:contains(Tour Shelf)",
        },
        {
            trigger: ".o_scrap_touch_confirm_part:enabled",
            run: "click",
        },
        {
            content: "Marked, and no more wheels to dismantle",
            trigger: ".o_scrap_touch_parts:contains(Tour Wheel)",
        },
        {
            trigger: ".o_scrap_touch_dismantle_screen:not(:has(.o_scrap_touch_part:contains(Tour Wheel)))",
        },
        {
            content: "The engine marked as missing by mistake, and undone",
            trigger: ".o_scrap_touch_part:contains(Tour Engine)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_part_option_missing",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_confirm_part:enabled",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_parts tr:contains(Tour Engine) .o_scrap_touch_undo_part",
            run: "click",
        },
        {
            trigger: ".modal .btn-primary:contains(Undo)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_parts:not(:contains(Tour Engine))",
        },
        {
            content: "Finished, although the engine is left, on another day",
            trigger: ".o_scrap_touch_part:contains(Tour Engine)",
        },
        {
            trigger: ".o_scrap_touch_finish_on_date",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_dismantled",
        },
        {
            trigger: ".o_scrap_touch_close_dismantle",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_stage_scrap .o_scrap_touch_deadline.text-bg-success",
        },
        {
            content: "The vehicles: search by license plate",
            trigger: ".o_scrap_touch_tabs button:contains(F5)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_vehicle_filter_all",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_vehicle_search",
            run: "edit tour 002",
        },
        {
            trigger: ".o_scrap_touch_body:not(:has(.o_scrap_touch_vehicle:contains(TOUR001)))",
        },
        {
            trigger: ".o_scrap_touch_vehicle:contains(TOUR002)",
            run: "click",
        },
        {
            content: "A vehicle to sell has no legal deadlines",
            trigger: ".o_scrap_touch_vehicle_summary:not(:has(.o_scrap_touch_deadlines))",
        },
        {
            trigger: ".o_scrap_touch_back",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_vehicle_search",
        },
        {
            content: "The purchase/sale entry: its vehicles on sale, in stock",
            trigger: ".o_scrap_touch_tabs button:contains(F2)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_draft_filter_on_sale.btn-outline-info",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_draft_filter_on_sale.btn-info",
        },
        {
            trigger: ".o_scrap_touch_on_sale .o_scrap_touch_vehicle:contains(TOUR002)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_vehicle_summary .o_scrap_touch_vehicle_plate:contains(TOUR002)",
        },
        {
            content: "Back to the vehicles on sale",
            trigger: ".o_scrap_touch_back",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_on_sale .o_scrap_touch_vehicle:contains(TOUR002)",
        },
        {
            content: "Not in the scrap entry",
            trigger: ".o_scrap_touch_tabs button:contains(F1)",
            run: "click",
        },
        {
            trigger: ".o_scrap_touch_draft_filter_draft.btn-primary",
        },
        {
            trigger: ".o_scrap_touch_draft_filters:not(:has(.o_scrap_touch_draft_filter_on_sale))",
        },
    ],
});
