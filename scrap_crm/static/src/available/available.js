import { Component, onWillDestroy, onWillStart, proxy, signal, useOnChange, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatFloat } from "@web/core/utils/numbers";
import { imageUrl } from "@web/core/utils/urls";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const MODEL = "scrap.crm.available";
// Time to wait after typing before searching
const SEARCH_DELAY = 300;
// Pixels to swipe to go to the next photo
const SWIPE_DISTANCE = 50;

/**
 * What is available for an opportunity, on a touch screen as the one of CAT (scrap_touch):
 *
 * - In stock: the products in stock, of a brand (the one of the opportunity by default) or of
 *   all of them, made of a scrap template (the one of the opportunity by default) or of any;
 * - Assembled: the ones in stock with the scrap template asked for (the one of the opportunity
 *   by default) still to dismantle, as a vehicle with its engine.
 *
 * A single search box looks up the name, the barcode and the references.
 */
export class ScrapCrmAvailable extends Component {
    static template = "scrap_crm.Available";
    props = useProps(standardActionServiceProps);
    galleryRef = signal.ref();

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({
            data: null,
            mode: "stock",
            query: "",
            brandId: false,
            templateId: false,
            products: [],
            counts: { stock: 0, assembled: 0 },
            // The photos of a product: {product, images, index}
            gallery: null,
        });
        // A search still to do once left, not done
        onWillDestroy(() => browser.clearTimeout(this.searchTimeout));
        // On it, for the keys
        useOnChange(
            () => [this.galleryRef()],
            (el) => el?.focus()
        );
        onWillStart(async () => {
            const leadId = this.props.action.params?.lead_id || false;
            const data = await this.orm.call(MODEL, "get_screen_data", [leadId]);
            this.state.data = data;
            this.state.brandId = data.brand_id;
            this.state.templateId = data.template_id;
            await this.load();
        });
    }

    get modes() {
        return [
            { key: "stock", name: _t("In stock"), icon: "inventory_2" },
            { key: "assembled", name: _t("Assembled"), icon: "build" },
        ];
    }

    async load() {
        const { mode, query, brandId, templateId } = this.state;
        const result = await this.orm.call(MODEL, "search_available", [mode, query, brandId || false, templateId || false]);
        // A later search may have answered first
        if (mode === this.state.mode && query === this.state.query && brandId === this.state.brandId
            && templateId === this.state.templateId) {
            this.state.products = result.products;
            this.state.counts = result.counts;
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

    async onBrand(ev) {
        this.state.brandId = parseInt(ev.target.value) || false;
        await this.load();
    }

    /** The template filters both options, with the brand. */
    async onTemplate(ev) {
        this.state.templateId = parseInt(ev.target.value) || false;
        await this.load();
    }

    onBack() {
        if (this.env.config.breadcrumbs?.length > 1) {
            this.action.restore();
        } else if (this.state.data.lead) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "crm.lead",
                res_id: this.state.data.lead.id,
                views: [[false, "form"]],
            });
        }
    }

    async onOpenProduct(product) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.template",
            res_id: product.id,
            views: [[false, "form"]],
            target: "new",
        }, { onClose: () => this.load() });
    }

    /** Its form, in a new tab of the browser */
    productUrl(product) {
        return `/odoo/product.template/${product.id}`;
    }

    async onOpenGallery(product) {
        const images = await this.orm.call(MODEL, "get_product_images", [product.id]);
        this.state.gallery = { product, images, index: 0 };
    }

    onCloseGallery() {
        this.state.gallery = null;
    }

    onGalleryMove(step) {
        const { images, index } = this.state.gallery;
        this.state.gallery.index = (index + step + images.length) % images.length;
    }

    onGalleryGo(index) {
        this.state.gallery.index = index;
    }

    onGalleryKeydown(ev) {
        const moves = { ArrowLeft: -1, ArrowRight: 1 };
        if (ev.key === "Escape") {
            ev.stopPropagation();
            this.onCloseGallery();
        } else if (ev.key in moves && this.state.gallery.images.length > 1) {
            this.onGalleryMove(moves[ev.key]);
        }
    }

    onGalleryTouchStart(ev) {
        this.touchX = ev.changedTouches[0].clientX;
    }

    onGalleryTouchEnd(ev) {
        const distance = ev.changedTouches[0].clientX - this.touchX;
        if (Math.abs(distance) > SWIPE_DISTANCE && this.state.gallery.images.length > 1) {
            this.onGalleryMove(distance < 0 ? 1 : -1);
        }
    }

    async onGalleryProduct() {
        const { product } = this.state.gallery;
        this.onCloseGallery();
        await this.onOpenProduct(product);
    }

    galleryImage(image, field) {
        return imageUrl(image.model, image.id, field, { unique: image.unique });
    }

    productImage(product) {
        return imageUrl("product.product", product.product_id, "image_128", { unique: product.image_unique });
    }

    formatQty(qty) {
        return formatFloat(qty, { digits: [false, 3], trailingZeros: false });
    }
}

registry.category("actions").add("scrap_crm.available", ScrapCrmAvailable);
