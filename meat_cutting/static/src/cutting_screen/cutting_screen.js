import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatFloat } from "@web/core/utils/numbers";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { LabelEditDialog } from "./label_edit_dialog";

const SESSION_MODEL = "meat.cutting.session";
const LABEL_REPORT = "meat_cutting.action_report_meat_cutting_label";
const KEYPAD_KEYS = ["7", "8", "9", "4", "5", "6", "1", "2", "3", "0", ".", "C"];

/** Lowercase without accents, so that "jamon" finds "Jamón". */
function normalize(text) {
    return (text || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase();
}

export class CuttingScreen extends Component {
    static template = "meat_cutting.CuttingScreen";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.keypadKeys = KEYPAD_KEYS;
        const context = this.props.action.context || {};
        this.state = proxy({
            pickings: [],
            products: [],
            pickingId: context.meat_cutting_picking_id || false,
            product: null,
            bomChoice: null,
            search: "",
            session: null,
            weight: "",
            autoPrint: false,
            showKeypad: false,
            showFormats: false,
            busy: false,
        });
        onWillStart(async () => {
            if (context.meat_cutting_session_id) {
                await this.loadSession(context.meat_cutting_session_id);
            } else {
                await this.loadSelection();
            }
        });
    }

    // ---- Data loading ----

    async loadSelection() {
        const [pickings, products] = await Promise.all([
            this.orm.call(SESSION_MODEL, "get_cutting_pickings", []),
            this.orm.call(SESSION_MODEL, "get_cutting_products", [], {
                picking_id: this.state.pickingId,
            }),
        ]);
        this.state.pickings = pickings;
        this.state.products = products;
    }

    async loadSession(sessionId) {
        const session = await this.orm.call(SESSION_MODEL, "get_cutting_screen_data", [[sessionId]]);
        this.setSession(session);
    }

    setSession(session) {
        this.state.session = session;
    }

    // ---- Selection step ----

    matches(...texts) {
        const search = normalize(this.state.search.trim());
        return !search || texts.some((text) => normalize(text).includes(search));
    }

    /** Lots of the product matching the search; all of them when the product itself matches. */
    getVisibleLots(product) {
        if (this.matches(product.name)) {
            return product.lots;
        }
        return product.lots.filter((lot) => this.matches(lot.name, lot.crotal_name));
    }

    get visiblePickings() {
        return this.state.pickings.filter(
            (picking) =>
                picking.id === this.state.pickingId ||
                this.matches(picking.name, picking.partner_name, ...picking.search_terms)
        );
    }

    get visibleProducts() {
        return this.state.products.filter(
            (product) => this.matches(product.name) || this.getVisibleLots(product).length
        );
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
    }

    onSearchKeydown(ev) {
        // A scanned crotal or lot (ending with Enter) opens its product directly
        if (ev.key === "Enter") {
            const products = this.visibleProducts;
            if (products.length === 1) {
                this.onSelectProduct(products[0]);
            }
        }
    }

    clearSearch() {
        this.state.search = "";
    }


    async onSelectPicking(pickingId) {
        this.state.pickingId = this.state.pickingId === pickingId ? false : pickingId;
        this.state.product = null;
        this.state.products = await this.orm.call(SESSION_MODEL, "get_cutting_products", [], {
            picking_id: this.state.pickingId,
        });
    }

    async onSelectProduct(product) {
        const lots = this.getVisibleLots(product);
        if (product.tracking !== "none" && lots.length !== 1) {
            this.state.product = product;
            return;
        }
        await this.onSelectLot(product, lots[0]?.id || false);
    }

    async onSelectLot(product, lotId) {
        // Several BoMs are several cutting methods: the operator picks one
        if (product.boms.length > 1) {
            this.state.bomChoice = { product, lotId };
            return;
        }
        await this.startSession(product, lotId);
    }

    onBackToProducts() {
        this.state.product = null;
        this.state.bomChoice = null;
    }

    onBackFromBoms() {
        // Back to the lots of the product, or to the products
        this.state.bomChoice = null;
    }

    async startSession(product, lotId, bomId = false) {
        const sessionId = await this.orm.call(SESSION_MODEL, "start_cutting_session", [
            product.id,
            lotId,
            this.state.pickingId,
            bomId,
        ]);
        this.state.bomChoice = null;
        await this.loadSession(sessionId);
    }

    get labelFormatName() {
        const session = this.state.session;
        const format = session?.label_formats.find((format) => format.id === session.label_report_id);
        return format?.name || _t("Label format");
    }

    toggleFormats() {
        this.state.showFormats = !this.state.showFormats;
    }

    async toggleSessionFreeze() {
        const freeze = !this.state.session.freeze;
        await this.orm.call(SESSION_MODEL, "action_set_freeze", [[this.state.session.id], freeze]);
        this.state.session.freeze = freeze;
    }

    async toggleLineFreeze(line) {
        await this.orm.call("meat.cutting.line", "action_set_freeze", [[line.id], !line.freeze]);
        await this.loadSession(this.state.session.id);
    }

    async onSelectFormat(format) {
        await this.orm.call(SESSION_MODEL, "action_set_label_report", [
            [this.state.session.id],
            format.id,
        ]);
        this.state.session.label_report_id = format.id;
        this.state.showFormats = false;
    }

    async onChangeSource() {
        this.state.showFormats = false;
        this.state.session = null;
        this.state.product = null;
        this.state.bomChoice = null;
        this.state.search = "";
        this.state.weight = "";
        await this.loadSelection();
    }

    // ---- Weight ----

    parseNumber(value) {
        const number = parseFloat(String(value).replace(",", "."));
        return Number.isFinite(number) ? number : 0;
    }

    formatQty(value) {
        return formatFloat(value, { digits: [false, 3] });
    }

    onWeightInput(ev) {
        this.state.weight = ev.target.value;
    }

    onKeypad(key) {
        if (key === "C") {
            this.state.weight = "";
        } else if (key !== "." || !this.state.weight.includes(".")) {
            this.state.weight += key;
        }
    }

    toggleKeypad() {
        this.state.showKeypad = !this.state.showKeypad;
    }

    toggleAutoPrint() {
        this.state.autoPrint = !this.state.autoPrint;
    }

    // ---- Cuts ----

    async onComponentClick(component) {
        const weight = this.parseNumber(this.state.weight);
        if (weight <= 0) {
            this.notification.add(_t("Enter the weight before selecting the cut."), {
                type: "warning",
            });
            return;
        }
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const lineId = await this.orm.call(SESSION_MODEL, "action_add_line", [
                [this.state.session.id],
                component.bom_line_id,
                weight,
            ]);
            this.state.weight = "";
            await this.loadSession(this.state.session.id);
            if (this.state.autoPrint) {
                await this.printLabel(lineId);
            }
        } finally {
            this.state.busy = false;
        }
    }

    async printLabel(lineId) {
        await this.action.doAction(this.state.session?.label_report_id || LABEL_REPORT, {
            additionalContext: {
                active_model: "meat.cutting.line",
                active_id: lineId,
                active_ids: [lineId],
            },
        });
    }

    onEditLabel(line) {
        this.dialog.add(LabelEditDialog, {
            lineId: line.id,
            print: (lineId) => this.printLabel(lineId),
            onSaved: () => this.loadSession(this.state.session.id),
        });
    }

    onDeleteLine(line) {
        this.dialog.add(ConfirmationDialog, {
            body: _t("Delete %(weight)s %(uom)s of %(product)s?", {
                weight: this.formatQty(line.weight),
                uom: line.uom_name,
                product: line.product_name,
            }),
            confirmLabel: _t("Delete"),
            confirmClass: "btn-danger",
            confirm: async () => {
                await this.orm.unlink("meat.cutting.line", [line.id]);
                await this.loadSession(this.state.session.id);
            },
            cancel: () => {},
        });
    }

    // ---- Validation ----

    onValidate() {
        const session = this.state.session;
        this.dialog.add(ConfirmationDialog, {
            title: _t("Finish cutting"),
            body: _t(
                "Lots will be created for %(count)s cuts (%(weight)s) and %(qty)s %(uom)s of %(product)s will be consumed.",
                {
                    count: session.lines.length,
                    weight: this.formatQty(session.total_weight),
                    qty: this.formatQty(session.consumed_qty),
                    uom: session.uom_name,
                    product: session.product_name,
                }
            ),
            confirmLabel: _t("Validate"),
            confirm: async () => {
                const result = await this.orm.call(SESSION_MODEL, "action_validate", [[session.id]]);
                this.setSession(result);
                this.notification.add(_t("Cutting %s validated.", result.name), {
                    type: "success",
                });
            },
            cancel: () => {},
        });
    }

    async onNewSession() {
        this.state.pickingId = false;
        await this.onChangeSource();
    }

    onOpenSession() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: SESSION_MODEL,
            res_id: this.state.session.id,
            views: [[false, "form"]],
        });
    }
}

registry.category("actions").add("meat_cutting_screen", CuttingScreen);
