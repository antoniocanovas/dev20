import { Component, onWillStart, onWillUnmount, proxy, useListener, useProps, usePlugin } from "@odoo/owl";
import { BarcodePlugin } from "@barcodes/barcode_plugin";
import { BusPlugin } from "@bus/services/bus_plugin";
import { browser } from "@web/core/browser/browser";
import { isDisplayStandalone } from "@web/core/browser/feature_detection";
import { formatCurrency } from "@web/core/currency";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime, formatDate } from "@web/core/l10n/dates";
import { normalize } from "@web/core/l10n/utils";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { formatFloat } from "@web/core/utils/numbers";
import { imageUrl } from "@web/core/utils/urls";
import { parseFloat } from "@web/views/fields/parsers";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { TouchNumpad } from "./touch_numpad";

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
        this.pwa = useService("pwa");
        // The home menu of Odoo Enterprise; Community has none
        this.homeMenu = "home_menu" in this.env.services ? useService("home_menu") : null;
        this.modes = [
            { key: "sale", fkey: "F1", name: _t("Sale"), icon: "storefront", help: _t("Sell and deliver with lots and boxes") },
            { key: "purchase", fkey: "F2", name: _t("Purchase"), icon: "local_shipping", help: _t("Buy and receive, with new lots and labels") },
            { key: "boxes", fkey: "F3", name: _t("Boxes"), icon: "inventory_2", help: _t("Boxes given back by customers or to suppliers") },
            { key: "lots", fkey: "F4", name: _t("Lots"), icon: "widgets", help: _t("Stock of the lots, scrap and settlement") },
            { key: "payment", fkey: "F5", name: _t("Payments"), icon: "payments", help: _t("Collect the invoices of a customer") },
        ];
        this.state = proxy({
            // false (main menu) or the key of a mode
            mode: false,
            data: null,
            sending: false,
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
            // Payments
            invoiceIds: [],
            amount: "",
            journalId: false,
            memo: "",
        });
        this.searchTimeout = null;

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
        this.resetOperation();
        this.state.partner = null;
        this.state.partnerSearch = "";
        this.state.partners = [];
        this.state.mode = mode;
        if (mode === "lots") {
            await this.loadLots();
        } else {
            await this.searchPartners();
        }
    }

    resetOperation() {
        this.state.product = null;
        this.state.lots = [];
        this.state.entry = null;
        this.state.lines = [];
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
        this.operationUuid = null;
    }

    onBack() {
        if (this.state.sending) {
            return;
        }
        if (this.state.entry) {
            this.state.entry = null;
            if (!this.state.lots.length) {
                this.state.product = null;
            }
        } else if (this.state.product) {
            this.state.product = null;
            this.state.lots = [];
        } else if (this.state.scrap) {
            this.state.scrap = null;
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
        const partner = this.state.partner;
        this.resetOperation();
        this.state.partner = partner;
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
            // Field written by the keypad
            field: "qty",
        };
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

    numpadValue() {
        const entry = this.state.entry;
        return entry.field === "boxQty" ? String(entry.boxQty || "") : entry[entry.field];
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
    }

    onEntryState(ev) {
        const stateId = parseInt(ev.target.value, 10) || false;
        this.state.entry.originStateId = stateId;
        const state = this.state.data.origin.states.find((s) => s.id === stateId);
        if (state) {
            this.state.entry.originCountryId = state.country_id;
        }
    }

    originStates() {
        const countryId = this.state.entry?.originCountryId;
        return this.state.data.origin.states.filter((state) => !countryId || state.country_id === countryId);
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
        };
        if (entry.line) {
            Object.assign(entry.line, values);
        } else {
            this.state.lines.push({ key: `${Date.now()}-${this.state.lines.length}`, ...values });
        }
        this.state.entry = null;
        this.state.product = null;
        this.state.lots = [];
    }

    onEditLine(line) {
        if (this.state.sending) {
            return;
        }
        this.state.product = line.product;
        this.state.lots = line.lot ? [line.lot] : [];
        this.openEntry(line.product, line.lot, line);
    }

    onRemoveLine(line) {
        this.state.lines = this.state.lines.filter((l) => l !== line);
        if (this.state.entry?.line === line) {
            this.state.entry = null;
            this.state.product = null;
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
        if (!this.state.lines.length) {
            return;
        }
        const result = await this.run("sell", [
            {
                uuid: this.newUuid(),
                partner_id: this.state.partner.id,
                lines: this.state.lines.map((line) => ({
                    product_id: line.product.id,
                    qty: line.qty,
                    price_unit: line.price,
                    ...(line.lot ? { lot_id: line.lot.id } : {}),
                    box_qty: line.boxQty,
                    ...(line.boxProductId ? { box_product_id: line.boxProductId } : {}),
                    ...(line.note ? { note: line.note } : {}),
                })),
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
        if (!this.state.lines.length) {
            return;
        }
        const result = await this.run("purchase", [
            {
                uuid: this.newUuid(),
                partner_id: this.state.partner.id,
                lines: this.state.lines.map((line) => ({
                    product_id: line.product.id,
                    qty: line.qty,
                    price_unit: line.price,
                    box_qty: line.boxQty,
                    ...(line.boxProductId ? { box_product_id: line.boxProductId } : {}),
                    ...(line.originCountryId ? { origin_country_id: line.originCountryId } : {}),
                    ...(line.originStateId ? { origin_state_id: line.originStateId } : {}),
                    firm: line.firm,
                    ...(line.lotName ? { lot_name: line.lotName } : {}),
                    ...(line.note ? { note: line.note } : {}),
                })),
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

    async onPrint(kind) {
        const done = this.state.done;
        const action = await this.orm.call(MODEL, "get_print_action", [done.model, done.id, kind]);
        await this.action.doAction(action);
    }

    onNewOperation() {
        this.state.done = null;
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
        if (!["sale", "purchase", "lots"].includes(this.state.mode) || this.state.sending) {
            return;
        }
        if (this.state.mode === "lots") {
            this.state.lotSearch = barcode;
            await this.loadLots();
            return;
        }
        if (!this.state.partner || this.state.done) {
            this.notification.add(_t("Choose the customer or supplier first."), { type: "warning" });
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

    formatDate(value) {
        return value ? formatDate(deserializeDateTime(value)) : "";
    }
}

registry.category("actions").add("mercas_touch.screen", TouchScreen);
