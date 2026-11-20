import { Component, t, useProps } from "@odoo/owl";
import { localization } from "@web/core/l10n/localization";
import { parseFloat } from "@web/views/fields/parsers";

/** Operators of the keypad, as shown in the field, and the keys typed for them on a keyboard. */
const OPERATORS = { "+": "+", "−": "-", "×": "*", "÷": "/" };
const KEYBOARD_OPERATORS = { "-": "−", "*": "×", "x": "×", "X": "×", "/": "÷" };
const OPERATOR_RE = /([+\-−×÷*/xX])/;

/**
 * Keypad for the quantities, prices and amounts of the counter: big keys for a touch screen,
 * with the four operations of a simple calculator.
 * It only tells which key was pressed ("0"-"9", the decimal point, an operator, "=",
 * "backspace" or "clear"): the screen applies it to the field being edited, so the keypad
 * doesn't keep any value. The field holds the operation ("12,5×3") until "=" or until it's
 * confirmed, when it's worked out (evalNumpadExpression).
 */
export class TouchNumpad extends Component {
    static template = "mercas_touch.TouchNumpad";
    props = useProps({
        onKey: t.function(),
        // Without decimals (counters of boxes) the decimal point and the operators are disabled
        decimals: t.boolean().optional(true),
        // Without the column of operators, for a keypad that only ever takes whole numbers
        calculator: t.boolean().optional(true),
    });

    get decimalPoint() {
        return localization.decimalPoint;
    }

    /** Rows of the keypad: three digits and an operator. */
    get rows() {
        return [
            ["7", "8", "9", "÷"],
            ["4", "5", "6", "×"],
            ["1", "2", "3", "−"],
        ];
    }

    isOperator(key) {
        return key in OPERATORS;
    }

    onKey(key) {
        this.props.onKey(key);
    }
}

/** Whether `value` is an operation still to work out ("12×3"), not just a number. */
export function isNumpadExpression(value) {
    const text = String(value || "").trim();
    // As in the fields of Odoo, "=" starts an operation ("=50*2-3"); a minus at the start is
    // the sign of the number, not an operation
    return text.startsWith("=") || OPERATOR_RE.test(text.replace(/^-/, ""));
}

/**
 * The number of the operation written in a field ("12,5×3+1"), the multiplications and
 * divisions first. Numbers are read as written in the language of the user. NaN if it can't
 * be worked out (an operator without a number, a division by zero...).
 */
export function evalNumpadExpression(value) {
    let text = String(value || "").trim();
    if (!text) {
        return 0;
    }
    if (text.startsWith("=")) {
        // The operation of the fields of Odoo ("=(50*2-3)^2"), worked out by its parser
        try {
            const number = parseFloat(text);
            return Number.isFinite(number) ? Math.round(number * 1e6) / 1e6 : NaN;
        } catch {
            return NaN;
        }
    }
    let sign = 1;
    if (text.startsWith("-")) {
        sign = -1;
        text = text.slice(1);
    }
    const parts = text.split(OPERATOR_RE);
    const numbers = [];
    const operators = [];
    for (let i = 0; i < parts.length; i++) {
        if (i % 2) {
            const op = KEYBOARD_OPERATORS[parts[i]] || parts[i];
            operators.push(OPERATORS[op]);
            continue;
        }
        const part = parts[i].trim();
        if (!part) {
            return NaN;
        }
        let number;
        try {
            number = parseFloat(part);
        } catch {
            return NaN;
        }
        numbers.push(number);
    }
    numbers[0] *= sign;
    // Multiplications and divisions first, then additions and subtractions
    const terms = [numbers[0]];
    const termOps = [];
    operators.forEach((op, i) => {
        const number = numbers[i + 1];
        if (op === "*") {
            terms.push(terms.pop() * number);
        } else if (op === "/") {
            // A division by zero isn't finite: NaN below
            terms.push(terms.pop() / number);
        } else {
            terms.push(number);
            termOps.push(op);
        }
    });
    let result = terms[0];
    termOps.forEach((op, i) => {
        result = op === "+" ? result + terms[i + 1] : result - terms[i + 1];
    });
    if (!Number.isFinite(result)) {
        return NaN;
    }
    // Without the noise of the floating point (0,1+0,2)
    return Math.round(result * 1e6) / 1e6;
}

/** A number as written in a field: the decimal point of the user, no thousands separator. */
function formatNumpadNumber(number) {
    return String(number).replace(".", localization.decimalPoint);
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
    if (key === "=") {
        if (!isNumpadExpression(value)) {
            return value;
        }
        const result = evalNumpadExpression(value);
        // An operation that can't be worked out stays, to be corrected
        return Number.isNaN(result) ? value : formatNumpadNumber(result);
    }
    if (key in OPERATORS) {
        if (!value) {
            return value;
        }
        // Another operator replaces the last one: it was a mistake
        return OPERATOR_RE.test(value.slice(-1)) ? value.slice(0, -1) + key : value + key;
    }
    if (key === localization.decimalPoint) {
        // One decimal point for each number of the operation
        const number = value.split(OPERATOR_RE).pop();
        if (number.includes(key)) {
            return value;
        }
    }
    return value + key;
}
