import { Component, onPatched, onWillStart, onWillUnmount, proxy, signal, useListener, useProps } from "@odoo/owl";
import { ActivityMarkAsDone } from "@mail/core/web/activity_markasdone_popover";
import { browser } from "@web/core/browser/browser";
import { isDisplayStandalone } from "@web/core/browser/feature_detection";
import { _t } from "@web/core/l10n/translation";
import { deserializeDate, formatDate, serializeDate } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { usePopover } from "@web/core/popover/popover_hook";
import { useService } from "@web/core/utils/hooks";
import { View } from "@web/views/view";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const MODEL = "project.task.touch";
// Order of the tasks in the columns of the kanban
const KANBAN_ORDER = [
    { name: "date_deadline", asc: true },
    { name: "priority", asc: false },
];
// The views of the tasks, as in the switcher of Odoo
const TASK_VIEWS = ["kanban", "list"];
// The view chosen, kept on this device
const VIEW_KEY = "project_task_touch.view";
// Time to wait after typing before searching
const SEARCH_DELAY = 300;

/**
 * Files (Expedientes), on a touch screen as the one of CAT (scrap_touch).
 *
 * Two options, as big buttons with how many there are: the tasks of the projects marked to be
 * shown, in the kanban of the tasks grouped by state (its tags, subtasks, drag and drop...), and
 * the activities marked to be shown,
 * in columns by their state (overdue, today, planned).
 * The tasks are filtered by the template the project was created from, then by project, and a
 * single search box looks up the task, its project and the people assigned.
 *
 * Two buttons create: a new task (a project, then its name and deadline) and a new file (a
 * project created from a template, then its name and start date).
 */
