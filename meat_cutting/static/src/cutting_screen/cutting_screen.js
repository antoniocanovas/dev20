import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { post } from "@web/core/network/http_service";
import { redirect } from "@web/core/utils/urls";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { formatFloat } from "@web/core/utils/numbers";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { LabelEditDialog } from "./label_edit_dialog";
import { PackageInfoDialog } from "./package_info_dialog";

const SESSION_MODEL = "meat.cutting.session";
const PICKING_MODEL = "stock.picking";
const LABEL_REPORT = "meat_cutting.action_report_meat_cutting_label";
const BOX_LABEL_REPORT = "meat_cutting.action_report_meat_box_label";
const PICKING_BOX_LABEL_REPORT = "meat_cutting.action_report_picking_meat_box_label";
// Path of the screen, also the start of the app installed on the tablet
const APP_PATH = "meat-cutting";

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
        this.pwa = useService("pwa");
        this.ui = useService("ui");
        // The home menu of Odoo Enterprise; Community has none
        this.homeMenu = "home_menu" in this.env.services ? useService("home_menu") : null;
        // A scanner in keyboard mode, without having to focus the search first
        useBus(useService("barcode").bus, "barcode_scanned", (ev) => this.onBarcodeScanned(ev.detail.barcode));
        this.pwaInstallUrl = `/scoped_app?app_id=meat_cutting&path=scoped_app/${APP_PATH}`;
        this.modes = [
            { key: "receipt", name: _t("Receipts"), icon: "local_shipping", help: _t("Cut the received carcasses") },
            { key: "cutting", name: _t("Cutting"), icon: "content_cut", help: _t("Cut a package in stock again") },
            { key: "preparation", name: _t("Preparation"), icon: "fork_right", help: _t("Split a package with a presentation") },
            { key: "production", name: _t("Production"), icon: "factory", help: _t("Make a product from ingredients") },
            { key: "packing", name: _t("Packing"), icon: "package_2", help: _t("Put the pieces of a delivery in boxes") },
            { key: "labels", name: _t("Labels"), icon: "label", help: _t("Print a damaged label again") },
        ];
        const context = this.props.action.context || {};
        this.state = proxy({
            // The main menu until a process is chosen; a receipt opens its cutting
            mode: context.meat_cutting_picking_id ? "receipt" : false,
            // Receipts
            pickings: [],
            products: [],
            pickingId: context.meat_cutting_picking_id || false,
            product: null,
            bomChoice: null,
            // Cutting, preparation and production: family, then package or product
            families: [],
            familyId: false,
            packages: [],
            productionProducts: [],
            // Production: ingredient whose stock is shown
            ingredient: null,
            ingredientPackages: [],
            // Production: packages of any ingredient found by a scan
            foundPackages: [],
            presentationId: false,
            // Packing
            deliveries: [],
            packing: null,
            boxId: false,
            newBox: null,
            // Labels: packages and boxes found, and the one whose label is printed again
            relabelResults: [],
            relabelSearched: false,
            relabel: null,
            relabelFormatKey: false,
            search: "",
            session: null,
            weight: "",
            autoPrint: false,
            showFormats: false,
            busy: false,
        });
        onWillStart(async () => {
            if (context.meat_cutting_session_id) {
                await this.loadSession(context.meat_cutting_session_id);
                this.state.mode = this.state.session.mode;
            } else if (this.state.mode) {
                await this.loadSelection();
            }
        });
    }

    // ---- Data loading ----

    async loadSelection() {
        const mode = this.state.mode;
        if (!mode) {
            return;
        }
        if (mode === "receipt") {
            const [pickings, products] = await Promise.all([
                this.orm.call(SESSION_MODEL, "get_cutting_pickings", []),
                this.orm.call(SESSION_MODEL, "get_cutting_products", [], {
                    picking_id: this.state.pickingId,
                }),
            ]);
            this.state.pickings = pickings;
            this.state.products = products;
        } else if (mode === "labels") {
            if (this.state.relabel) {
                await this.loadRelabel(this.state.relabel.id);
            }
        } else if (mode === "packing") {
            this.state.deliveries = await this.orm.call(PICKING_MODEL, "get_meat_packing_pickings", []);
        } else {
            this.state.families = await this.orm.call(SESSION_MODEL, "get_cutting_families", [mode]);
            if (this.state.familyId) {
                await this.loadFamily();
            }
        }
    }

    async loadFamily() {
        if (this.state.mode === "production") {
            this.state.productionProducts = await this.orm.call(SESSION_MODEL, "get_production_products", [
                this.state.familyId,
            ]);
        } else {
            this.state.packages = await this.orm.call(SESSION_MODEL, "get_cutting_packages", [
                this.state.mode,
                this.state.familyId,
            ]);
        }
    }

    // ---- Mode ----

    get currentMode() {
        return this.modes.find((mode) => mode.key === this.state.mode);
    }

    get searchPlaceholder() {
        if (this.state.packing) {
            return _t("Scan or type a package");
        }
        return {
            receipt: _t("Receipt, product, lot or crotal"),
            cutting: _t("Product, package, lot or crotal"),
            preparation: _t("Product, package, lot or crotal"),
            production: _t("Product"),
            packing: _t("Delivery or customer; scan a package"),
            labels: _t("Scan the label, or type a package, lot or box"),
        }[this.state.mode];
    }

    async onSelectMode(mode) {
        if (this.state.busy) {
            return;
        }
        this.state.mode = mode;
        this.state.familyId = false;
        this.state.packing = null;
        this.state.boxId = false;
        this.state.newBox = null;
        this.state.relabel = null;
        this.state.relabelResults = [];
        this.state.relabelSearched = false;
        this.state.busy = true;
        try {
            await this.onChangeSource();
        } finally {
            this.state.busy = false;
        }
    }

    // ---- Main menu ----

    /** Back to Odoo, as the Barcode app does. */
    onOdooHome() {
        if (this.homeMenu) {
            this.homeMenu.toggle(true);
        } else {
            browser.location.href = "/odoo";
        }
    }

    async onLogout() {
        const redirectPart = this.pwa.isScopedApp ? "scoped_app" : "/odoo";
        const url = await post(
            `/web/session/logout?redirect=${redirectPart}/${APP_PATH}`,
            { csrf_token: odoo.csrf_token },
            "url"
        );
        redirect(url);
    }

    /** A label scanned with the reader on the main menu is printed again. */
    async onHomeScan(barcode) {
        if (!barcode || this.state.busy) {
            return;
        }
        await this.onSelectMode("labels");
        this.state.search = barcode;
        await this.onRelabelSearch();
    }

    /** A scan out of an input: like typing it in the search and pressing Enter. */
    async onBarcodeScanned(barcode) {
        if (this.state.busy) {
            return;
        }
        if (!this.state.mode) {
            await this.onHomeScan(barcode);
        } else if (!this.state.session || this.showIngredientSearch) {
            this.state.search = barcode;
            this.onSearchKeydown({ key: "Enter" });
        }
    }

    /** Back to the main menu; a session in progress is kept to resume it. */
    async onHome() {
        await this.onSelectMode(false);
    }

    async loadSession(sessionId) {
        const session = await this.orm.call(SESSION_MODEL, "get_cutting_screen_data", [[sessionId]]);
        this.setSession(session);
    }

    setSession(session) {
        this.state.session = session;
        const presentations = session.presentations || [];
        if (!presentations.some((presentation) => presentation.id === this.state.presentationId)) {
            this.state.presentationId = presentations[0]?.id || false;
        }
        if (this.state.ingredient) {
            this.state.ingredient = session.components.find(
                (component) => component.product_id === this.state.ingredient.product_id
            );
        }
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

    get visiblePackages() {
        return this.state.packages.filter((pack) =>
            this.matches(pack.product_name, pack.default_code, pack.package_name, pack.lot_name, pack.crotal_name)
        );
    }

    get visibleProductionProducts() {
        return this.state.productionProducts.filter((product) => this.matches(product.name));
    }

    /** Production: packages of the ingredient matching the search. A scanned
     * label (GS1) is longer than the lot or package it carries: it matches
     * when it contains it. */
    get visibleIngredientPackages() {
        const search = normalize(this.state.search.trim());
        return this.state.ingredientPackages.filter(
            (pack) =>
                this.matches(pack.product_name, pack.default_code, pack.package_name, pack.lot_name, pack.crotal_name) ||
                [pack.package_name, pack.lot_name].some((name) => name && search.includes(normalize(name)))
        );
    }

    get showIngredientSearch() {
        const session = this.state.session;
        return session?.mode === "production" && session.state === "draft";
    }

    get visibleDeliveries() {
        return this.state.deliveries.filter((delivery) =>
            this.matches(delivery.name, delivery.partner_name, delivery.origin)
        );
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
        this.state.foundPackages = [];
    }

    onSearchKeydown(ev) {
        if (ev.key !== "Enter") {
            return;
        }
        // A scanned crotal, lot or package (ending with Enter) opens it directly
        if (this.state.mode === "labels") {
            this.onRelabelSearch();
        } else if (this.showIngredientSearch) {
            this.onFindIngredientPackage();
        } else if (this.state.mode === "packing" && this.state.packing) {
            this.onScanPackage();
        } else if (this.state.mode === "receipt") {
            const products = this.visibleProducts;
            if (products.length === 1) {
                this.onSelectProduct(products[0]);
            }
        } else if (["cutting", "preparation"].includes(this.state.mode) && this.state.familyId) {
            const packages = this.visiblePackages;
            if (packages.length === 1) {
                this.onSelectPackage(packages[0]);
            }
        }
    }

    clearSearch() {
        this.state.search = "";
        this.state.foundPackages = [];
    }


    // ---- Selection by family (cutting, preparation, production) ----

    async onSelectFamily(familyId) {
        this.state.familyId = familyId;
        this.state.search = "";
        await this.loadFamily();
    }

    onBackToFamilies() {
        this.state.familyId = false;
        this.state.packages = [];
        this.state.productionProducts = [];
        this.state.bomChoice = null;
    }

    async onSelectPackage(pack, bomId = false) {
        // Several BoMs are several cutting methods: the operator picks one
        if (this.state.mode === "cutting" && !bomId && pack.boms.length > 1) {
            this.state.bomChoice = { pack, boms: pack.boms, name: pack.product_name };
            return;
        }
        const sessionId = await this.orm.call(SESSION_MODEL, "start_package_session", [
            this.state.mode,
            pack.package_id,
            pack.product_id,
            bomId,
        ]);
        this.state.bomChoice = null;
        await this.loadSession(sessionId);
    }

    async onSelectProductionProduct(product, bomId = false) {
        if (!bomId && product.boms.length > 1) {
            this.state.bomChoice = { productionProduct: product, boms: product.boms, name: product.name };
            return;
        }
        const sessionId = await this.orm.call(SESSION_MODEL, "start_production_session", [product.id, bomId]);
        this.state.bomChoice = null;
        await this.loadSession(sessionId);
    }

    onSelectBom(bom) {
        const choice = this.state.bomChoice;
        if (choice.pack) {
            return this.onSelectPackage(choice.pack, bom.id);
        } else if (choice.productionProduct) {
            return this.onSelectProductionProduct(choice.productionProduct, bom.id);
        }
        return this.startSession(choice.product, choice.lotId, bom.id);
    }

    get bomChoiceBoms() {
        const choice = this.state.bomChoice;
        return choice.boms || choice.product.boms;
    }

    get bomChoiceName() {
        const choice = this.state.bomChoice;
        return choice.name || choice.product.name;
    }

    // ---- Receipts ----

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
        this.state.ingredient = null;
        this.state.ingredientPackages = [];
        this.state.foundPackages = [];
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

    toggleAutoPrint() {
        this.state.autoPrint = !this.state.autoPrint;
    }

    // ---- Cuts ----

    async onComponentClick(component) {
        await this.addLine(component.bom_line_id);
    }

    /** Weigh a cut of the BoM, a prepared package or the product made. */
    async addLine(bomLineId = false) {
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
                bomLineId,
                weight,
                ["preparation", "production"].includes(this.state.session.mode) ? this.state.presentationId : false,
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

    // ---- Preparation: presentations in carousel ----

    get presentationName() {
        const presentations = this.state.session?.presentations || [];
        return presentations.find((p) => p.id === this.state.presentationId)?.name || _t("No presentation");
    }

    /** Next presentation of the list, back to the first one after the last. */
    nextPresentation(presentationId) {
        const presentations = this.state.session.presentations;
        const index = presentations.findIndex((p) => p.id === presentationId);
        return presentations[(index + 1) % presentations.length]?.id || false;
    }

    rotatePresentation() {
        if (!this.state.session) {
            return;
        }
        this.state.presentationId = this.nextPresentation(this.state.presentationId);
    }

    async rotateLinePresentation(line) {
        await this.orm.call("meat.cutting.line", "action_set_presentation", [
            [line.id],
            this.nextPresentation(line.presentation_id),
        ]);
        await this.loadSession(this.state.session.id);
    }

    get preparationLeftQty() {
        const session = this.state.session;
        return session.available_qty - session.total_weight;
    }

    // ---- Production: ingredients ----

    /** The weight typed is the quantity to make: the ingredients are recommended from it. */
    async onSetProductionQty() {
        const qty = this.parseNumber(this.state.weight);
        if (qty <= 0) {
            this.notification.add(_t("Type the quantity to make, then press here."), { type: "warning" });
            return;
        }
        await this.orm.call(SESSION_MODEL, "action_set_production_qty", [[this.state.session.id], qty]);
        this.state.weight = "";
        await this.loadSession(this.state.session.id);
    }

    /** Quantity of the ingredient still to add to reach the recommended one. */
    ingredientMissingQty(component) {
        return Math.max(component.recommended_qty - component.weighed_qty, 0);
    }

    /** Used, up to the recommended quantity when there is one. */
    ingredientDone(component) {
        return Boolean(component.weighed_count) && (!component.recommended_qty || !this.ingredientMissingQty(component));
    }

    ingredientProgress(component) {
        return Math.min(Math.round((100 * component.weighed_qty) / component.recommended_qty), 100);
    }

    async onSelectIngredient(component) {
        this.state.search = "";
        this.state.foundPackages = [];
        if (this.state.ingredient?.product_id === component.product_id) {
            this.state.ingredient = null;
            return;
        }
        this.state.ingredient = component;
        this.state.ingredientPackages = await this.orm.call(SESSION_MODEL, "get_ingredient_packages", [
            [this.state.session.id],
            component.product_id,
        ]);
    }

    /** A package tile: the source of the session, or an ingredient used. */
    onPackageClick(pack) {
        if (this.state.session) {
            return this.onSelectIngredientPackage(pack);
        }
        return this.onSelectPackage(pack);
    }

    onPackageInfo(pack) {
        this.dialog.add(PackageInfoDialog, { pack });
    }

    /** A package typed or scanned: of the ingredient shown, else of any
     * ingredient of the recipe. A single one is used at once. */
    async onFindIngredientPackage() {
        const text = this.state.search.trim();
        if (!text || this.state.busy) {
            return;
        }
        let packages = this.state.ingredient ? this.visibleIngredientPackages : [];
        if (packages.length !== 1) {
            packages = await this.orm.call(SESSION_MODEL, "find_ingredient_packages", [
                [this.state.session.id],
                text,
            ]);
        }
        if (packages.length === 1) {
            await this.onSelectIngredientPackage(packages[0]);
        } else if (packages.length) {
            this.state.ingredient = null;
            this.state.foundPackages = packages;
        } else {
            this.notification.add(_t("No package matches."), { type: "warning" });
        }
    }

    /** Use the weight typed of the package, or all of it without weight. */
    async onSelectIngredientPackage(pack) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call(SESSION_MODEL, "action_add_consumption", [
                [this.state.session.id],
                pack.product_id,
                this.parseNumber(this.state.weight),
            ], {
                package_id: pack.package_id,
                lot_id: pack.lot_id,
                location_id: pack.location_id,
            });
            this.state.weight = "";
            this.state.search = "";
            this.state.foundPackages = [];
            await this.loadSession(this.state.session.id);
            // The ingredient of the package used stays shown, also when found by a scan
            this.state.ingredient = this.state.session.components.find(
                (component) => component.product_id === pack.product_id
            ) || null;
            this.state.ingredientPackages = await this.orm.call(SESSION_MODEL, "get_ingredient_packages", [
                [this.state.session.id],
                pack.product_id,
            ]);
        } finally {
            this.state.busy = false;
        }
    }

    onDeleteConsumption(consumption) {
        this.dialog.add(ConfirmationDialog, {
            body: _t("Delete %(weight)s %(uom)s of %(product)s?", {
                weight: this.formatQty(consumption.weight),
                uom: consumption.uom_name,
                product: consumption.product_name,
            }),
            confirmLabel: _t("Delete"),
            confirmClass: "btn-danger",
            confirm: async () => {
                await this.orm.unlink("meat.cutting.consumption", [consumption.id]);
                await this.loadSession(this.state.session.id);
                if (this.state.ingredient) {
                    this.state.ingredientPackages = await this.orm.call(
                        SESSION_MODEL,
                        "get_ingredient_packages",
                        [[this.state.session.id], this.state.ingredient.product_id]
                    );
                }
            },
            cancel: () => {},
        });
    }

    formatDate(value) {
        return value ? value.slice(0, 10) : "";
    }

    // ---- Labels: print a damaged label again ----

    async onRelabelSearch() {
        const text = this.state.search.trim();
        if (!text || this.state.busy) {
            return;
        }
        const results = await this.orm.call("stock.package", "meat_relabel_search", [text]);
        this.state.search = "";
        if (results.length === 1) {
            await this.onSelectRelabel(results[0]);
            return;
        }
        this.state.relabel = null;
        this.state.relabelResults = results;
        this.state.relabelSearched = true;
    }

    async loadRelabel(packageId) {
        const data = await this.orm.call("stock.package", "get_meat_relabel_data", [[packageId]]);
        this.state.relabel = data;
        if (!data.formats.some((format) => format.key === this.state.relabelFormatKey)) {
            this.state.relabelFormatKey = data.formats[0]?.key || false;
        }
    }

    async onSelectRelabel(pack) {
        this.state.relabelFormatKey = false;
        await this.loadRelabel(pack.id);
    }

    get relabelFormat() {
        return this.state.relabel?.formats.find((format) => format.key === this.state.relabelFormatKey);
    }

    onSelectRelabelFormat(format) {
        this.state.relabelFormatKey = format.key;
    }

    async onRelabelPrint() {
        const format = this.relabelFormat;
        await this.action.doAction(format.report_id, {
            additionalContext: { active_model: format.model, active_id: format.res_ids[0], active_ids: format.res_ids },
        });
    }

    onRelabelEdit() {
        const format = this.relabelFormat;
        this.dialog.add(LabelEditDialog, {
            lineId: format.edit_id,
            model: format.edit_model,
            kind: format.edit_kind || "",
            print: () => this.onRelabelPrint(),
            onSaved: () => this.loadRelabel(this.state.relabel.id),
        });
    }

    onBackFromRelabel() {
        this.state.relabel = null;
    }

    // ---- Packing ----

    async loadPacking(pickingId) {
        this.state.packing = await this.orm.call(PICKING_MODEL, "get_meat_packing_data", [[pickingId]]);
        const boxes = this.state.packing.boxes;
        if (this.state.boxId && !boxes.some((box) => box.id === this.state.boxId) && !this.state.newBox) {
            this.state.boxId = false;
        }
    }

    async onSelectDelivery(delivery) {
        this.state.search = "";
        this.state.boxId = false;
        this.state.newBox = null;
        await this.loadPacking(delivery.id);
    }

    async onBackToDeliveries() {
        this.state.packing = null;
        this.state.boxId = false;
        this.state.newBox = null;
        await this.loadSelection();
    }

    get packingBoxes() {
        const boxes = [...this.state.packing.boxes];
        // A new box is listed until something is put in it
        if (this.state.newBox && !boxes.some((box) => box.id === this.state.newBox.id)) {
            boxes.push({ ...this.state.newBox, count: 0, weight: 0 });
        }
        return boxes;
    }

    async onNewBox() {
        const box = await this.orm.call(PICKING_MODEL, "action_meat_new_box", [[this.state.packing.id]]);
        this.state.newBox = box;
        this.state.boxId = box.id;
    }

    onSelectBox(box) {
        this.state.boxId = box.id;
    }

    async onToggleLine(line) {
        if (this.state.busy) {
            return;
        }
        if (!line.box_id && !this.state.boxId) {
            await this.onNewBox();
        }
        this.state.busy = true;
        try {
            await this.orm.call(PICKING_MODEL, "action_meat_toggle_box", [
                [this.state.packing.id],
                line.id,
                this.state.boxId,
            ]);
            await this.loadPacking(this.state.packing.id);
        } finally {
            this.state.busy = false;
        }
    }

    async onScanPackage() {
        const barcode = this.state.search.trim();
        if (!barcode || this.state.busy) {
            return;
        }
        if (!this.state.boxId) {
            await this.onNewBox();
        }
        this.state.busy = true;
        try {
            await this.orm.call(PICKING_MODEL, "action_meat_scan_package", [
                [this.state.packing.id],
                barcode,
                this.state.boxId,
            ]);
            this.state.search = "";
            await this.loadPacking(this.state.packing.id);
        } finally {
            this.state.busy = false;
        }
    }

    async printBoxLabel(box) {
        await this.action.doAction(BOX_LABEL_REPORT, {
            additionalContext: { active_model: "stock.package", active_id: box.id, active_ids: [box.id] },
        });
    }

    async printAllBoxLabels() {
        const pickingId = this.state.packing.id;
        await this.action.doAction(PICKING_BOX_LABEL_REPORT, {
            additionalContext: { active_model: PICKING_MODEL, active_id: pickingId, active_ids: [pickingId] },
        });
    }

    async onValidateDelivery() {
        const pickingId = this.state.packing.id;
        const result = await this.orm.call(PICKING_MODEL, "button_validate", [[pickingId]]);
        const done = async () => {
            await this.loadPacking(pickingId);
            if (this.state.packing.state === "done") {
                this.notification.add(_t("Delivery %s validated.", this.state.packing.name), { type: "success" });
                await this.onBackToDeliveries();
            }
        };
        if (result && typeof result === "object") {
            // E.g. the backorder wizard, when a piece is missing
            await this.action.doAction(result, { onClose: done });
        } else {
            await done();
        }
    }

    onOpenDelivery() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: PICKING_MODEL,
            res_id: this.state.packing.id,
            views: [[false, "form"]],
        });
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

    get validationMessage() {
        const session = this.state.session;
        const values = {
            count: session.lines.length,
            weight: this.formatQty(session.total_weight),
            qty: this.formatQty(session.consumed_qty),
            uom: session.uom_name,
            product: session.product_name,
            package: session.package_name,
            ingredients: session.consumptions.length,
        };
        if (session.mode === "preparation") {
            return _t(
                "%(count)s packages (%(weight)s %(uom)s) will be made from %(package)s; the rest stays in it.",
                values
            );
        } else if (session.mode === "production") {
            return _t(
                "%(count)s packages of %(product)s (%(weight)s %(uom)s) will be made with %(ingredients)s ingredients (%(qty)s).",
                values
            );
        }
        return _t(
            "Lots will be created for %(count)s cuts (%(weight)s) and %(qty)s %(uom)s of %(product)s will be consumed.",
            values
        );
    }

    onValidate() {
        const session = this.state.session;
        const unused = session.mode === "production" ? session.components.filter((c) => !c.weighed_count) : [];
        if (unused.length) {
            this.notification.add(
                _t("Use every ingredient of the recipe before finishing. Not used: %s.",
                    unused.map((component) => component.name).join(", ")),
                { type: "danger" }
            );
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Finish"),
            body: this.validationMessage,
            confirmLabel: _t("Validate"),
            confirm: async () => {
                const result = await this.orm.call(SESSION_MODEL, "action_validate", [[session.id]]);
                this.setSession(result);
                this.notification.add(_t("%s validated.", result.name), {
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
