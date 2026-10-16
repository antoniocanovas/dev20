import { Component, t, useProps } from "@odoo/owl";
import { localization } from "@web/core/l10n/localization";

/**
 * Keypad for the quantities, prices and amounts of the counter: big keys for a touch screen.
 * It only tells which key was pressed ("0"-"9", the decimal point, "backspace" or "clear"):
 * the screen applies it to the field being edited, so the keypad doesn't keep any value.
 */
export class TouchNumpad extends Component {
    static template = "mercas_touch.TouchNumpad";
    props = useProps({
        onKey: t.function(),
        decimals: t.boolean().optional(true),
    });

    get decimalPoint() {
        return localization.decimalPoint;
    }

    get keys() {
        return ["7", "8", "9", "4", "5", "6", "1", "2", "3"];
    }

    onKey(key) {
        this.props.onKey(key);
    }
}

/** The text of a field after pressing `key` on the keypad. */
export function applyNumpadKey(value, key) {
    value = value || "";
    if (key === "clear") {
        return "";
    }
    if (key === "backspace") {
        return value.slice(0, -1);
    }
    if (key === localization.decimalPoint && value.includes(key)) {
        return value;
    }
    return value + key;
}