export class ProjectTaskTouch extends Component {
    static template = "project_task_touch.TouchScreen";
    static components = { View };
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.pwa = useService("pwa");
        this.homeMenu = "home_menu" in this.env.services ? useService("home_menu") : null;
        this.store = useService("mail.store");
        // Done as in the chatter: its feedback, then done or done and the next one scheduled
        this.markDonePopover = usePopover(ActivityMarkAsDone, { position: "bottom" });
        this.state = proxy({
            data: null,
            // "tasks" or "activities"
            mode: "tasks",
            query: "",
            // false (all), "none" (projects not created from a template) or the id of a template
            templateId: false,
            projectId: false,
            // The tasks closed (done or cancelled) instead of the open ones
            closed: false,
            // "kanban" or "list": the view of the tasks
            viewType: this.getSavedView(),
            // Changed with the props of the kanban, to show them
            kanbanVersion: 0,
            activities: [],
            counts: { tasks: 0, activities: 0 },
            loading: false,
            sending: false,
            // Something being created: { kind: "task" | "project", parent, name, date }, its
            // parent (the project of the task, the template of the file) chosen first
            creating: null,
        });
        this.searchTimeout = null;
        this.focusName = false;
        // Props of the kanban of the tasks: replaced only when they change, as the kanban is
        // loaded again with each new value
        this.kanbanProps = null;
        this.kanbanReloads = 0;
        onPatched(() => {
            if (this.focusName) {
                this.focusName = false;
                document.querySelector(".o_project_task_touch_new_name")?.focus();
            }
        });
        onWillStart(async () => {
            this.state.data = await this.orm.call(MODEL, "get_screen_data", []);
            await this.load();
        });
        useListener(window, "keydown", (ev) => this.onKeydown(ev), { capture: true });
        onWillUnmount(() => browser.clearTimeout(this.searchTimeout));
    }

    get modes() {
        return [
            { key: "tasks", name: _t("Tasks"), icon: "checklist" },
            { key: "activities", name: _t("Activities"), icon: "event" },
        ];
    }

    get searchPlaceholder() {
        return this.state.mode === "tasks"
            ? _t("Task, project, customer, tag or person assigned")
            : _t("Activity, document or person assigned");
    }

    // ------------------------------------------------------------------
    // Loading
    // ------------------------------------------------------------------

    async load() {
        const { mode, query, templateId, projectId, closed } = this.state;
        this.state.loading = true;
        try {
            const result = mode === "tasks"
                ? await this.orm.call(MODEL, "get_tasks", [query, templateId, projectId, closed])
                : await this.orm.call(MODEL, "get_activities", [query, templateId, projectId, closed]);
            // A later search may have answered first
            if (mode === this.state.mode && query === this.state.query && templateId === this.state.templateId
                && projectId === this.state.projectId && closed === this.state.closed) {
                if (mode === "tasks") {
                    this.setKanbanProps(result.domain, result.states);
                } else {
                    this.state.activities = result.activities;
                }
                this.state.counts = result.counts;
            }
        } finally {
            this.state.loading = false;
        }
    }

    async onMode(mode) {
        this.state.mode = mode;
        await this.load();
    }

    onSearchInput(ev) {
        this.state.query = ev.target.value;
        browser.clearTimeout(this.searchTimeout);
        this.searchTimeout = browser.setTimeout(() => this.load(), SEARCH_DELAY);
    }

    /** First the template, then a project of it. */
    async onTemplate(ev) {
        const value = ev.target.value;
        this.state.templateId = value === "none" ? "none" : parseInt(value) || false;
        if (this.state.projectId && !this.projects.some((project) => project.id === this.state.projectId)) {
            this.state.projectId = false;
        }
        await this.load();
    }

    async onProject(ev) {
        this.state.projectId = parseInt(ev.target.value) || false;
        await this.load();
    }

    async onToggleClosed() {
        this.state.closed = !this.state.closed;
        await this.load();
    }

    /** The projects of the template chosen. */
    get projects() {
        const { templateId } = this.state;
        const projects = this.state.data.projects;
        if (templateId === "none") {
            return projects.filter((project) => !project.template_id);
        }
        return templateId ? projects.filter((project) => project.template_id === templateId) : projects;
    }

    // ------------------------------------------------------------------
    // Tasks: the kanban of the tasks, by state
    // ------------------------------------------------------------------

    get taskViews() {
        return [
            { type: "kanban", name: _t("Kanban"), icon: "oi_view-kanban" },
            { type: "list", name: _t("List"), icon: "reorder" },
        ];
    }

    getSavedView() {
        try {
            const view = browser.localStorage.getItem(VIEW_KEY);
            return TASK_VIEWS.includes(view) ? view : "kanban";
        } catch {
            return "kanban";
        }
    }

    onTaskView(viewType) {
        if (viewType === this.state.viewType) {
            return;
        }
        this.state.viewType = viewType;
        try {
            browser.localStorage.setItem(VIEW_KEY, viewType);
        } catch {
            // Not kept: the kanban next time
        }
        this.setKanbanProps(this.kanbanProps.domain, this.kanbanProps.context.touch_states);
    }

    /** The props of the view of the tasks: the kanban by state or the list. */
    setKanbanProps(domain, states) {
        const isKanban = this.state.viewType === "kanban";
        this.kanbanProps = {
            resModel: "project.task",
            type: this.state.viewType,
            views: [
                [isKanban ? this.state.data.kanban_view_id : this.state.data.list_view_id, this.state.viewType],
                [false, "search"],
            ],
            domain,
            groupBy: isKanban ? ["state"] : [],
            // The nearest deadline first (the ones without one, last), then the highest priority
            orderBy: KANBAN_ORDER,
            // touch_states: the columns shown even if empty (see project.task); touch_reload, to
            // load it again after a change in a dialog
            context: { touch_states: states, touch_reload: this.kanbanReloads },
            display: { controlPanel: false },
            selectRecord: (resId) => this.onOpenTask(resId),
            ...(isKanban ? {} : { allowSelectors: false }),
        };
        this.state.kanbanVersion++;
    }

    /** The task, in a dialog over the screen. */
    onOpenTask(resId) {
        this.dialog.add(FormViewDialog, {
            resModel: "project.task",
            resId,
        }, {
            onClose: () => {
                this.kanbanReloads++;
                this.load();
            },
        });
    }

    /** Its deadline as the one of the tasks: red when late, yellow today. */
    activityDeadlineClass(activity) {
        return { overdue: "text-bg-danger", today: "text-bg-warning" }[activity.state] || "text-bg-light";
    }

    activityStateClass(state) {
        return { overdue: "text-bg-danger", today: "text-bg-warning", planned: "text-bg-success" }[state];
    }

    get activityColumns() {
        if (this.state.closed) {
            return [{ key: "done", name: _t("Done"), activities: this.state.activities }];
        }
        return this.state.data.activity_states.map((state) => ({
            ...state,
            activities: this.state.activities.filter((activity) => activity.state === state.key),
        }));
    }

    // ------------------------------------------------------------------
    // Activities
    // ------------------------------------------------------------------

    onOpenActivityRecord(activity) {
        this.dialog.add(FormViewDialog, {
            title: activity.res_name,
            resModel: activity.res_model,
            resId: activity.res_id,
            onRecordSaved: () => this.load(),
        }, { onClose: () => this.load() });
    }

    /** The popover of the chatter to mark it done: its feedback, and done or done and the next
     * one scheduled with the standard wizard. */
    onActivityDone(activity, ev) {
        if (this.markDonePopover.isOpen) {
            this.markDonePopover.close();
            return;
        }
        const record = this.store["mail.activity"].insert({
            id: activity.id,
            res_id: activity.res_id,
            res_model: activity.res_model,
            feedback: "",
        });
        this.markDonePopover.open(ev.currentTarget, {
            activity: signal(record),
            hasHeader: true,
            onActivityChanged: () => this.load(),
        });
    }

    // ------------------------------------------------------------------
    // New task and new file
    // ------------------------------------------------------------------

    /** A new task: of the project filtered, or of one to choose. */
    onNewTask() {
        const project = this.state.data.projects.find((project) => project.id === this.state.projectId);
        this.startCreating("task", project || null);
    }

    /** A new file: from the template filtered, or from one to choose. */
    onNewProject() {
        const template = this.state.data.templates.find((template) => template.id === this.state.templateId);
        this.startCreating("project", template || null);
    }

    startCreating(kind, parent) {
        // A parent filtered is kept: back closes it all
        this.state.creating = { kind, parent, fixed: Boolean(parent), name: "", date: serializeDate(luxon.DateTime.local()) };
        this.focusName = Boolean(parent);
    }

    /** The parents to choose from: the projects (of the template filtered) or the templates. */
    get creatingParents() {
        return this.state.creating.kind === "task" ? this.projects : this.state.data.templates;
    }

    onChooseParent(parent) {
        this.state.creating.parent = parent;
        this.focusName = true;
    }

    onCreatingName(ev) {
        this.state.creating.name = ev.target.value;
    }

    onCreatingDate(ev) {
        this.state.creating.date = ev.target.value;
    }

    onCreatingKeydown(ev) {
        if (ev.key === "Enter") {
            this.onCreate();
        }
    }

    async onCreate() {
        const creating = this.state.creating;
        if (!creating.name.trim()) {
            this.notification.add(creating.kind === "task" ? _t("Write the name of the task.") : _t("Write the name of the file."), { type: "warning" });
            return;
        }
        const date = creating.date || false;
        if (creating.kind === "task") {
            const task = await this.run("create_task", [creating.parent.id, creating.name, date]);
            if (task) {
                this.notification.add(_t("Task %s created.", task.name), { type: "success" });
                this.state.mode = "tasks";
                this.state.closed = false;
                // Loaded before closing, so that the kanban is shown once, with its filters
                await this.load();
                this.state.creating = null;
            }
        } else {
            const project = await this.run("create_project", [creating.parent.id, creating.name, date]);
            if (project) {
                this.notification.add(_t("File %s created.", project.name), { type: "success" });
                // Shown alone, with its tasks copied from the template
                this.state.data.projects.push(project);
                this.state.data.projects.sort((a, b) => a.name.localeCompare(b.name));
                this.state.templateId = project.template_id;
                this.state.projectId = project.id;
                this.state.mode = "tasks";
                this.state.closed = false;
                this.state.query = "";
                await this.load();
                this.state.creating = null;
            }
        }
    }

    onCancelCreating() {
        if (this.state.creating.parent && !this.state.creating.fixed) {
            this.state.creating.parent = null;
        } else {
            this.state.creating = null;
        }
    }

    // ------------------------------------------------------------------
    // Others
    // ------------------------------------------------------------------

    onKeydown(ev) {
        if (ev.key === "Escape" && this.state.creating && !document.querySelector(".modal")) {
            ev.preventDefault();
            ev.stopImmediatePropagation();
            this.state.creating = null;
        }
    }

    async run(method, args) {
        if (this.state.sending) {
            return null;
        }
        this.state.sending = true;
        try {
            return await this.orm.call(MODEL, method, args);
        } finally {
            this.state.sending = false;
        }
    }

    onOdooHome() {
        if (this.homeMenu) {
            this.homeMenu.toggle(true);
        } else {
            browser.location.href = "/odoo";
        }
    }

    canInstall() {
        return this.pwa.isAvailable && !isDisplayStandalone();
    }

    onInstall() {
        this.pwa.show();
    }

    formatDay(value) {
        return value ? formatDate(deserializeDate(value)) : "";
    }
}

registry.category("actions").add("project_task_touch.screen", ProjectTaskTouch);
