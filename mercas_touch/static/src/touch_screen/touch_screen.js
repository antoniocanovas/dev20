import { Component, onPatched, onWillStart, onWillUnmount, proxy, useListener, useProps, usePlugin } from "@odoo/owl";
import { BarcodePlugin } from "@barcodes/barcode_plugin";
import { BusPlugin } from "@bus/services/bus_plugin";
import { browser } from "@web/core/browser/browser";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { isDisplayStandalone } from "@web/core/browser/feature_detection";
import { formatCurrency } from "@web/core/currency";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime, formatDate, formatDateTime } from "@web/core/l10n/dates";
import { normalize } from "@web/core/l10n/utils";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { formatFloat } from "@web/core/utils/numbers";
import { imageUrl } from "@web/core/utils/urls";
import { parseFloat } from "@web/views/fields/parsers";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { applyNumpadKey, TouchNumpad } from "./touch_numpad";
import { localization } from "@web/core/l10n/localization";

const MODEL = "mercas.touch";
// Sent by the server when the stock of some lots changes
const LOTS_CHANGED = "mercas_touch/lots_changed";
// Time to wait after typing before searching partners or lots
const SEARCH_DELAY = 300;

/** A random uuid (version 4); crypto.randomUUID() needs HTTPS, the counter may use plain HTTP. */
function randomUuid() {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/**
 * Counter screen of the wholesale market, made for touch screens.
 *
 * One mode per task, also opened with the function keys: F1 sale, F2 purchase, F3 boxes,
 * F4 lots and F5 payments. Each operation is a single call to the server, which runs the flows
 * of mercas_base; it carries a uuid so that a double tap or a retry doesn't duplicate it.
 * The screen works online only: the stock of the lots must be the real one.
 */
export class TouchScreen extends Component {
    static template = "mercas_touch.TouchScreen";
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
            { key: "sale", fkey: "F1", name: _t("Sale"), icon: "storefront", help: _t("Sell and deliver with lots and boxes") },
            { key: "purchase", fkey: "F2", name: _t("Purchase"), icon: "local_shipping", help: _t("Buy and receive, with new lots and labels") },
            { key: "boxes", fkey: "F3", name: _t("Boxes"), icon: "inventory_2", help: _t("Boxes given back by customers or to suppliers") },
            { key: "lots", fkey: "F4", name: _t("Lots"), icon: "widgets", help: _t("Stock of the lots, scrap and settlement") },
            { key: "payment", fkey: "F5", name: _t("Payments"), icon: "payments", help: _t("Collect the invoices of a customer") },
            { key: "labels", fkey: "F6", name: _t("Damaged label"), icon: "label", help: _t("Reprint the labels of a lot") },
        ];
        this.state = proxy({
            // false (main menu) or the key of a mode
            mode: false,
            data: null,
            sending: false,
            // Sale and purchase: the drafts to resume, or the partner of a new one
            drafts: [],
            draftSearch: "",
            // "draft" (in progress), "to_invoice" or "all"
            draftFilter: "draft",
            choosingCustomer: false,
            // Draft of the sale or purchase being made, saved after each change: { id, name }
            order: null,
            // false, "saving", "saved" or "error"
            saveState: false,
            // Partner of the sale, purchase, boxes or payment, with their debt, risk and boxes
            partnerSearch: "",
            partners: [],
            partner: null,
            // Catalog of the sale and the purchase
            categoryId: false,
            productSearch: "",
            // Product being added: its lots, then the line being edited
            product: null,
            lots: [],
            lotsLoading: false,
            entry: null,
            // Lines of the sale or the purchase
            lines: [],
            // States of origin of each country, loaded when the country is chosen (without the
            // origin filter of the company, which sends the few states of origin at once)
            originStates: {},
            // Price of a line being changed from the ticket: { key, value, fresh }
            priceEdit: null,
            // Result of the last operation, shown until the next one starts
            done: null,
            // Boxes
            boxDirection: "return",
            boxQty: {},
            // Lots
            lotSearch: "",
            lotList: [],
            lotSelection: {},
            scrap: null,
            // Damaged label: the lots found by the code scanned or typed
            labelSearch: "",
            labelLots: [],
            // Payments
            invoiceIds: [],
            amount: "",
            journalId: false,
            memo: "",
        });
        this.searchTimeout = null;
        // Saves of the draft being made, one after the other; a new operation starts a
        // new token, so that a late answer doesn't change it
        this.saveToken = {};
        this.saveDirty = false;
        this.savePromise = null;
        // The price field is focused and selected each time the editor moves to a line, so
        // that a keyboard or a scale replaces the price
        this.focusPrice = false;
        // The code of a damaged label is typed or scanned as soon as its screen opens
        this.focusLabelSearch = false;
        onPatched(() => {
            if (this.focusPrice) {
                this.focusPrice = false;
                const input = document.querySelector(".o_mercas_touch_price_edit_input");
                input?.focus();
                input?.select();
            }
            if (this.focusLabelSearch) {
                this.focusLabelSearch = false;
                const input = document.querySelector(".o_mercas_touch_label_search");
                input?.focus();
                input?.select();
            }
        });

        onWillStart(async () => {
            this.state.data = await this.orm.call(MODEL, "get_screen_data", []);
            this.state.journalId = this.state.data.journals[0]?.id || false;
        });

        // F1-F5 open the modes, Escape goes back. Captured on the window, before the shortcuts
        // of mercas_keys, which open the backend lists with the same keys.
        useListener(window, "keydown", (ev) => this.onKeydown(ev), { capture: true });
        // A scanner in keyboard mode: the code of a box label is the name of its lot
        useBus(usePlugin(BarcodePlugin).bus, "barcode_scanned", (ev) =>
            this.onBarcodeScanned(ev.detail.barcode)
        );
        // Sales and scraps made on other screens change the stock of the lots shown
        const bus = usePlugin(BusPlugin);
        const onLotsChanged = (payload) => this.onLotsChanged(payload);
        bus.subscribe(LOTS_CHANGED, onLotsChanged);
        onWillUnmount(() => {
            bus.unsubscribe(LOTS_CHANGED, onLotsChanged);
            browser.clearTimeout(this.searchTimeout);
        });
    }

    // ------------------------------------------------------------------
    // Navigation
    // ------------------------------------------------------------------

    onKeydown(ev) {
        const mode = this.modes.find((mode) => mode.fkey === ev.key);
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
        this.state.partnerSearch = "";
        this.state.partners = [];
        this.state.mode = mode;
        if (mode === "lots") {
            await this.loadLots();
        } else if (mode === "labels") {
            this.state.labelSearch = "";
            this.focusLabelSearch = true;
            await this.loadLabelLots();
        } else if (this.hasDrafts()) {
            await this.loadDrafts();
        } else {
            await this.searchPartners();
        }
    }

    resetOperation() {
        this.state.product = null;
        this.state.lots = [];
        this.state.entry = null;
        this.state.lines = [];
        this.state.priceEdit = null;
        this.state.done = null;
        this.state.categoryId = false;
        this.state.productSearch = "";
        this.state.boxQty = {};
        this.state.boxDirection = "return";
        this.state.invoiceIds = [];
        this.state.amount = "";
        this.state.memo = "";
        this.state.scrap = null;
        this.state.lotSelection = {};
        this.state.order = null;
        this.state.saveState = false;
        this.state.choosingCustomer = false;
        this.operationUuid = null;
        this.saveToken = {};
        this.saveDirty = false;
        this.savePromise = null;
    }

    async onBack() {
        if (this.state.sending) {
            return;
        }
        if (this.state.priceEdit) {
            this.onClosePriceEdit();
        } else if (this.state.entry) {
            this.state.entry = null;
            if (!this.state.lots.length) {
                this.state.product = null;
            }
        } else if (this.state.product) {
            this.state.product = null;
            this.state.lots = [];
        } else if (this.state.scrap) {
            this.state.scrap = null;
        } else if (this.hasDrafts() && (this.state.partner || this.state.choosingCustomer)) {
            // The draft is saved: back to the list, to resume it or another one later
            await this.flushSave();
            this.resetOperation();
            this.state.partner = null;
            await this.loadDrafts();
        } else if (this.state.partner && !this.state.done && this.hasWork()) {
            this.notification.add(_t("Finish or clear the current operation first."), { type: "warning" });
        } else if (this.state.partner) {
            this.resetOperation();
            this.state.partner = null;
            this.searchPartners();
        } else {
            this.state.mode = false;
        }
    }

    hasWork() {
        return (
            this.state.lines.length > 0 ||
            Object.values(this.state.boxQty).some((qty) => qty > 0) ||
            this.state.invoiceIds.length > 0
        );
    }

    onClearOperation() {
        if (this.hasDrafts() && this.state.order) {
            this.onCancelDraft();
            return;
        }
        const partner = this.state.partner;
        this.resetOperation();
        this.state.partner = partner;
    }

    clearTitle() {
        if (!this.hasDrafts() || !this.state.order) {
            return _t("Clear");
        }
        return this.state.mode === "sale" ? _t("Cancel the quotation") : _t("Cancel the purchase");
    }

    draftSearchPlaceholder() {
        return this.state.mode === "sale"
            ? _t("Search a quotation or a customer")
            : _t("Search a purchase or a supplier");
    }

    /** The sale and the purchase are saved as drafts while they are made. */
    hasDrafts() {
        return this.state.mode === "sale" || this.state.mode === "purchase";
    }

    // ------------------------------------------------------------------
    // Drafts: the sale or purchase being made is saved as a quotation or a request for
    // quotation in draft
    // ------------------------------------------------------------------

    onDraftSearchInput(ev) {
        this.state.draftSearch = ev.target.value;
        browser.clearTimeout(this.searchTimeout);
        this.searchTimeout = browser.setTimeout(() => this.loadDrafts(), SEARCH_DELAY);
    }

    async loadDrafts() {
        const mode = this.state.mode;
        const drafts = await this.orm.call(MODEL, "get_drafts", [
            mode,
            this.state.draftSearch,
            this.state.draftFilter,
        ]);
        if (this.state.mode === mode && !this.state.partner) {
            this.state.drafts = drafts;
        }
    }

    get draftFilters() {
        return [
            { key: "draft", name: _t("In progress") },
            { key: "to_invoice", name: _t("To invoice") },
            { key: "all", name: _t("All") },
        ];
    }

    async onDraftFilter(filter) {
        this.state.draftFilter = filter;
        await this.loadDrafts();
    }

    async onNewDraft() {
        this.resetOperation();
        this.state.choosingCustomer = true;
        this.state.partnerSearch = "";
        await this.searchPartners();
    }

    async onResumeDraft(draft) {
        if (draft.state !== "draft") {
            await this.openOrderSummary(draft);
            return;
        }
        const [data, partner] = await Promise.all([
            this.orm.call(MODEL, "get_draft", [this.state.mode, draft.id]),
            this.orm.call(MODEL, "get_partner_info", [draft.partner_id]),
        ]);
        this.resetOperation();
        this.state.partner = partner;
        this.state.order = { id: data.id, name: data.name };
        this.state.saveState = "saved";
        this.state.lines = data.lines.map((line) => ({
            key: `line-${line.line_id}`,
            lineId: line.line_id,
            product: line.product,
            lot: line.lot || null,
            attributeValueIds: line.attribute_value_ids || [],
            qty: line.qty,
            price: line.price,
            boxQty: line.box_qty || 0,
            boxProductId: line.box_product_id || false,
            note: line.note || "",
            origNote: line.note || "",
            originCountryId: line.origin_country_id || false,
            originStateId: line.origin_state_id || false,
            firm: Boolean(line.firm),
            lotName: line.lot_name || "",
        }));
    }

    /** A confirmed sale or purchase, to look it up, print it or invoice it. */
    async openOrderSummary(draft) {
        const mode = this.state.mode;
        const [summary, partner] = await Promise.all([
            this.orm.call(MODEL, "get_order_summary", [mode, draft.id]),
            this.orm.call(MODEL, "get_partner_info", [draft.partner_id]),
        ]);
        this.resetOperation();
        this.state.partner = partner;
        this.state.done = { ...summary, reviewing: true };
    }

    async refreshOrderSummary() {
        const done = this.state.done;
        if (!done) {
            return;
        }
        const summary = await this.orm.call(MODEL, "get_order_summary", [done.kind, done.id]);
        if (this.state.done === done) {
            Object.assign(done, summary);
        }
        await this.reloadPartner();
    }

    onCancelDraft() {
        const order = this.state.order;
        const mode = this.state.mode;
        this.dialog.add(ConfirmationDialog, {
            title: this.clearTitle(),
            body: _t("%s will be cancelled.", order.name),
            confirmLabel: this.clearTitle(),
            cancelLabel: _t("Keep it"),
            confirm: async () => {
                await this.flushSave();
                await this.orm.call(MODEL, "cancel_draft", [mode, order.id]);
                this.resetOperation();
                this.state.partner = null;
                await this.loadDrafts();
            },
            cancel: () => {},
        });
    }

    /** The lines of the sale or the purchase, as the server saves them in the draft. */
    linesPayload(lines) {
        const isPurchase = this.state.mode === "purchase";
        return lines.map((line) => ({
            ...(line.lineId ? { line_id: line.lineId } : {}),
            product_id: line.product.id,
            qty: line.qty,
            price_unit: line.price,
            ...(!isPurchase && line.lot ? { lot_id: line.lot.id } : {}),
            ...(!isPurchase ? { attribute_value_ids: line.attributeValueIds || [] } : {}),
            box_qty: line.boxQty || 0,
            ...(line.boxProductId ? { box_product_id: line.boxProductId } : {}),
            ...(isPurchase
                ? {
                      firm: line.firm,
                      ...(line.lotName ? { lot_name: line.lotName } : {}),
                      ...(line.originCountryId ? { origin_country_id: line.originCountryId } : {}),
                      ...(line.originStateId ? { origin_state_id: line.originStateId } : {}),
                  }
                : {}),
            // The text replaces the description under the product only when it changed
            ...(line.note !== (line.lineId ? line.origNote : "") ? { note: line.note } : {}),
        }));
    }

    /** Save the draft after a change of the lines, in the background. */
    scheduleSave() {
        if (!this.hasDrafts() || !this.state.partner || this.state.done) {
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
        const notes = lines.map((line) => line.note);
        const vals = {
            uuid: this.newUuid(),
            partner_id: this.state.partner.id,
            ...(this.state.order ? { order_id: this.state.order.id } : {}),
            lines: this.linesPayload(lines),
        };
        this.state.saveState = "saving";
        let result;
        try {
            result = await this.orm.silent.call(MODEL, "save_draft", [this.state.mode, vals]);
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
            line.origNote = notes[index];
        });
        this.state.saveState = this.saveDirty ? "saving" : "saved";
    }

    /** Wait for the saves in progress. */
    async flushSave() {
        while (this.savePromise) {
            await this.savePromise;
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

    get currentMode() {
        return this.modes.find((mode) => mode.key === this.state.mode);
    }

    // ------------------------------------------------------------------
    // Partners
    // ------------------------------------------------------------------

    partnerKind() {
        return this.state.mode === "purchase" ? "supplier" : "customer";
    }

    partnerPlaceholder() {
        return this.partnerKind() === "supplier" ? _t("Search a supplier") : _t("Search a customer");
    }

    onPartnerSearchInput(ev) {
        this.state.partnerSearch = ev.target.value;
        browser.clearTimeout(this.searchTimeout);
        this.searchTimeout = browser.setTimeout(() => this.searchPartners(), SEARCH_DELAY);
    }

    async searchPartners() {
        const mode = this.state.mode;
        const partners = await this.orm.call(MODEL, "search_partners", [
            this.state.partnerSearch,
            this.partnerKind(),
        ]);
        if (this.state.mode === mode && !this.state.partner) {
            this.state.partners = partners;
        }
    }

    async onSelectPartner(partnerId) {
        this.resetOperation();
        this.state.partner = await this.orm.call(MODEL, "get_partner_info", [partnerId]);
        // In a sale or a purchase, the draft is created with its first line
        if (this.state.mode === "boxes") {
            this.state.boxDirection = this.state.partner.boxes.some((box) => box.supplier < 0) &&
                !this.state.partner.boxes.some((box) => box.customer > 0) ? "deliver" : "return";
        }
    }

    async reloadPartner() {
        if (this.state.partner) {
            this.state.partner = await this.orm.call(MODEL, "get_partner_info", [this.state.partner.id]);
        }
    }

    debtTotal() {
        const debt = this.state.partner?.debt;
        return debt ? debt.overdue + debt.not_due : 0;
    }

    isOverLimit() {
        const partner = this.state.partner;
        if (!partner) {
            return false;
        }
        if (partner.risk) {
            return partner.risk.exception;
        }
        return partner.credit_limit > 0 && this.debtTotal() > partner.credit_limit;
    }

    /**
     * Credit used and granted to show in the risk warning, or null without a credit limit
     * (the risk can be exceeded by other limits, like the one of open invoices).
     */
    creditUsage() {
        const partner = this.state.partner;
        const [used, limit] = partner?.risk
            ? [partner.risk.total, partner.risk.limit]
            : [this.debtTotal(), partner?.credit_limit];
        return limit > 0 ? { used, limit } : null;
    }

    // ------------------------------------------------------------------
    // Catalog and lines of the sale and the purchase
    // ------------------------------------------------------------------

    isProductAllowed(product) {
        if (product.is_box) {
            return false;
        }
        return this.state.mode === "purchase" ? product.purchase_ok : product.sale_ok;
    }

    categories() {
        const used = new Set(
            this.state.data.products.filter((p) => this.isProductAllowed(p)).map((p) => p.categ_id)
        );
        return this.state.data.categories.filter((category) => used.has(category.id));
    }

    visibleProducts() {
        const search = normalize(this.state.productSearch.trim());
        return this.state.data.products.filter(
            (product) =>
                this.isProductAllowed(product) &&
                (search
                    ? normalize(`${product.default_code} ${product.name} ${product.barcode}`).includes(search)
                    : !this.state.categoryId || product.categ_id === this.state.categoryId)
        );
    }

    boxProducts() {
        return this.state.data.products.filter((product) => product.is_box);
    }

    productById(productId) {
        return this.state.data.products.find((product) => product.id === productId);
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

    async onSelectProduct(product) {
        if (this.state.priceEdit) {
            if (!this.commitPrice()) {
                return;
            }
            this.state.priceEdit = null;
        }
        this.state.product = product;
        this.state.lots = [];
        if (this.state.mode === "sale" && product.tracking) {
            await this.loadProductLots();
            if (!this.state.lots.length) {
                this.notification.add(_t("%s has no lot with stock.", product.name), { type: "warning" });
            }
        } else {
            this.openEntry(product, null);
        }
    }

    async loadProductLots() {
        const product = this.state.product;
        this.state.lotsLoading = true;
        try {
            const lots = await this.orm.call(MODEL, "get_product_lots", [product.id]);
            if (this.state.product === product) {
                this.state.lots = lots;
            }
        } finally {
            this.state.lotsLoading = false;
        }
    }

    /** Quantity of the lot already in the lines of the sale. */
    lotQtyInLines(lotId, exceptLine = null) {
        return this.state.lines
            .filter((line) => line.lot && line.lot.id === lotId && line !== exceptLine)
            .reduce((total, line) => total + line.qty, 0);
    }

    lotAvailable(lot, exceptLine = null) {
        return lot.available - this.lotQtyInLines(lot.id, exceptLine);
    }

    openEntry(product, lot, line = null) {
        const partner = this.state.partner;
        const defaultBox = product.box_product_id || false;
        this.state.entry = {
            line,
            product,
            lot,
            qty: line ? this.formatInput(line.qty) : "",
            price: line ? this.formatInput(line.price) : this.formatInput(product.price),
            boxQty: line ? line.boxQty : 0,
            boxProductId: line ? line.boxProductId : defaultBox,
            note: line ? line.note : "",
            showNote: Boolean(line?.note),
            originCountryId: line ? line.originCountryId : false,
            originStateId: line ? line.originStateId : false,
            firm: line ? line.firm : Boolean(partner?.firm_negotiation),
            lotName: line ? line.lotName : "",
            attributeValueIds: line ? [...(line.attributeValueIds || [])] : [],
            // Field written by the keypad
            field: "qty",
        };
        this.loadOriginStates(this.state.entry.originCountryId);
    }

    onSelectLot(lot) {
        if (this.lotAvailable(lot) <= 0) {
            this.notification.add(_t("All the stock of the lot %s is already in the sale.", lot.name), {
                type: "warning",
            });
            return;
        }
        this.openEntry(this.state.product, lot);
    }

    onEntryField(field) {
        this.state.entry.field = field;
    }

    onEntryInput(field, ev) {
        this.state.entry[field] = ev.target.value;
        this.state.entry.field = field;
    }

    onNumpadInput(value) {
        const entry = this.state.entry;
        if (entry.field === "boxQty") {
            entry.boxQty = Math.max(0, parseInt(value || "0", 10) || 0);
        } else {
            entry[entry.field] = value;
        }
    }


    /**
     * A key of the keypad, applied to the field being edited: the price of a line of the
     * ticket, the field of the line being added, the quantity to scrap or the amount to collect.
     */
    onNumpadKey(key) {
        const priceEdit = this.state.priceEdit;
        const entry = this.state.entry;
        if (priceEdit) {
            // The first key replaces the price, as on a till
            priceEdit.value = applyNumpadKey(priceEdit.fresh ? "" : priceEdit.value, key);
            priceEdit.fresh = false;
        } else if (entry) {
            if (entry.field === "boxQty") {
                if (key !== localization.decimalPoint) {
                    this.onNumpadInput(applyNumpadKey(String(entry.boxQty || ""), key));
                }
            } else {
                entry[entry.field] = applyNumpadKey(entry[entry.field], key);
            }
        } else if (this.state.scrap) {
            this.state.scrap.qty = applyNumpadKey(this.state.scrap.qty, key);
        } else if (this.state.mode === "payment") {
            this.state.amount = applyNumpadKey(this.state.amount, key);
        }
    }

    onBoxQtyStep(step) {
        this.state.entry.boxQty = Math.max(0, (this.state.entry.boxQty || 0) + step);
    }

    onEntryBoxProduct(ev) {
        this.state.entry.boxProductId = parseInt(ev.target.value, 10) || false;
    }

    onEntryCountry(ev) {
        this.state.entry.originCountryId = parseInt(ev.target.value, 10) || false;
        this.state.entry.originStateId = false;
        this.loadOriginStates(this.state.entry.originCountryId);
    }

    onEntryState(ev) {
        const stateId = parseInt(ev.target.value, 10) || false;
        this.state.entry.originStateId = stateId;
        const state = this.originStates().find((s) => s.id === stateId);
        if (state) {
            this.state.entry.originCountryId = state.country_id;
        }
    }

    async loadOriginStates(countryId) {
        const origin = this.state.data.origin;
        if (this.state.mode !== "purchase" || !origin.state || origin.filter || !countryId ||
            this.state.originStates[countryId]) {
            return;
        }
        const states = await this.orm.call(MODEL, "get_origin_states", [countryId]);
        this.state.originStates = { ...this.state.originStates, [countryId]: states };
    }

    /** States of origin to choose: of the country chosen, or all the states of origin. */
    originStates() {
        const countryId = this.state.entry?.originCountryId;
        const origin = this.state.data.origin;
        if (origin.filter) {
            return origin.states.filter((state) => !countryId || state.country_id === countryId);
        }
        return (countryId && this.state.originStates[countryId]) || [];
    }

    /** Attributes chosen on each sale of the product, as the quality and the size of bulk goods. */
    entryAttributes() {
        return this.state.mode === "sale" ? this.state.entry.product.attributes || [] : [];
    }

    /** A value of an attribute of the line: it replaces the other value of the attribute, and
     * touched again it is removed. */
    onEntryAttributeValue(attribute, value) {
        const entry = this.state.entry;
        const selected = entry.attributeValueIds.includes(value.id);
        const otherIds = attribute.values.map((v) => v.id);
        entry.attributeValueIds = entry.attributeValueIds.filter((id) => !otherIds.includes(id));
        if (!selected) {
            entry.attributeValueIds.push(value.id);
        }
    }

    /** Values chosen on the line, as "Extra · 70-75". */
    lineAttributes(line) {
        const names = [];
        for (const attribute of line.product.attributes || []) {
            for (const value of attribute.values) {
                if ((line.attributeValueIds || []).includes(value.id)) {
                    names.push(value.name);
                }
            }
        }
        return names.join(" · ");
    }

    onEntryFirm(ev) {
        this.state.entry.firm = ev.target.checked;
    }

    toggleEntryNote() {
        this.state.entry.showNote = !this.state.entry.showNote;
    }

    parseNumber(value) {
        try {
            return parseFloat(String(value || "").trim() || "0");
        } catch {
            return NaN;
        }
    }

    onAddEntry() {
        const entry = this.state.entry;
        const qty = this.parseNumber(entry.qty);
        const price = this.parseNumber(entry.price);
        if (!(qty > 0)) {
            this.notification.add(_t("Enter the quantity."), { type: "warning" });
            entry.field = "qty";
            return;
        }
        if (!(price >= 0)) {
            this.notification.add(_t("Enter a valid price."), { type: "warning" });
            entry.field = "price";
            return;
        }
        if (entry.lot && qty > this.lotAvailable(entry.lot, entry.line) + 1e-6) {
            this.notification.add(
                _t("The lot %(lot)s only has %(qty)s %(uom)s available.", {
                    lot: entry.lot.name,
                    qty: this.formatQty(this.lotAvailable(entry.lot, entry.line)),
                    uom: entry.product.uom,
                }),
                { type: "warning" }
            );
            return;
        }
        const values = {
            product: entry.product,
            lot: entry.lot,
            qty,
            price,
            boxQty: entry.boxQty || 0,
            boxProductId: entry.boxQty ? entry.boxProductId : false,
            note: entry.note.trim(),
            originCountryId: entry.originCountryId,
            originStateId: entry.originStateId,
            firm: entry.firm,
            lotName: entry.lotName.trim(),
            attributeValueIds: [...entry.attributeValueIds],
        };
        if (entry.line) {
            Object.assign(entry.line, values);
        } else {
            this.state.lines.push({ key: `${Date.now()}-${this.state.lines.length}`, ...values });
        }
        this.scheduleSave();
        this.state.entry = null;
        this.state.product = null;
        this.state.lots = [];
    }

    onEditLine(line) {
        if (this.state.sending || !this.commitPrice()) {
            return;
        }
        this.state.priceEdit = null;
        this.state.product = line.product;
        this.state.lots = line.lot ? [line.lot] : [];
        this.openEntry(line.product, line.lot, line);
    }

    onRemoveLine(line) {
        if (this.state.priceEdit?.key === line.key) {
            this.state.priceEdit = null;
        }
        this.state.lines = this.state.lines.filter((l) => l !== line);
        this.scheduleSave();
        if (this.state.entry?.line === line) {
            this.state.entry = null;
            this.state.product = null;
        }
    }

    // ------------------------------------------------------------------
    // Quick price change from the ticket, line after line
    // ------------------------------------------------------------------

    onEditPrice(line) {
        if (this.state.sending || (this.state.priceEdit && !this.commitPrice())) {
            return;
        }
        // The line being added is left aside: the price is changed on the ticket
        this.state.entry = null;
        this.state.product = null;
        this.state.lots = [];
        this.openPriceEdit(line);
    }

    openPriceEdit(line) {
        this.state.priceEdit = { key: line.key, value: this.formatInput(line.price), fresh: true };
        this.focusPrice = true;
    }

    priceEditLine() {
        const key = this.state.priceEdit?.key;
        return this.state.lines.find((line) => line.key === key);
    }

    priceEditIndex() {
        return this.state.lines.indexOf(this.priceEditLine());
    }

    /** The price typed, with the quantity of the line, as the subtotal shown while typing. */
    priceEditSubtotal() {
        const price = this.parseNumber(this.state.priceEdit.value);
        return price >= 0 ? this.priceEditLine().qty * price : 0;
    }


    onPriceInput(ev) {
        this.state.priceEdit.value = ev.target.value;
        this.state.priceEdit.fresh = false;
    }

    onPriceKeydown(ev) {
        if (ev.key === "Enter" || ev.key === "ArrowDown" || ev.key === "ArrowUp") {
            ev.preventDefault();
            this.onPriceStep(ev.key === "ArrowUp" || (ev.key === "Enter" && ev.shiftKey) ? -1 : 1);
        }
    }

    /** Write the price typed on its line; false if it isn't a valid price. */
    commitPrice() {
        const edit = this.state.priceEdit;
        const line = this.priceEditLine();
        if (!edit || !line) {
            return true;
        }
        const price = this.parseNumber(edit.value);
        if (!(price >= 0)) {
            this.notification.add(_t("Enter a valid price."), { type: "warning" });
            this.focusPrice = true;
            return false;
        }
        if (line.price !== price) {
            line.price = price;
            this.scheduleSave();
        }
        return true;
    }

    /** Write the price and go to the previous (-1) or next (1) line; past the last one, close. */
    onPriceStep(step) {
        if (!this.commitPrice()) {
            return;
        }
        const next = this.state.lines[this.priceEditIndex() + step];
        if (next) {
            this.openPriceEdit(next);
        } else if (step > 0) {
            this.state.priceEdit = null;
        }
    }

    onClosePriceEdit() {
        if (this.commitPrice()) {
            this.state.priceEdit = null;
        }
    }

    lineSubtotal(line) {
        return line.qty * line.price;
    }

    linesTotal() {
        return this.state.lines.reduce((total, line) => total + this.lineSubtotal(line), 0);
    }

    linesBoxes() {
        return this.state.lines.reduce((total, line) => total + (line.boxQty || 0), 0);
    }

    boxName(boxProductId) {
        return this.productById(boxProductId)?.name || _t("boxes");
    }

    // ------------------------------------------------------------------
    // Operations
    // ------------------------------------------------------------------

    newUuid() {
        // Kept until the operation is done, so that a retry sends the same one
        if (!this.operationUuid) {
            this.operationUuid = randomUuid();
        }
        return this.operationUuid;
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

    async onSell() {
        if (!this.state.lines.length || !this.commitPrice()) {
            return;
        }
        this.state.sending = true;
        try {
            await this.flushSave();
        } finally {
            this.state.sending = false;
        }
        const result = await this.run("sell", [
            {
                uuid: this.newUuid(),
                partner_id: this.state.partner.id,
                ...(this.state.order ? { order_id: this.state.order.id } : {}),
                lines: this.linesPayload(this.state.lines),
            },
        ]);
        if (!result) {
            return;
        }
        this.finishOperation({ kind: "sale", model: "sale.order", ...result.order });
        if (result.action) {
            // Risk exceeded: the standard dialog lets a risk manager go on
            await this.action.doAction(result.action, {
                onClose: () => this.refreshSaleAfterRisk(result.order.id),
            });
        }
    }

    async refreshSaleAfterRisk(orderId) {
        const [order] = await this.orm.read("sale.order", [orderId], ["name", "state"]);
        if (this.state.done?.id === orderId && order) {
            this.state.done.state = order.state;
            this.state.done.delivered = order.state === "sale";
        }
        await this.reloadPartner();
    }

    async onPurchase() {
        if (!this.state.lines.length || !this.commitPrice()) {
            return;
        }
        this.state.sending = true;
        try {
            await this.flushSave();
        } finally {
            this.state.sending = false;
        }
        const result = await this.run("purchase", [
            {
                uuid: this.newUuid(),
                partner_id: this.state.partner.id,
                ...(this.state.order ? { order_id: this.state.order.id } : {}),
                lines: this.linesPayload(this.state.lines),
            },
        ]);
        if (result) {
            this.finishOperation({ kind: "purchase", model: "purchase.order", ...result.order });
        }
    }

    finishOperation(done) {
        const partner = this.state.partner;
        this.resetOperation();
        this.state.partner = partner;
        this.state.done = done;
        this.reloadPartner();
    }

    /** Invoice the sale just made; the invoice can then be printed and collected. */
    async onInvoiceSale() {
        const done = this.state.done;
        const invoice = await this.run("invoice_sale", [done.id]);
        if (invoice?.action) {
            // Risk exceeded: the invoice stays in draft until a risk manager goes on
            Object.assign(done, invoice.order);
            await this.action.doAction(invoice.action, {
                onClose: () => this.refreshOrderSummary(),
            });
            return;
        }
        if (invoice && this.state.done === done) {
            Object.assign(done, invoice.order);
            done.invoice = invoice;
            await this.reloadPartner();
        }
    }

    /** The bill of a purchase, made from the order as in the backend, reviewed in a dialog. */
    async onInvoicePurchase() {
        const action = await this.run("invoice_purchase", [this.state.done.id]);
        if (action) {
            await this.action.doAction(action, { onClose: () => this.refreshOrderSummary() });
        }
    }

    /** Collect the invoice of the sale just made, in the payments of the customer. */
    async onCollectInvoice() {
        const invoice = this.state.done.invoice;
        const partnerId = this.state.partner.id;
        await this.flushSave();
        this.resetOperation();
        this.state.mode = "payment";
        this.state.partner = await this.orm.call(MODEL, "get_partner_info", [partnerId]);
        if (this.state.partner.invoices.some((inv) => inv.id === invoice.id)) {
            this.state.invoiceIds = [invoice.id];
            this.state.amount = this.formatInput(invoice.residual);
        }
    }

    async onPrint(kind) {
        const done = this.state.done;
        const action = await this.orm.call(MODEL, "get_print_action", [done.model, done.id, kind]);
        await this.action.doAction(action);
    }

    async onNewOperation() {
        this.state.done = null;
        if (this.hasDrafts()) {
            // A new sale or purchase starts again from the drafts
            this.state.partner = null;
            await this.loadDrafts();
        }
    }

    // ------------------------------------------------------------------
    // Boxes
    // ------------------------------------------------------------------

    onBoxDirection(direction) {
        this.state.boxDirection = direction;
        this.state.boxQty = {};
    }

    boxBalance(productId) {
        const box = this.state.partner?.boxes.find((box) => box.product_id === productId);
        if (!box) {
            return 0;
        }
        return this.state.boxDirection === "return" ? box.customer : -box.supplier;
    }

    onBoxStep(productId, step) {
        const qty = Math.max(0, (this.state.boxQty[productId] || 0) + step);
        this.state.boxQty = { ...this.state.boxQty, [productId]: qty };
    }

    onBoxInput(productId, ev) {
        const qty = Math.max(0, parseInt(ev.target.value, 10) || 0);
        this.state.boxQty = { ...this.state.boxQty, [productId]: qty };
    }

    boxTotal() {
        return Object.values(this.state.boxQty).reduce((total, qty) => total + qty, 0);
    }

    async onMoveBoxes() {
        const lines = Object.entries(this.state.boxQty)
            .filter(([, qty]) => qty > 0)
            .map(([productId, qty]) => ({ product_id: parseInt(productId, 10), qty }));
        if (!lines.length) {
            return;
        }
        const result = await this.run("move_boxes", [
            {
                uuid: this.newUuid(),
                partner_id: this.state.partner.id,
                direction: this.state.boxDirection,
                lines,
            },
        ]);
        if (!result) {
            return;
        }
        const direction = this.state.boxDirection;
        this.finishOperation({ kind: "boxes", direction, ...result.order });
        this.state.partner.boxes = result.boxes;
        this.state.boxDirection = direction;
        if (result.action) {
            await this.action.doAction(result.action, { onClose: () => this.reloadPartner() });
        }
    }

    async onOpenDocument() {
        const done = this.state.done;
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: done.model,
            res_id: done.id,
            views: [[false, "form"]],
            target: "new",
        });
    }

    // ------------------------------------------------------------------
    // Lots
    // ------------------------------------------------------------------

    onLotSearchInput(ev) {
        this.state.lotSearch = ev.target.value;
        browser.clearTimeout(this.searchTimeout);
        this.searchTimeout = browser.setTimeout(() => this.loadLots(), SEARCH_DELAY);
    }

    async loadLots() {
        const lots = await this.orm.call(MODEL, "get_lots", [this.state.lotSearch]);
        if (this.state.mode === "lots") {
            this.state.lotList = lots;
            const ids = new Set(lots.map((lot) => lot.id));
            this.state.lotSelection = Object.fromEntries(
                Object.entries(this.state.lotSelection).filter(([id]) => ids.has(parseInt(id, 10)))
            );
        }
    }

    lotProgress(lot) {
        const base = Math.max(lot.purchased, lot.received, lot.sold + lot.scrapped + lot.stock, 1);
        const percent = (value) => `${Math.max(0, Math.min(100, (value / base) * 100))}%`;
        return { sold: percent(lot.sold), scrapped: percent(lot.scrapped), stock: percent(lot.stock) };
    }

    toggleLotSelection(lot) {
        const selection = { ...this.state.lotSelection };
        if (selection[lot.id]) {
            delete selection[lot.id];
        } else {
            selection[lot.id] = true;
        }
        this.state.lotSelection = selection;
    }

    selectedLotIds() {
        return Object.keys(this.state.lotSelection).map((id) => parseInt(id, 10));
    }

    onScrapLot(lot) {
        this.state.scrap = { lot, qty: "" };
    }

    onScrapInput(value) {
        this.state.scrap.qty = value;
    }

    async onConfirmScrap() {
        const scrap = this.state.scrap;
        const qty = this.parseNumber(scrap.qty);
        if (!(qty > 0)) {
            this.notification.add(_t("Enter the quantity to scrap."), { type: "warning" });
            return;
        }
        const lot = await this.run("scrap_lot", [scrap.lot.id, qty]);
        if (lot) {
            this.state.scrap = null;
            this.notification.add(_t("%(qty)s %(uom)s of the lot %(lot)s scrapped.", {
                qty: this.formatQty(qty), uom: lot.uom, lot: lot.name,
            }), { type: "success" });
            await this.loadLots();
        }
    }

    async onInvoiceLots(mode) {
        const lotIds = this.selectedLotIds();
        if (!lotIds.length) {
            this.notification.add(_t("Select the lots to invoice."), { type: "warning" });
            return;
        }
        const action = await this.run("invoice_lots", [lotIds, mode]);
        this.state.lotSelection = {};
        await this.loadLots();
        if (action) {
            await this.action.doAction(action);
        }
    }

    /** The box labels of the lots, as many as boxes were bought, in the wizard of mercas_base. */
    async onPrintLotLabels(lotIds) {
        const action = await this.run("get_lot_label_action", [lotIds]);
        if (action) {
            await this.action.doAction(action, {
                onClose: () => {
                    if (this.state.mode === "labels") {
                        this.focusLabelSearch = true;
                        this.render();
                    }
                },
            });
        }
    }

    // ------------------------------------------------------------------
    // Damaged label: reprint the labels of a lot, scanned or typed
    // ------------------------------------------------------------------

    onLabelSearchInput(ev) {
        this.state.labelSearch = ev.target.value;
        browser.clearTimeout(this.searchTimeout);
        this.searchTimeout = browser.setTimeout(() => this.loadLabelLots(), SEARCH_DELAY);
    }

    /** Enter ends a typed code, and a scanner in keyboard mode writing in the field. */
    async onLabelSearchKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            await this.findLabel(ev.target.value);
        }
    }

    async loadLabelLots() {
        const search = this.state.labelSearch;
        const lots = await this.orm.call(MODEL, "search_label_lots", [search]);
        if (this.state.mode === "labels" && this.state.labelSearch === search) {
            this.state.labelLots = lots;
        }
        return lots;
    }

    /** The lot named exactly as the code goes straight to print; otherwise the lots found. */
    async findLabel(code) {
        browser.clearTimeout(this.searchTimeout);
        this.state.labelSearch = code.trim();
        const lots = await this.loadLabelLots();
        const exact = lots.filter((lot) => lot.exact);
        if (exact.length === 1) {
            await this.onPrintLotLabels([exact[0].id]);
        } else if (this.state.labelSearch && !lots.length) {
            this.notification.add(_t("No lot found for %s.", this.state.labelSearch), { type: "warning" });
            this.focusLabelSearch = true;
            this.render();
        }
    }

    // ------------------------------------------------------------------
    // Payments
    // ------------------------------------------------------------------

    toggleInvoice(invoice) {
        const ids = this.state.invoiceIds.includes(invoice.id)
            ? this.state.invoiceIds.filter((id) => id !== invoice.id)
            : [...this.state.invoiceIds, invoice.id];
        this.state.invoiceIds = ids;
        // Propose the amount of the invoices chosen
        const total = this.state.partner.invoices
            .filter((inv) => ids.includes(inv.id))
            .reduce((sum, inv) => sum + inv.residual, 0);
        this.state.amount = total > 0 ? this.formatInput(total) : "";
    }

    onAmountInput(value) {
        this.state.amount = value;
    }

    onMemoInput(ev) {
        this.state.memo = ev.target.value;
    }

    onSelectJournal(journalId) {
        this.state.journalId = journalId;
    }

    async onRegisterPayment() {
        const amount = this.parseNumber(this.state.amount);
        if (!(amount > 0)) {
            this.notification.add(_t("Enter the amount."), { type: "warning" });
            return;
        }
        if (!this.state.journalId) {
            this.notification.add(_t("Choose a journal."), { type: "warning" });
            return;
        }
        const payment = await this.run("register_payment", [
            {
                uuid: this.newUuid(),
                partner_id: this.state.partner.id,
                amount,
                journal_id: this.state.journalId,
                invoice_ids: this.state.invoiceIds,
                memo: this.state.memo,
            },
        ]);
        if (payment) {
            this.finishOperation({ kind: "payment", model: "account.payment", ...payment });
        }
    }

    // ------------------------------------------------------------------
    // Scanner and other screens
    // ------------------------------------------------------------------

    async onBarcodeScanned(barcode) {
        if (!["sale", "purchase", "lots", "labels"].includes(this.state.mode) || this.state.sending) {
            return;
        }
        if (this.state.mode === "labels") {
            await this.findLabel(barcode);
            return;
        }
        if (this.state.mode === "lots") {
            this.state.lotSearch = barcode;
            await this.loadLots();
            return;
        }
        if (!this.state.partner || this.state.done) {
            this.notification.add(
                _t("Choose an order in draft or start a new one first."),
                { type: "warning" }
            );
            return;
        }
        const found = await this.orm.call(MODEL, "find_by_barcode", [barcode]);
        const lots = found.lots.filter((lot) => this.productById(lot.product_id));
        if (this.state.mode === "sale" && lots.length) {
            const withStock = lots.filter((lot) => lot.available > 0);
            if (withStock.length === 1) {
                const lot = withStock[0];
                this.state.product = this.productById(lot.product_id);
                this.state.lots = [lot];
                this.onSelectLot(lot);
                return;
            }
            if (!withStock.length) {
                this.notification.add(_t("The lot %s has no stock.", barcode), { type: "warning" });
                return;
            }
        }
        const productId = lots[0]?.product_id || found.product_id;
        const product = productId && this.productById(productId);
        if (product && this.isProductAllowed(product)) {
            await this.onSelectProduct(product);
        } else {
            this.notification.add(_t("Nothing found for %s.", barcode), { type: "warning" });
        }
    }

    async onLotsChanged(payload) {
        if (payload.company_id !== this.state.data?.company_id) {
            return;
        }
        const product = this.state.product;
        if (this.state.mode === "sale" && product?.tracking && payload.product_ids.includes(product.id)) {
            await this.loadProductLots();
        } else if (this.state.mode === "lots" && !this.state.scrap) {
            await this.loadLots();
        }
    }

    // ------------------------------------------------------------------
    // Formatting
    // ------------------------------------------------------------------

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

    formatDate(value) {
        return value ? formatDate(deserializeDateTime(value)) : "";
    }
}

registry.category("actions").add("mercas_touch.screen", TouchScreen);
