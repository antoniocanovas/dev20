import { Component, t, useProps } from "@odoo/owl";
import { localization } from "@web/core/l10n/localization";

/**
 * Keypad for the quantities, prices and amounts of the counter: big keys for a touch screen.
 * It edits the text of a field; a scale or a keyboard can still type into the field itself.
 */
export class TouchNumpad extends Component {
    static template = "mercas_touch.TouchNumpad";
    props = useProps({
        value: t.string(),
        onInput: t.function(),
        decimals: t.boolean().optional(true),
    });

    get decimalPoint() {
        return localization.decimalPoint;
    }

    get keys() {
        return ["7", "8", "9", "4", "5", "6", "1", "2", "3"];
    }

    onKey(key) {
        const value = this.props.value || "";
        if (key === this.decimalPoint && value.includes(key)) {
            return;
        }
        this.props.onInput(value + key);
    }

    onBackspace() {
        this.props.onInput((this.props.value || "").slice(0, -1));
    }

    onClear() {
        this.props.onInput("");
    }
}
