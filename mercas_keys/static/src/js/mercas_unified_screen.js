import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { MODES, modeAction } from "./mercas_modes";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

class MercasUnifiedScreen extends Component {
    static template = "mercas_keys.MercasUnifiedScreen";
    props = useProps(standardActionServiceProps);

    setup() {
        this.modes = MODES;
        this.actionService = useService("action");
    }

    async openMode(mode) {
        await this.actionService.doAction(modeAction(mode));
    }
}

registry.category("actions").add("mercas_unified_screen", MercasUnifiedScreen);
