/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, signal, useProps } from "@odoo/owl";
import { useLayoutEffect } from "@web/owl2/utils";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { TextField, textField } from "@web/views/fields/text/text_field";

// Read-only chat transcript: keeps the scrollbar pinned to the bottom
// (the newest message) instead of leaving the user scrolled to the top
// after the form reloads.
export class ChatHistoryField extends Component {
    static template = "mercas_ai.ChatHistoryField";
    props = useProps(standardFieldProps);

    boxRef = signal.ref();

    setup() {
        useLayoutEffect(
            (value, el) => {
                if (el) {
                    el.scrollTop = el.scrollHeight;
                }
            },
            () => [this.value, this.boxRef()]
        );
    }

    get value() {
        return this.props.record.data[this.props.name] || "";
    }
}

registry.category("fields").add("mercas_chat_history", {
    component: ChatHistoryField,
    supportedTypes: ["html"],
});

// Message input: plain Enter submits (like a chat app); Shift+Enter still
// inserts a newline, in addition to the regular TextField behaviour it
// extends. Also keeps the cursor in the field after every send/reload, so
// the user can keep asking follow-up questions without re-clicking into it.
export class ChatMessageField extends TextField {
    setup() {
        super.setup();
        useLayoutEffect(
            (el) => {
                if (!el) {
                    return undefined;
                }
                el.focus();
                const end = el.value.length;
                el.setSelectionRange(end, end);
                const onKeydown = (ev) => this.onSendShortcut(ev);
                el.addEventListener("keydown", onKeydown);
                return () => el.removeEventListener("keydown", onKeydown);
            },
            () => [this.textareaRef()]
        );
    }

    async onSendShortcut(ev) {
        if (ev.key !== "Enter" || ev.shiftKey || ev.isComposing) {
            return;
        }
        ev.preventDefault();
        await this.props.record.update({ [this.props.name]: ev.target.value });
        const form = ev.target.closest(".o_form_view");
        const button = form && form.querySelector(".o_mercas_chat_send");
        if (button) {
            button.click();
        }
    }
}

registry.category("fields").add("mercas_chat_message", {
    ...textField,
    component: ChatMessageField,
});
