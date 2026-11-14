import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("project_task_touch_tour", {
    steps: () => [
        {
            content: "The tasks of the files, in columns by state",
            trigger: ".o_project_task_touch_mode_tasks.btn-primary",
        },
        {
            trigger: ".o_kanban_group:has(.o_column_title:contains(In Progress)) .o_kanban_record:contains(Tour Existing Task)",
        },
        {
            content: "By deadline, then by priority",
            trigger: ".o_kanban_record:contains(Tour Urgent Task)",
            run() {
                const names = [...document.querySelectorAll(".o_kanban_record")]
                    .map((record) => record.textContent)
                    .map((text) => ["Tour Sooner Task", "Tour Later Task", "Tour Urgent Task", "Tour Existing Task"].find((name) => text.includes(name)))
                    .filter(Boolean);
                const expected = ["Tour Sooner Task", "Tour Later Task", "Tour Urgent Task", "Tour Existing Task"];
                if (JSON.stringify(names) !== JSON.stringify(expected)) {
                    throw new Error(`Wrong order: ${names.join(", ")}`);
                }
            },
        },
        {
            content: "As a list, with the same order",
            trigger: ".o_project_task_touch_view_list",
            run: "click",
        },
        {
            trigger: ".o_list_view .o_data_row:contains(Tour Urgent Task)",
            run() {
                const names = [...document.querySelectorAll(".o_list_view .o_data_row")]
                    .map((row) => row.textContent)
                    .map((text) => ["Tour Sooner Task", "Tour Later Task", "Tour Urgent Task", "Tour Existing Task"].find((name) => text.includes(name)))
                    .filter(Boolean);
                const expected = ["Tour Sooner Task", "Tour Later Task", "Tour Urgent Task", "Tour Existing Task"];
                if (JSON.stringify(names) !== JSON.stringify(expected)) {
                    throw new Error(`Wrong order in the list: ${names.join(", ")}`);
                }
            },
        },
        {
            content: "Its subtasks closed from the list, as on the kanban",
            trigger: ".o_data_row:contains(Tour Existing Task) .o_project_task_touch_subtasks:contains(0/1)",
            run: "click",
        },
        {
            trigger: ".o_project_task_touch_subtask:contains(Tour Subtask) .o_project_task_touch_subtask_done",
            run: "click",
        },
        {
            trigger: ".o_project_task_touch_subtasks_popover:not(:has(.o_project_task_touch_subtask))",
        },
        {
            trigger: ".o_data_row:contains(Tour Existing Task) .o_project_task_touch_subtasks:contains(1/1)",
        },
        {
            content: "And a new one added",
            trigger: ".o_project_task_touch_subtask_new",
            run: "edit Tour Subtask 2 && press Enter",
        },
        {
            trigger: ".o_project_task_touch_subtask:contains(Tour Subtask 2)",
        },
        {
            trigger: ".o_data_row:contains(Tour Existing Task) .o_project_task_touch_subtasks:contains(1/2)",
            run: "click",
        },
        {
            trigger: "body:not(:has(.o_project_task_touch_subtasks_popover))",
        },
        {
            content: "Filtered as it is written, also in the list",
            trigger: ".o_project_task_touch_search",
            run: "edit Tour Sooner",
        },
        {
            trigger: ".o_list_view:not(:has(.o_data_row:contains(Tour Later Task)))",
        },
        {
            trigger: ".o_project_task_touch_search",
            run: "clear",
        },
        {
            trigger: ".o_list_view .o_data_row:contains(Tour Later Task)",
        },
        {
            content: "Back to the kanban",
            trigger: ".o_project_task_touch_view_kanban",
            run: "click",
        },
        {
            trigger: ".o_kanban_view .o_kanban_record:contains(Tour Existing Task)",
        },
        {
            content: "Its subtasks, inside it, not as tasks of their own",
            trigger: ".o_kanban_view:not(:has(.o_kanban_record .o_kanban_record_title:contains(Tour Subtask), .o_kanban_record [name=name]:contains(Tour Subtask)))",
        },
        {
            content: "The empty states too, to drag the tasks to them",
            trigger: ".o_kanban_group .o_column_title:contains(Waiting)",
        },
        {
            content: "A new file from the template",
            trigger: ".o_project_task_touch_new_project",
            run: "click",
        },
        {
            trigger: ".o_project_task_touch_parent_choice:contains(Tour Template)",
            run: "click",
        },
        {
            trigger: ".o_project_task_touch_new_name",
            run: "edit Tour File",
        },
        {
            trigger: ".o_project_task_touch_create",
            run: "click",
        },
        {
            content: "Shown alone, with the tasks of the template",
            trigger: ".o_project_task_touch_project option:selected:contains(Tour File):not(:visible)",
        },
        {
            trigger: ".o_kanban_record:contains(Tour Template Step)",
        },
        {
            trigger: ".o_kanban_view:not(:has(.o_kanban_record:contains(Tour Existing Task)))",
        },
        {
            content: "A new task of the project filtered",
            trigger: ".o_project_task_touch_new_task",
            run: "click",
        },
        {
            trigger: ".o_project_task_touch_parent:contains(Tour File)",
        },
        {
            trigger: ".o_project_task_touch_new_name",
            run: "edit Tour New Task",
        },
        {
            trigger: ".o_project_task_touch_create",
            run: "click",
        },
        {
            trigger: ".o_kanban_group:has(.o_column_title:contains(In Progress)) .o_kanban_record:contains(Tour New Task)",
        },
        {
            content: "Its state changed on its card: to its column at once",
            trigger: ".o_kanban_record:contains(Tour New Task) .o_field_project_task_state_selection button",
            run: "click",
        },
        {
            trigger: ".project_task_state_selection_menu span.text-success:contains(Approved)",
            run: "click",
        },
        {
            trigger: ".o_kanban_group:has(.o_column_title:contains(Approved)) .o_kanban_record:contains(Tour New Task)",
        },
        {
            content: "Dragged to another state",
            trigger: ".o_kanban_record:contains(Tour New Task)",
            async run({ drag_and_drop }) {
                await drag_and_drop(".o_kanban_group:has(.o_column_title:contains(Waiting))", { position: "center" });
            },
        },
        {
            trigger: ".o_kanban_group:has(.o_column_title:contains(Waiting)) .o_kanban_record:contains(Tour New Task)",
        },
        {
            content: "The projects without template, searched by the project",
            trigger: ".o_project_task_touch_template",
            run: "select none",
        },
        {
            trigger: ".o_project_task_touch_project option:selected:contains(All projects):not(:visible)",
        },
        {
            trigger: ".o_project_task_touch_search",
            run: "edit Tour Project",
        },
        {
            trigger: ".o_kanban_view:not(:has(.o_kanban_record:contains(Tour New Task)))",
        },
        {
            trigger: ".o_kanban_record:contains(Tour Existing Task)",
        },
        {
            content: "Filtered as it is written: the task of the other project is hidden",
            trigger: ".o_project_task_touch_search",
            run: "edit Tour Existing",
        },
        {
            trigger: ".o_kanban_view:not(:has(.o_kanban_record:contains(Tour Other Task)))",
        },
        {
            trigger: ".o_project_task_touch_search",
            run: "clear",
        },
        {
            trigger: ".o_kanban_record:contains(Tour Other Task)",
        },
        {
            content: "The activities",
            trigger: ".o_project_task_touch_mode_activities",
            run: "click",
        },
        {
            trigger: ".o_project_task_touch_column_overdue",
        },
        {
            content: "The activity itself, in the form of the chatter",
            trigger: ".o_project_task_touch_activity:contains(Tour Call) .o_project_task_touch_activity_edit",
            run: "click",
        },
        {
            content: "Its box to show it here, with its label",
            trigger: ".modal .o_project_task_touch_activity_touch_ok:has(.o_field_widget[name=touch_ok] input:checked) label:contains(Show in Deadlines)",
        },
        {
            trigger: ".modal .o_field_widget[name=summary] input",
            run: "edit Tour Call Edited",
        },
        {
            trigger: ".modal .modal-footer button[name=action_close_dialog]:visible",
            run: "click",
        },
        {
            trigger: "body:not(:has(.modal)) .o_project_task_touch_activity_name:contains(Tour Call Edited)",
        },
        {
            content: "Done with the popover of the chatter: its feedback",
            trigger: ".o_project_task_touch_activity:contains(Tour Call) .o_project_task_touch_activity_done",
            run: "click",
        },
        {
            trigger: ".o-mail-ActivityMarkAsDone textarea",
            run: "edit Tour feedback",
        },
        {
            trigger: ".o-mail-ActivityMarkAsDone button[aria-label=Done]",
            run: "click",
        },
        {
            trigger: ".o_project_task_touch_columns:not(:has(.o_project_task_touch_activity:contains(Tour Call)))",
        },
        {
            content: "Among the closed ones, with its feedback",
            trigger: ".o_project_task_touch_closed",
            run: "click",
        },
        {
            trigger: ".o_project_task_touch_column_done .o_project_task_touch_activity:contains(Tour Call) .o_project_task_touch_activity_feedback:contains(Tour feedback)",
        },
        {
            content: "The closed tasks, the last closed first",
            trigger: ".o_project_task_touch_mode_tasks",
            run: "click",
        },
        {
            trigger: ".o_kanban_record:contains(Tour First Closed), .o_data_row:contains(Tour First Closed)",
            run() {
                const names = [...document.querySelectorAll(".o_kanban_record, .o_data_row")]
                    .map((record) => record.textContent)
                    .map((text) => ["Tour Last Closed", "Tour First Closed"].find((name) => text.includes(name)))
                    .filter(Boolean);
                if (JSON.stringify(names) !== JSON.stringify(["Tour Last Closed", "Tour First Closed"])) {
                    throw new Error(`Wrong order of the closed tasks: ${names.join(", ")}`);
                }
            },
        },
    ],
});
