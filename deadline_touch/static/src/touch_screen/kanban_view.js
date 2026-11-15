import { registry } from "@web/core/registry";
import { projectTaskKanbanView } from "@project/views/project_task_kanban/project_task_kanban_view";

const ProjectTaskKanbanController = projectTaskKanbanView.Controller;

/**
 * The kanban of the tasks of Deadlines, grouped by state: a task whose state is changed on its card
 * (with the state widget, not by dragging it) goes to the column of its new state at once.
 */
export class DeadlineTouchKanbanController extends ProjectTaskKanbanController {
    onRecordSaved(record) {
        super.onRecordSaved(...arguments);
        const root = this.model.root;
        if (root.isGrouped && root.groupByField?.name === "state" && record.group
            && record.data.state !== record.group.value) {
            // Not awaited: the save is still running, and the load waits for it
            root.load();
        }
    }
}

export const projectTaskTouchKanbanView = {
    ...projectTaskKanbanView,
    Controller: DeadlineTouchKanbanController,
};

registry.category("views").add("deadline_touch_kanban", projectTaskTouchKanbanView);
