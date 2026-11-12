import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { usePopover } from "@web/core/popover/popover_hook";
import { useService } from "@web/core/utils/hooks";
import {
    ProjectTaskNameWithSubtaskCountCharField,
    projectTaskNameWithSubtaskCountCharField,
} from "@project/components/project_task_name_with_subtask_count_char_field/project_task_name_with_subtask_count_char_field";

const MODEL = "project.task.touch";
const CLOSED_STATES = ["1_done", "1_canceled"];

/**
 * The open subtasks of a task, under its row of the list: closed with a touch (done) or changed
 * to another state, and new ones added, as with the subtasks of the cards of the kanban.
 */
export class SubtasksPopover extends Component {
    static template = "project_task_touch.SubtasksPopover";
    props = useProps({
        taskId: t.number(),
        states: t.array(),
        onChanged: t.function(),
        close: t.function().optional(),
    });

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({ subtasks: [], name: "", sending: false });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.subtasks = await this.orm.call(MODEL, "get_subtasks", [this.props.taskId]);
    }

    async setState(subtask, state) {
        if (this.state.sending) {
            return;
        }
        this.state.sending = true;
        try {
            await this.orm.write("project.task", [subtask.id], { state });
            if (CLOSED_STATES.includes(state)) {
                this.notification.add(_t("%s closed.", subtask.name), { type: "success" });
            }
            await this.load();
            await this.props.onChanged();
        } finally {
            this.state.sending = false;
        }
    }

    onNameInput(ev) {
        this.state.name = ev.target.value;
    }

    async onNameKeydown(ev) {
        if (ev.key === "Enter") {
            await this.onAdd();
        }
    }

    async onAdd() {
        const name = this.state.name.trim();
        if (!name || this.state.sending) {
            return;
        }
        this.state.sending = true;
        try {
            await this.orm.call(MODEL, "create_subtask", [this.props.taskId, name]);
            this.state.name = "";
            await this.load();
            await this.props.onChanged();
        } finally {
            this.state.sending = false;
        }
    }
}

/**
 * The name of the task with how many subtasks are closed, as in the list of Odoo, but as a
 * button that opens its subtasks (or adds the first one).
 */
export class TouchNameSubtasksField extends ProjectTaskNameWithSubtaskCountCharField {
    static template = "project_task_touch.NameSubtasksField";

    setup() {
        super.setup();
        this.subtasksPopover = usePopover(SubtasksPopover, { position: "bottom-start" });
    }

    onSubtasks(ev) {
        if (this.subtasksPopover.isOpen) {
            this.subtasksPopover.close();
            return;
        }
        const record = this.props.record;
        this.subtasksPopover.open(ev.currentTarget, {
            taskId: record.resId,
            states: record.fields.state.selection,
            onChanged: () => record.load(),
        });
    }
}

registry.category("fields").add("project_task_touch_name_subtasks", {
    ...projectTaskNameWithSubtaskCountCharField,
    component: TouchNameSubtasksField,
});
