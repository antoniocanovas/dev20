import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { MODES, modeAction, addLineAndFocusProduct } from "./mercas_modes";

class MercasTopBar extends Component {
    static template = "mercas_keys.MercasTopBar";
    static components = { Dropdown, DropdownItem };
    props = useProps({});

    setup() {
        this.modes = MODES;
        this.actionService = useService("action");
    }

    async openMode(mode) {
        await this.actionService.doAction(modeAction(mode));
    }

    addLine() {
        addLineAndFocusProduct();
    }
}

registry.category("systray").add("mercas_topbar", {
    Component: MercasTopBar,
    sequence: 1,
});
