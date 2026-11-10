import { Component, onPatched, onWillStart, onWillUnmount, proxy, useListener, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { isDisplayStandalone } from "@web/core/browser/feature_detection";
import { formatCurrency } from "@web/core/currency";
import { _t } from "@web/core/l10n/translation";
import { deserializeDate, deserializeDateTime, formatDate, formatDateTime, serializeDate } from "@web/core/l10n/dates";
import { normalize } from "@web/core/l10n/utils";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatFloat } from "@web/core/utils/numbers";
import { imageUrl } from "@web/core/utils/urls";
import { parseFloat } from "@web/views/fields/parsers";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { applyNumpadKey, TouchNumpad } from "./touch_numpad";

const MODEL = "scrap.touch";
// Time to wait after typing before searching suppliers or drafts
const SEARCH_DELAY = 300;

/** A random uuid (version 4); crypto.randomUUID() needs HTTPS, the screen may use plain HTTP. */
function randomUuid() {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/**
 * Screen of the vehicle recycling, made for touch screens.
 *
 * One mode per task, also opened with its function key: F1 is the scrap entry and F2 the
 * purchase/sale entry, of the vehicles to repair and sell whole. Both work the same way: the
 * vehicles of a supplier, added as lines with their license plate (their serial number, as the
 * chassis isn't known before receiving them), then bought and received at once.
 * The purchase being made is saved as a request for quotation in draft after each change, so
 * that it can be resumed later, on this screen, on another one or in the backend.
 *
 * F3 (decontamination), F4 (dismantling) and F5 (vehicles) work as the lists of purchases: a
 * list of vehicles, with a search and filters, and the summary of each one, where it is marked
 * as decontaminated or dismantled.
 */
export class TouchScreen extends Component {
    static template = "scrap_touch.TouchScreen";
    static components = { TouchNumpad };
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.pwa = useService("pwa");
        // The home menu of Odoo Enterprise; Community has none
        this.homeMenu = "home_menu" in this.env.services ? useService("home_menu") : null;
        this.modes = [
            {
                key: "entry",
                fkey: "F1",
                name: _t("Scrap entry"),
                icon: "local_shipping",
                help: _t("Buy and receive the vehicles to dismantle"),
                // Kind of entry of its purchases (unbuild_type)
                unbuildType: "main",
            },
            {
                key: "resale",
                fkey: "F2",
                name: _t("Purchase/Sale entry"),
                icon: "storefront",
                help: _t("Buy and receive the vehicles to repair and sell whole"),
                unbuildType: "refurbish",
            },
            {
                key: "decontamination",
                fkey: "F3",
                name: _t("Decontamination"),
                icon: "colorize",
                help: _t("The vehicles to decontaminate, the nearest legal limit first"),
                // A list of vehicles, of a stage of their legal deadlines (see scrap_base)
                stage: "decontamination",
            },
            {
                key: "dismantling",
                fkey: "F4",
                name: _t("Dismantling"),
                icon: "build",
                help: _t("The vehicles decontaminated to dismantle, the nearest legal limit first"),
                stage: "scrap",
            },
            {
                key: "vehicles",
                fkey: "F5",
                name: _t("Vehicles"),
                icon: "inventory_2",
                help: _t("Look up the vehicles bought, their deadlines and their location"),
                stage: "vehicles",
            },
        ];
        this.state = proxy({
            // false (main menu) or the key of a mode
            mode: false,
            data: null,
            sending: false,
            // Purchases to resume (in draft) or to look up
            drafts: [],
            draftSearch: "",
            // "draft" (in progress), "to_receive", "to_invoice" or "all"
            draftFilter: "draft",
            // A new purchase: its supplier is being chosen
            choosingPartner: false,
            // Supplier of the purchase
            partnerSearch: "",
            partners: [],
            partner: null,
            // Draft of the purchase being made, saved after each change: { id, name }
            order: null,
            // false, "saving", "saved" or "error"
            saveState: false,
            // Catalog
            categoryId: false,
            productSearch: "",
            // Line being added or changed: { product, price, lotName, line }
            entry: null,
            // Lines of the purchase: { key, lineId, product, price, lotName }
            lines: [],
            // Result of the last operation, shown until the next one starts
            done: null,
            // Vehicles of the modes of a stage, as the purchases
            vehicles: [],
            vehicleSearch: "",
            vehicleFilter: "pending",
            // Summary of the vehicle opened from the list
            vehicle: null,
            // Date to mark a stage done on another day than today
            markDate: "",
            // Dismantling of the vehicle opened: its components still to dismantle and the
            // parts marked (see get_dismantle)
            dismantle: null,
            // Component being marked: { line, quantity, result, condition, location }
            part: null,
            // The destination of the part is being chosen
            choosingLocation: false,
            locationSearch: "",
            locations: [],
        });
        this.searchTimeout = null;
        this.nextLineKey = 1;
        // Identifier of the purchase, sent with each save: the first one creates the draft
        this.orderUuid = null;
        // Saves of the draft, one after the other; a new purchase starts a new token, so that
        // a late answer doesn't change it
        this.saveToken = {};
        this.saveDirty = false;
        this.savePromise = null;
        // The license plate is typed as soon as the line opens
        this.focusLotName = false;
        this.focusWasteQuantity = false;
        onPatched(() => {
            if (this.focusLotName) {
                this.focusLotName = false;
                document.querySelector(".o_scrap_touch_lot_name")?.focus();
            }
            if (this.focusWasteQuantity) {
                this.focusWasteQuantity = false;
                document.querySelector(".o_scrap_touch_waste_quantity")?.focus();
            }
        });

        onWillStart(async () => {
            this.state.data = await this.orm.call(MODEL, "get_screen_data", []);
        });

        // The function keys open the modes, Escape goes back
        useListener(window, "keydown", (ev) => this.onKeydown(ev), { capture: true });
        onWillUnmount(() => browser.clearTimeout(this.searchTimeout));
    }

    // ------------------------------------------------------------------
    // Navigation
    // ------------------------------------------------------------------

    /** The modes the user can use: the purchases, for the purchase users, and the stages and
     * the vehicles, for the inventory users. */
    get visibleModes() {
        const data = this.state.data;
        return this.modes.filter((mode) => (mode.stage ? data.can_cat : data.can_purchase));
    }

    onKeydown(ev) {
        const mode = this.visibleModes.find((mode) => mode.fkey === ev.key);
        if (mode) {
            ev.preventDefault();
            ev.stopImmediatePropagation();
            this.openMode(mode.key);
        } else if (ev.key === "Escape" && this.state.mode && !document.querySelector(".modal")) {
            ev.preventDefault();
            ev.stopImmediatePropagation();
            this.onBack();
        }
    }

    async openMode(mode) {
        if (this.state.sending) {
            return;
        }
        await this.flushSave();
        this.resetOperation();
        this.state.partner = null;
        this.state.vehicle = null;
        this.closeDismantle();
        this.state.mode = mode;
        if (this.currentMode.stage) {
            this.state.vehicleSearch = "";
            this.state.vehicleFilter = this.currentMode.stage === "vehicles" ? "in_stock" : "pending";
            this.state.vehicles = [];
            await this.loadVehicles();
        } else {
            // "On sale" is only of the purchase/sale entry
            if (this.state.draftFilter === "on_sale" && this.currentMode.unbuildType !== "refurbish") {
                this.state.draftFilter = "draft";
            }
            this.state.vehicles = [];
            await this.loadDrafts();
        }
    }

    resetOperation() {
        this.state.entry = null;
        this.state.lines = [];
        this.state.done = null;
        this.state.order = null;
        this.state.saveState = false;
        this.state.choosingPartner = false;
        this.state.categoryId = false;
        this.state.productSearch = "";
        this.orderUuid = null;
        this.saveToken = {};
        this.saveDirty = false;
        this.savePromise = null;
    }

    async onBack() {
        if (this.state.sending) {
            return;
        }
        if (this.state.choosingLocation) {
            this.state.choosingLocation = false;
        } else if (this.state.part) {
            this.state.part = null;
        } else if (this.state.dismantle) {
            await this.onCloseDismantle();
        } else if (this.state.vehicle) {
            await this.onBackToVehicles();
        } else if (this.state.entry) {
            this.state.entry = null;
        } else if (this.state.partner || this.state.choosingPartner) {
            // The draft is saved: back to the list, to resume it or another one later
            await this.flushSave();
            this.resetOperation();
            this.state.partner = null;
            await this.loadDrafts();
        } else {
            this.state.mode = false;
            await this.refreshCatCounts();
        }
    }

    /** The vehicles pending and late of each stage, in the main menu. */
    async refreshCatCounts() {
        if (this.state.data.can_cat) {
            this.state.data.cat_counts = await this.orm.call(MODEL, "get_cat_counts", []);
        }
    }

    catCounts(mode) {
        return mode.stage && this.state.data.cat_counts?.[mode.stage];
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

    get currentMode() {
        return this.modes.find((mode) => mode.key === this.state.mode);
    }

    // ------------------------------------------------------------------
    // Drafts
    // ------------------------------------------------------------------

    onDraftSearchInput(ev) {
        this.state.draftSearch = ev.target.value;
        browser.clearTimeout(this.searchTimeout);
        this.searchTimeout = browser.setTimeout(() => this.loadDrafts(), SEARCH_DELAY);
    }

    get draftFilters() {
        return [
            { key: "draft", name: _t("In progress") },
            { key: "to_receive", name: _t("To receive") },
            { key: "to_invoice", name: _t("To invoice") },
            { key: "all", name: _t("All") },
            // The vehicles to repair and sell in stock, in their own color
            ...(this.currentMode.unbuildType === "refurbish" ? [{ key: "on_sale", name: _t("On sale"), color: "info" }] : []),
        ];
    }

    /** The class of a filter button: of its color, if it has one. */
    filterClass(filter, active) {
        if (filter.key === active) {
            return `btn-${filter.color || "primary"}`;
        }
        return filter.color ? `btn-outline-${filter.color}` : "btn-secondary";
    }

    async onDraftFilter(filter) {
        this.state.draftFilter = filter;
        await this.loadDrafts();
    }

    async loadDrafts() {
        const mode = this.state.mode;
        if (this.state.draftFilter === "on_sale") {
            const vehicles = await this.orm.call(MODEL, "get_vehicles", [this.state.draftSearch, "on_sale", "vehicles"]);
            if (this.state.mode === mode && !this.state.vehicle && this.state.draftFilter === "on_sale") {
                this.state.vehicles = vehicles;
            }
            return;
        }
        const drafts = await this.orm.call(MODEL, "get_drafts", [
            this.state.draftSearch,
            this.state.draftFilter,
            this.currentMode.unbuildType,
        ]);
        if (this.state.mode === mode && !this.state.partner && !this.state.choosingPartner) {
            this.state.drafts = drafts;
        }
    }

    async onNewDraft() {
        this.resetOperation();
        this.state.choosingPartner = true;
        this.state.partnerSearch = "";
        this.state.partners = [];
        await this.searchPartners();
    }

    async onResumeDraft(draft) {
        if (draft.state !== "draft") {
            await this.openOrderSummary(draft.id);
            return;
        }
        const data = await this.orm.call(MODEL, "get_draft", [draft.id]);
        this.resetOperation();
        this.state.partner = data.partner;
        this.state.order = { id: data.id, name: data.name };
        this.state.saveState = "saved";
        this.state.lines = data.lines.map((line) => ({
            key: this.nextLineKey++,
            lineId: line.line_id,
            product: line.product,
            price: line.price,
            lotName: line.lot_name,
        }));
    }

    onCancelDraft() {
        const order = this.state.order;
        this.dialog.add(ConfirmationDialog, {
            title: _t("Cancel the purchase"),
            body: _t("%s will be cancelled.", order.name),
            confirmLabel: _t("Cancel the purchase"),
            cancelLabel: _t("Keep it"),
            confirm: async () => {
                await this.flushSave();
                await this.orm.call(MODEL, "cancel_draft", [order.id]);
                this.resetOperation();
                this.state.partner = null;
                await this.loadDrafts();
            },
            cancel: () => {},
        });
    }

    /** The lines of the purchase, as the server saves them in the draft. */
    linesPayload(lines) {
        return lines.map((line) => ({
            ...(line.lineId ? { line_id: line.lineId } : {}),
            product_id: line.product.id,
            price_unit: line.price,
            lot_name: line.lotName,
        }));
    }

    purchaseVals(lines) {
        if (!this.orderUuid) {
            this.orderUuid = randomUuid();
        }
        return {
            uuid: this.orderUuid,
            partner_id: this.state.partner.id,
            unbuild_type: this.currentMode.unbuildType,
            ...(this.state.order ? { order_id: this.state.order.id } : {}),
            lines: this.linesPayload(lines),
        };
    }

    /** Save the draft after a change of the lines, in the background. */
    scheduleSave() {
        if (!this.state.partner || this.state.done) {
            return;
        }
        this.saveDirty = true;
        if (!this.savePromise) {
            const token = this.saveToken;
            this.savePromise = this.runSaves(token).finally(() => {
                if (token === this.saveToken) {
                    this.savePromise = null;
                }
            });
        }
    }

    async runSaves(token) {
        while (this.saveDirty && token === this.saveToken) {
            this.saveDirty = false;
            await this.saveDraft(token);
        }
    }

    async saveDraft(token) {
        const lines = [...this.state.lines];
        this.state.saveState = "saving";
        let result;
        try {
            result = await this.orm.silent.call(MODEL, "save_draft", [this.purchaseVals(lines)]);
        } catch (error) {
            if (token === this.saveToken) {
                this.state.saveState = "error";
                this.notification.add(error.data?.message || _t("The changes couldn't be saved."), {
                    title: _t("Not saved"),
                    type: "danger",
                });
            }
            return;
        }
        if (token !== this.saveToken) {
            return;
        }
        this.state.order = { id: result.id, name: result.name };
        lines.forEach((line, index) => {
            line.lineId = result.line_ids[index];
        });
        this.state.saveState = this.saveDirty ? "saving" : "saved";
    }

    /** Wait for the saves in progress. */
    async flushSave() {
        while (this.savePromise) {
            await this.savePromise;
        }
    }

    // ------------------------------------------------------------------
    // Suppliers
    // ------------------------------------------------------------------

    onPartnerSearchInput(ev) {
        this.state.partnerSearch = ev.target.value;
        browser.clearTimeout(this.searchTimeout);
        this.searchTimeout = browser.setTimeout(() => this.searchPartners(), SEARCH_DELAY);
    }

    async searchPartners() {
        const partners = await this.orm.call(MODEL, "search_partners", [this.state.partnerSearch]);
        if (this.state.choosingPartner) {
            this.state.partners = partners;
        }
    }

    onSelectPartner(partner) {
        this.resetOperation();
        this.state.partner = partner;
    }

    /** A new supplier, in a short form; once saved, the purchase goes on with it. */
    onNewPartner() {
        const name = this.state.partnerSearch.trim();
        this.dialog.add(FormViewDialog, {
            title: _t("New supplier"),
            resModel: "res.partner",
            viewId: this.state.data.partner_view_id,
            context: name ? { default_name: name } : {},
            canExpand: false,
            onRecordSaved: (record) => {
                this.onSelectPartner({
                    id: record.resId,
                    name: record.data.name,
                    city: record.data.city || "",
                    vat: record.data.vat || "",
                });
            },
        });
    }

    // ------------------------------------------------------------------
    // Products
    // ------------------------------------------------------------------

    categories() {
        return this.state.data.categories;
    }

    visibleProducts() {
        const search = normalize(this.state.productSearch.trim());
        return this.state.data.products.filter(
            (product) =>
                (!this.state.categoryId || product.categ_id === this.state.categoryId) &&
                (!search ||
                    normalize(product.name).includes(search) ||
                    normalize(product.default_code).includes(search))
        );
    }

    productImage(product) {
        return imageUrl("product.product", product.id, "image_128", { unique: product.image_unique });
    }

    onSelectCategory(categoryId) {
        this.state.categoryId = categoryId;
        this.state.productSearch = "";
    }

    onProductSearchInput(ev) {
        this.state.productSearch = ev.target.value;
    }

    onSelectProduct(product) {
        this.openEntry(product);
    }

    // ------------------------------------------------------------------
    // Line being added or changed
    // ------------------------------------------------------------------

    /** Open the line editor: for a new vehicle of `product`, or to change `line`. */
    openEntry(product, line = null) {
        this.state.entry = {
            product,
            price: line ? this.formatInput(line.price) : "",
            lotName: line ? line.lotName : "",
            line,
        };
        this.focusLotName = !line;
    }

    onLotNameInput(ev) {
        // License plates are written in capitals
        const { selectionStart, selectionEnd } = ev.target;
        ev.target.value = ev.target.value.toUpperCase();
        ev.target.setSelectionRange(selectionStart, selectionEnd);
        this.state.entry.lotName = ev.target.value;
    }

    onPriceInput(ev) {
        this.state.entry.price = ev.target.value;
    }

    onNumpadKey(key) {
        const entry = this.state.entry;
        if (entry) {
            entry.price = applyNumpadKey(entry.price, key);
        }
    }

    parseNumber(value) {
        try {
            return parseFloat(String(value || "").trim() || "0");
        } catch {
            return NaN;
        }
    }

    /** Check the line being edited; return its values, or warn and return null. */
    checkEntry() {
        const entry = this.state.entry;
        const warn = (message) => {
            this.notification.add(message, { type: "warning" });
            return null;
        };
        // Without spaces nor hyphens, as the server saves it: "1234 ABC" is "1234ABC"
        const lotName = entry.lotName.replace(/[\s-]+/g, "").toUpperCase();
        if (!lotName) {
            return warn(_t("Enter the license plate."));
        }
        if (
            this.state.lines.some(
                (line) =>
                    line !== entry.line &&
                    line.product.id === entry.product.id &&
                    line.lotName === lotName
            )
        ) {
            return warn(_t("The license plate %s is already in the purchase.", lotName));
        }
        if (!String(entry.price).trim()) {
            return warn(_t("Enter the price (0 if it is free)."));
        }
        const price = this.parseNumber(entry.price);
        if (!Number.isFinite(price) || price < 0) {
            return warn(_t("Enter a price of 0 or more."));
        }
        return { price, lotName };
    }

    /** Add the line being edited to the purchase, or change the line it comes from. */
    onAddEntry() {
        const entry = this.state.entry;
        const values = this.checkEntry();
        if (!values) {
            return;
        }
        if (entry.line) {
            Object.assign(entry.line, values);
        } else {
            this.state.lines.push({ key: this.nextLineKey++, lineId: false, product: entry.product, ...values });
        }
        this.state.entry = null;
        this.scheduleSave();
    }

    // ------------------------------------------------------------------
    // Lines of the purchase
    // ------------------------------------------------------------------

    onEditLine(line) {
        if (!this.state.sending) {
            this.openEntry(line.product, line);
        }
    }

    onRemoveLine(line) {
        if (this.state.sending) {
            return;
        }
        this.state.lines = this.state.lines.filter((other) => other !== line);
        if (this.state.entry?.line === line) {
            this.state.entry = null;
        }
        this.scheduleSave();
    }

    linesTotal() {
        return this.state.lines.reduce((total, line) => total + line.price, 0);
    }

    /**
     * Buy the vehicles of the purchase; with `receive`, receive them too. Without it, the
     * receipt waits for the vehicles, with their license plates already set.
     */
    async onPurchase(receive) {
        if (!this.state.lines.length || this.state.entry || this.state.sending) {
            return;
        }
        this.state.sending = true;
        try {
            // The saves in progress first: the last one sends the same lines
            await this.flushSave();
            const done = await this.orm.call(MODEL, "purchase_entry", [
                this.purchaseVals(this.state.lines),
                receive,
            ]);
            const partner = this.state.partner;
            this.resetOperation();
            this.state.partner = partner;
            this.state.done = done;
        } finally {
            this.state.sending = false;
        }
    }

    // ------------------------------------------------------------------
    // Result, and confirmed purchases: receipt and bill
    // ------------------------------------------------------------------

    /** A confirmed purchase, to look it up, receive it or invoice it. */
    async openOrderSummary(orderId) {
        const summary = await this.orm.call(MODEL, "get_order_summary", [orderId]);
        this.resetOperation();
        this.state.partner = summary.partner_data;
        this.state.done = { ...summary, reviewing: true };
    }

    async refreshOrderSummary() {
        const done = this.state.done;
        if (!done) {
            return;
        }
        const summary = await this.orm.call(MODEL, "get_order_summary", [done.id]);
        if (this.state.done === done) {
            Object.assign(done, summary);
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

    /** Receive the vehicles of the purchase, with their license plates. */
    async onReceive() {
        const done = this.state.done;
        const summary = await this.run("receive_order", [done.id]);
        if (summary && this.state.done === done) {
            Object.assign(done, summary);
            this.notification.add(_t("%s received.", done.name), { type: "success" });
        }
    }

    /** The bill of the purchase, in draft, to review it in a dialog. */
    async onInvoice() {
        const action = await this.run("invoice_order", [this.state.done.id]);
        if (action) {
            await this.action.doAction(action, { onClose: () => this.refreshOrderSummary() });
        }
    }

    async onOpenBill(bill) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "account.move",
            res_id: bill.id,
            views: [[false, "form"]],
            target: "new",
        }, { onClose: () => this.refreshOrderSummary() });
    }

    async onBackToList() {
        this.resetOperation();
        this.state.partner = null;
        await this.loadDrafts();
    }

    async onOpenDocument() {
        const done = this.state.done;
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: done.model,
            res_id: done.id,
            views: [[false, "form"]],
            target: "new",
        }, { onClose: () => this.refreshOrderSummary() });
    }

    /** Another purchase of the same supplier. */
    onNewEntry() {
        const partner = this.state.partner;
        this.resetOperation();
        this.state.partner = partner;
    }

    // ------------------------------------------------------------------
    // Decontamination, dismantling and vehicles
    // ------------------------------------------------------------------

    get vehicleFilters() {
        if (this.currentMode.stage === "vehicles") {
            return [
                { key: "in_stock", name: _t("In stock") },
                { key: "main", name: _t("To dismantle") },
                { key: "refurbish", name: _t("Purchase/Sale") },
                { key: "all", name: _t("All") },
            ];
        }
        return [
            { key: "pending", name: _t("Pending") },
            { key: "late", name: _t("Late") },
            {
                key: "done",
                name: this.currentMode.stage === "scrap" ? _t("Dismantled") : _t("Decontaminated"),
            },
            { key: "all", name: _t("All") },
            // The subproducts to dismantle (as an engine), in their own color
            ...(this.currentMode.stage === "scrap" ? [{ key: "subproduct", name: _t("Subproducts"), color: "info" }] : []),
        ];
    }

    vehicleFilterClass(filter) {
        return this.filterClass(filter, this.state.vehicleFilter);
    }

    /** The stages marked on the summary of a vehicle: a subproduct is only dismantled. */
    vehicleStages(vehicle) {
        if (vehicle.is_subproduct) {
            return ["scrap"];
        }
        return vehicle.unbuild_type === "main" && vehicle.discharge_date ? ["decontamination", "scrap"] : [];
    }

    onVehicleSearchInput(ev) {
        this.state.vehicleSearch = ev.target.value;
        browser.clearTimeout(this.searchTimeout);
        this.searchTimeout = browser.setTimeout(() => this.loadVehicles(), SEARCH_DELAY);
    }

    async onVehicleFilter(filter) {
        this.state.vehicleFilter = filter;
        await this.loadVehicles();
    }

    async loadVehicles() {
        if (!this.currentMode.stage) {
            // The vehicles on sale of the purchase/sale entry
            return this.loadDrafts();
        }
        const mode = this.state.mode;
        const vehicles = await this.orm.call(MODEL, "get_vehicles", [
            this.state.vehicleSearch,
            this.state.vehicleFilter,
            this.currentMode.stage,
        ]);
        if (this.state.mode === mode && !this.state.vehicle) {
            this.state.vehicles = vehicles;
        }
    }

    async onOpenVehicle(vehicle) {
        const summary = await this.orm.call(MODEL, "get_vehicle", [vehicle.id]);
        this.state.markDate = serializeDate(luxon.DateTime.local());
        this.state.vehicle = summary;
    }

    async refreshVehicle() {
        const vehicle = this.state.vehicle;
        if (!vehicle) {
            return;
        }
        const summary = await this.orm.call(MODEL, "get_vehicle", [vehicle.id]);
        if (this.state.vehicle === vehicle) {
            Object.assign(vehicle, summary);
        }
    }

    async onBackToVehicles() {
        this.state.vehicle = null;
        this.closeDismantle();
        await this.loadVehicles();
    }

    // Dismantling: the operator marks the components of the bills of materials of the vehicle

    /** Whether the screen opened is the decontamination of the vehicle, or its dismantling. */
    get isDecontamination() {
        return this.state.dismantle?.stage === "decontamination";
    }

    /** The date of the stage of the screen opened: once set, nothing more is marked. */
    get dismantleDone() {
        const vehicle = this.state.vehicle;
        return this.isDecontamination ? vehicle.decontamination_date : vehicle.scrap_date;
    }

    /** The options of a part, in a single row: its condition, when it is dismantled, or the
     * other results. A waste of the decontamination is discarded or missing. */
    get partOptions() {
        if (this.isDecontamination) {
            return [
                { key: "discarded", name: _t("Discarded"), result: "discarded", condition: false, cls: "danger", icon: "delete" },
                { key: "missing", name: _t("Missing"), result: "missing", condition: false, cls: "warning", icon: "block" },
            ];
        }
        return [
            { key: "excellent", name: _t("Excellent"), result: "dismantled", condition: "excellent", cls: "success" },
            { key: "good", name: _t("Good"), result: "dismantled", condition: "good", cls: "success" },
            { key: "half_life", name: _t("Half Life"), result: "dismantled", condition: "half_life", cls: "success" },
            { key: "functional", name: _t("Functional"), result: "dismantled", condition: "functional", cls: "success" },
            { key: "missing", name: _t("Missing"), result: "missing", condition: false, cls: "warning", icon: "block" },
            { key: "discarded", name: _t("Discarded"), result: "discarded", condition: false, cls: "danger", icon: "delete" },
        ];
    }

    isPartOption(option, part = this.state.part) {
        return part.result === option.result && (part.condition || false) === option.condition;
    }

    /** The screen of the decontamination or of the dismantling (`stage`) of the vehicle. */
    async onOpenDismantle(stage = "scrap") {
        const vehicle = this.state.vehicle;
        const method = stage === "decontamination" ? "get_decontamination" : "get_dismantle";
        const data = await this.orm.call(MODEL, method, [vehicle.id]);
        if (this.state.vehicle === vehicle) {
            this.state.markDate = serializeDate(luxon.DateTime.local());
            this.applyDismantle(data);
        }
    }

    applyDismantle(data) {
        Object.assign(this.state.vehicle, data);
        this.state.dismantle = data;
        this.state.part = null;
        this.state.choosingLocation = false;
    }

    closeDismantle() {
        browser.clearTimeout(this.searchTimeout);
        this.state.dismantle = null;
        this.state.part = null;
        this.state.choosingLocation = false;
    }

    async onCloseDismantle() {
        this.closeDismantle();
        await this.refreshVehicle();
    }

    onSelectPart(line) {
        const dismantle = this.state.dismantle;
        this.state.choosingLocation = false;
        // A waste: its quantity is typed as soon as it is chosen
        this.focusWasteQuantity = this.isDecontamination;
        this.state.part = {
            line,
            // One by one; a fraction left, all of it
            quantity: Math.min(1, line.quantity),
            // A waste: as much as taken out, typed on the keypad
            quantityText: "",
            result: false,
            condition: false,
            location: { id: dismantle.location_id, name: dismantle.location_name },
        };
    }

    /** Correct a waste marked, in the same panel: its quantity, its result and its location. */
    onEditWaste(marked) {
        const dismantle = this.state.dismantle;
        this.focusWasteQuantity = true;
        this.state.choosingLocation = false;
        this.state.part = {
            line: { id: marked.product_id, product: marked.product, product_id: marked.product_id, uom: marked.uom },
            // The waste marked being corrected
            marked,
            quantity: marked.quantity,
            quantityText: this.formatInput(marked.quantity),
            result: marked.result,
            condition: false,
            location: marked.location_id
                ? { id: marked.location_id, name: marked.location }
                : { id: dismantle.location_id, name: dismantle.location_name },
        };
    }

    onPartQuantity(delta) {
        const part = this.state.part;
        part.quantity = Math.max(Math.min(part.quantity + delta, part.line.quantity), Math.min(1, part.line.quantity));
    }

    onPartOption(option) {
        this.state.part.result = option.result;
        this.state.part.condition = option.condition;
    }

    onWasteQuantityInput(ev) {
        this.state.part.quantityText = ev.target.value;
    }

    /** Enter confirms, once an option is chosen. */
    async onWasteQuantityKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            await this.onConfirmPart();
        }
    }

    onWasteNumpadKey(key) {
        this.state.part.quantityText = applyNumpadKey(this.state.part.quantityText, key);
    }

    /** The quantity of waste typed, or 0 if it isn't a number. */
    get wasteQuantity() {
        try {
            return parseFloat(this.state.part.quantityText || "0");
        } catch {
            return 0;
        }
    }

    get canConfirmPart() {
        const part = this.state.part;
        if (!part || !part.result) {
            return false;
        }
        if (this.isDecontamination) {
            return part.result === "missing" || (this.wasteQuantity > 0 && !!part.location.id);
        }
        return part.result !== "dismantled" || (!!part.condition && !!part.location.id);
    }

    async onChangeLocation() {
        this.state.choosingLocation = true;
        this.state.locationSearch = "";
        await this.loadLocations();
    }

    onLocationSearchInput(ev) {
        this.state.locationSearch = ev.target.value;
        browser.clearTimeout(this.searchTimeout);
        this.searchTimeout = browser.setTimeout(() => this.loadLocations(), SEARCH_DELAY);
    }

    async loadLocations() {
        const vehicle = this.state.vehicle;
        if (!vehicle || !this.state.choosingLocation) {
            return;
        }
        const locations = await this.orm.call(MODEL, "get_dismantle_locations", [vehicle.id, this.state.locationSearch]);
        if (this.state.vehicle === vehicle && this.state.choosingLocation) {
            this.state.locations = locations;
        }
    }

    onCancelLocation() {
        this.state.choosingLocation = false;
    }

    onSelectLocation(location) {
        browser.clearTimeout(this.searchTimeout);
        this.state.part.location = location;
        this.state.choosingLocation = false;
    }

    async onConfirmPart() {
        const vehicle = this.state.vehicle;
        const part = this.state.part;
        if (!this.canConfirmPart) {
            return;
        }
        let data;
        if (part.marked) {
            data = await this.run("update_decontamination_part", [
                vehicle.id,
                part.marked.id,
                this.wasteQuantity > 0 ? this.wasteQuantity : 1,
                part.result,
                part.result === "discarded" ? part.location.id : false,
            ]);
        } else if (this.isDecontamination) {
            data = await this.run("decontaminate_part", [
                vehicle.id,
                part.line.product_id,
                // Missing: the quantity typed, if any
                this.wasteQuantity > 0 ? this.wasteQuantity : 1,
                part.result,
                part.result === "discarded" ? part.location.id : false,
            ]);
        } else {
            data = await this.run("dismantle_part", [
                vehicle.id,
                part.line.id,
                part.quantity,
                part.result,
                part.condition || false,
                part.result === "dismantled" ? part.location.id : false,
            ]);
        }
        if (data && this.state.vehicle === vehicle) {
            this.applyDismantle(data);
            const option = this.partOptions.find((option) => this.isPartOption(option, part));
            this.notification.add(`${part.line.product}: ${option.name}`, { type: "success" });
            if (data.scrap_date) {
                this.notification.add(_t("%s dismantled.", vehicle.name), { type: "success" });
            }
        }
    }

    /** Mark the vehicle as decontaminated, or finish the dismantling, although parts are
     * left: today, or on the date chosen. */
    async onFinishDismantle(onDate = false) {
        const vehicle = this.state.vehicle;
        const decontamination = this.isDecontamination;
        await this.onMarkVehicle(decontamination ? "decontamination" : "scrap", onDate);
        if (!this.dismantleDone || this.state.vehicle !== vehicle || !this.state.dismantle) {
            return;
        }
        const method = decontamination ? "get_decontamination" : "get_dismantle";
        const data = await this.orm.call(MODEL, method, [vehicle.id]);
        // The operator may have left the dismantling meanwhile
        if (this.state.vehicle === vehicle && this.state.dismantle) {
            this.applyDismantle(data);
        }
    }

    /** Undo a part marked by mistake, after confirming it: it is again to dismantle. A waste is
     * deleted, until the vehicle is decontaminated. */
    onUndoPart(part) {
        const vehicle = this.state.vehicle;
        const decontamination = this.isDecontamination;
        let body;
        if (decontamination) {
            body = _t("%s will be removed; its stock goes back.", part.product);
        } else {
            body = _t("%s will be to dismantle again; its stock goes back.", part.product);
            if (vehicle.scrap_date) {
                body += " " + _t("The vehicle will be pending dismantling again.");
            }
        }
        this.dialog.add(ConfirmationDialog, {
            title: decontamination ? _t("Delete the waste") : _t("Undo the part"),
            body,
            confirmLabel: decontamination ? _t("Delete") : _t("Undo"),
            cancelLabel: _t("Keep it"),
            confirm: async () => {
                const data = await this.run("undo_dismantle_part", [vehicle.id, part.id]);
                if (data && this.state.vehicle === vehicle && this.state.dismantle) {
                    this.applyDismantle(data);
                    const message = decontamination ? _t("%s deleted.", part.product) : _t("%s undone.", part.product);
                    this.notification.add(message, { type: "success" });
                }
            },
            cancel: () => {},
        });
    }

    partImage(line) {
        return imageUrl("product.product", line.product_id, "image_128", { unique: line.image_unique });
    }

    partResultClass(result) {
        return { dismantled: "text-bg-success", missing: "text-bg-warning", discarded: "text-bg-danger" }[result] || "text-bg-secondary";
    }

    onMarkDateChange(ev) {
        this.state.markDate = ev.target.value;
    }

    /** Mark the vehicle as decontaminated or dismantled: today, or on the date chosen. */
    async onMarkVehicle(stage, onDate = false) {
        const vehicle = this.state.vehicle;
        if (onDate && !this.state.markDate) {
            this.notification.add(_t("Choose the date."), { type: "warning" });
            return;
        }
        const summary = await this.run("mark_vehicle", [vehicle.id, stage, onDate ? this.state.markDate : false]);
        if (summary && this.state.vehicle === vehicle) {
            Object.assign(vehicle, summary);
            const message = stage === "scrap" ? _t("%s dismantled.", vehicle.name) : _t("%s decontaminated.", vehicle.name);
            this.notification.add(message, { type: "success" });
        }
    }

    onUnmarkVehicle(stage) {
        const vehicle = this.state.vehicle;
        const scrap = stage === "scrap";
        this.dialog.add(ConfirmationDialog, {
            title: scrap ? _t("Undo the dismantling") : _t("Undo the decontamination"),
            body: scrap
                ? _t("%s will be pending dismantling again.", vehicle.name)
                : _t("%s will be pending decontamination again.", vehicle.name),
            confirmLabel: _t("Undo"),
            cancelLabel: _t("Keep it"),
            confirm: async () => {
                const summary = await this.run("unmark_vehicle", [vehicle.id, stage]);
                if (summary && this.state.vehicle === vehicle) {
                    Object.assign(vehicle, summary);
                }
            },
            cancel: () => {},
        });
    }

    async onOpenVehicleForm() {
        const vehicle = this.state.vehicle;
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: vehicle.model_name,
            res_id: vehicle.id,
            views: [[false, "form"]],
            target: "new",
        }, { onClose: () => this.refreshVehicle() });
    }

    vehicleImage(vehicle) {
        return imageUrl("product.product", vehicle.product_id, "image_128", { unique: vehicle.image_unique });
    }

    /** A stage of the legal deadlines of a vehicle: its limit, the days left and its date. */
    deadline(vehicle, stage) {
        const prefix = stage === "scrap" ? "scrap" : "decontamination";
        return {
            stage,
            name: stage === "scrap" ? _t("Dismantling") : _t("Decontamination"),
            limit: vehicle[`${prefix}_limit_date`],
            daysLeft: vehicle[`${prefix}_days_left`],
            date: vehicle[`${prefix}_date`],
        };
    }

    deadlineClass(deadline) {
        if (deadline.date) {
            return "text-bg-success";
        }
        if (!deadline.limit) {
            return "text-bg-secondary";
        }
        if (deadline.daysLeft < 0) {
            return "text-bg-danger";
        }
        return deadline.daysLeft <= 3 ? "text-bg-warning" : "text-bg-secondary";
    }

    deadlineLabel(deadline) {
        if (deadline.date) {
            return deadline.stage === "scrap"
                ? _t("Dismantled on %s", this.formatDateShort(deadline.date))
                : _t("Decontaminated on %s", this.formatDateShort(deadline.date));
        }
        if (!deadline.limit) {
            return _t("No limit");
        }
        if (deadline.daysLeft < 0) {
            return deadline.daysLeft === -1 ? _t("1 day late") : _t("%s days late", -deadline.daysLeft);
        }
        if (deadline.daysLeft === 0) {
            return _t("Due today");
        }
        return deadline.daysLeft === 1 ? _t("1 day left") : _t("%s days left", deadline.daysLeft);
    }

    /** Where the vehicle is: of the vehicles to dismantle, their stage; of the others, their stock. */
    vehicleStatus(vehicle) {
        if (vehicle.is_subproduct && !vehicle.scrap_date && (vehicle.origin || vehicle.discharge_date)) {
            return { label: _t("To dismantle"), cls: "text-bg-info" };
        }
        if (vehicle.scrap_date) {
            return { label: _t("Dismantled on %s", this.formatDateShort(vehicle.scrap_date)), cls: "text-bg-success" };
        }
        if (vehicle.decontamination_date) {
            return {
                label: _t("Decontaminated on %s", this.formatDateShort(vehicle.decontamination_date)),
                cls: "text-bg-info",
            };
        }
        if (vehicle.discharge_date) {
            return { label: _t("Received on %s", this.formatDateShort(vehicle.discharge_date)), cls: "text-bg-info" };
        }
        if (vehicle.qty_available > 0) {
            return { label: _t("In stock"), cls: "text-bg-info" };
        }
        return { label: _t("To receive"), cls: "text-bg-warning" };
    }

    canMark(vehicle, stage) {
        if (vehicle.is_subproduct) {
            // Dismantled from another product, or bought and received
            return stage === "scrap" && !!(vehicle.origin || vehicle.discharge_date);
        }
        if (vehicle.unbuild_type !== "main" || !vehicle.discharge_date) {
            return false;
        }
        return stage === "scrap" ? !!vehicle.decontamination_date : true;
    }

    formatDateShort(value) {
        return value ? formatDate(deserializeDate(value)) : "";
    }

    formatAmount(amount) {
        return formatCurrency(amount, this.state.data.currency_id);
    }

    formatQty(qty) {
        return formatFloat(qty, { digits: [false, 3], trailingZeros: false });
    }

    /** A number to edit: without thousands separators, so that it reads well in a field. */
    formatInput(value) {
        return formatFloat(value, { digits: [false, 3], trailingZeros: false, thousandsSep: "" });
    }

    formatDateTimeShort(value) {
        return value ? formatDateTime(deserializeDateTime(value), { showSeconds: false }) : "";
    }
}

registry.category("actions").add("scrap_touch.screen", TouchScreen);
