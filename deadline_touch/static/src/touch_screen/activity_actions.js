import { Component, signal, types, useProps } from "@odoo/owl";
import { ActivityMarkAsDone } from "@mail/core/web/activity_markasdone_popover";
import { registry } from "@web/core/registry";
import { usePopover } from "@web/core/popover/popover_hook";
import { useService } from "@web/core/utils/hooks";
import { Record } from "@web/model/relational_model/record";

// Triggered on the bus when an activity is changed from the list: the screen loads again
export const ACTIVITY_CHANGED = "DEADLINE_TOUCH:ACTIVITY_CHANGED";

/**
 * The activity, in its form as the chatter opens it (its name, type, date, person, note...): as
 * an action, so that its buttons (Save, Mark Done, Delete) close it.
 *
 * @param {Object} activity: id, res_model, res_id, summary and type
 */
export function editActivity(action, activity, onClose) {
    return action.doAction({
        type: "ir.actions.act_window",
        name: activity.summary || activity.type,
        res_model: "mail.activity",
        view_mode: "form",
        views: [[false, "form"]],
        target: "new",
        res_id: activity.id,
        context: {
            default_res_model: activity.res_model,
            default_res_id: activity.res_id,
            dialog_size: "medium",
        },
    }, { onClose });
}

/**
 * The popover of the chatter to mark it done: its feedback, and done or done and the next one
 * scheduled with the standard wizard.
 */
export function markActivityDone(popover, store, activity, target, onChanged) {
    if (popover.isOpen) {
        popover.close();
        return;
    }
    const record = store["mail.activity"].insert({
        id: activity.id,
        res_id: activity.res_id,
        res_model: activity.res_model,
        feedback: "",
    });
    popover.open(target, {
        activity: signal(record),
        hasHeader: true,
        onActivityChanged: onChanged,
    });
}

/**
 * The buttons of an open activity in the list of Deadlines, as on its card: the pencil edits it
 * and Done opens the popover of the chatter (the rest of the row opens its document).
 */
export class DeadlineTouchActivityButtons extends Component {
    static template = "deadline_touch.ActivityButtons";

    setup() {
        this.props = useProps({ record: types.instanceOf(Record) });
        this.action = useService("action");
        this.store = useService("mail.store");
        this.markDonePopover = usePopover(ActivityMarkAsDone, { position: "bottom" });
    }

    get activity() {
        const data = this.props.record.data;
        // A many2one_reference of the list: { resId, displayName }, not a number
        const resId = data.res_id;
        return {
            id: this.props.record.resId,
            res_model: data.res_model,
            res_id: typeof resId === "object" ? resId?.resId : resId,
            summary: data.summary,
            type: data.activity_type_id?.display_name || "",
        };
    }

    onChanged() {
        this.env.bus.trigger(ACTIVITY_CHANGED);
    }

    onEdit() {
        editActivity(this.action, this.activity, () => this.onChanged());
    }

    onDone(ev) {
        markActivityDone(this.markDonePopover, this.store, this.activity, ev.currentTarget, () => this.onChanged());
    }
}

registry.category("view_widgets").add("deadline_touch_activity_buttons", {
    component: DeadlineTouchActivityButtons,
    listViewWidth: [120, 160],
});
