import { Component, onWillStart, proxy, useOnChange, useProps, usePlugin } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { isDisplayStandalone } from "@web/core/browser/feature_detection";
import { formatCurrency } from "@web/core/currency";
import { _t } from "@web/core/l10n/translation";
import {
    deserializeDate,
    deserializeDateTime,
    formatDate,
    formatDateTime,
    serializeDate,
} from "@web/core/l10n/dates";
import { normalize } from "@web/core/l10n/utils";
import { ConnectionLostError } from "@web/core/network/rpc";
import { OfflinePlugin } from "@web/core/offline/offline_plugin";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatFloat } from "@web/core/utils/numbers";
import { imageUrl } from "@web/core/utils/urls";
import { parseFloat } from "@web/views/fields/parsers";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { RouteJournal } from "./route_journal";

const { DateTime } = luxon;

const PARTNER_MODEL = "res.partner";
const ORDER_MODEL = "sale.order";
const PAYMENT_MODEL = "account.payment";
// Data prepared before this many hours ago is shown as old
const STALE_HOURS = 12;
// Images downloaded at the same time when preparing the route
const IMAGE_DOWNLOADS = 6;

/**
 * Pre-sales on the route, with or without connection.
 *
 * The route data is loaded once with connection ("Prepare route") and read from the offline
 * cache afterwards. Orders and payments are sent right away when online; if the connection is
 * lost, they are queued in the offline plugin, which sends them when it comes back.
 */
export class RouteScreen extends Component {
    static template = "sale_route_offline.RouteScreen";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.offline = usePlugin(OfflinePlugin);
        this.pwa = useService("pwa");
        // The home menu of Odoo Enterprise; Community has none
        this.homeMenu = "home_menu" in this.env.services ? useService("home_menu") : null;
        this.journal = new RouteJournal();
        this.state = proxy({
            // false (main menu), "customers", "customer", "order", "catalog", "review" or "payment"
            mode: false,
            data: null,
            loadFailed: false,
            preparing: false,
            sending: false,
            search: "",
            productSearch: "",
            categoryId: false,
            customerId: false,
            order: null,
            payment: null,
            journal: this.journal.list(),
        });
        this.refreshing = null;
        onWillStart(() => this.loadRouteData());
        // The offline plugin sent the queued calls: show what reached the server
        useOnChange(
            () => [this.offline.syncingORM()],
            (syncing) => !syncing && this.refreshJournal(),
            { initialRun: false }
        );
    }

    // ---- Route data ----

    /**
     * Reads the route data from the offline cache, then from the server when there is
     * connection: the callback receives the fresh data.
     */
    async loadRouteData() {
        const orm = this.orm.cache({
            type: "disk",
            update: "always",
            callback: (data) => {
                this.setRouteData(data);
                this.refreshJournal({ refreshData: false });
            },
        });
        try {
            this.setRouteData(await orm.call(PARTNER_MODEL, "get_route_data"));
        } catch (error) {
            if (!(error instanceof ConnectionLostError)) {
                throw error;
            }
            // Offline and never prepared on this device
            this.state.loadFailed = true;
        }
    }

    setRouteData(data) {
        this.state.data = data;
        this.state.loadFailed = false;
    }

    async onPrepare() {
        if (this.offline.isOffline()) {
            this.notification.add(_t("Connect to the internet to prepare the route."), {
                type: "warning",
            });
            return;
        }
        this.state.preparing = true;
        try {
            // Skip the cached copy to get the server data; the answer replaces the cached one
            const data = await this.orm
                .cache({ type: "disk", update: "always", noCache: true })
                .call(PARTNER_MODEL, "get_route_data");
            this.setRouteData(data);
            await this.refreshJournal({ refreshData: false });
            this.notification.add(
                _t("Route ready: %s customers.", String(data.customers.length)),
                { type: "success" }
            );
            this.downloadImages(data.products);
        } catch (error) {
            if (!(error instanceof ConnectionLostError)) {
                throw error;
            }
            this.notification.add(_t("The connection was lost. Try again."), { type: "danger" });
        } finally {
            this.state.preparing = false;
        }
    }

    /**
     * Reads the route data again from the server, in the background, after an order or a
     * payment reached it: the recent orders, the debt and the invoices change. The answer
     * replaces the cached copy, so the screen also shows it offline afterwards.
     */
    refreshRouteData() {
        if (this.offline.isOffline()) {
            return Promise.resolve();
        }
        if (this.refreshing) {
            // One more time when the current one ends, with the last changes
            this.refreshAgain = true;
            return this.refreshing;
        }
        this.refreshing = this.orm.silent
            .cache({ type: "disk", update: "always", noCache: true })
            .call(PARTNER_MODEL, "get_route_data")
            .then(
                (data) => this.setRouteData(data),
                (error) => {
                    if (!(error instanceof ConnectionLostError)) {
                        throw error;
                    }
                }
            )
            .finally(() => {
                this.refreshing = null;
                if (this.refreshAgain) {
                    this.refreshAgain = false;
                    this.refreshRouteData();
                }
            });
        return this.refreshing;
    }

    /**
     * Puts the product images in the browser cache, so that the catalog shows them offline.
     * Their url changes with the product, so the browser keeps them without asking again.
     */
    async downloadImages(products) {
        const urls = products.map((product) => this.productImageUrl(product));
        const download = async () => {
            while (urls.length && !this.offline.isOffline()) {
                try {
                    await browser.fetch(urls.shift());
                } catch {
                    // Images are a nice to have: the catalog shows a placeholder without them
                }
            }
        };
        await Promise.all(Array.from({ length: IMAGE_DOWNLOADS }, download));
    }

    productImageUrl(product) {
        return imageUrl("product.product", product.id, "image_128", { unique: product.image_unique });
    }

    preparedAt() {
        return this.state.data && deserializeDateTime(this.state.data.generated_at);
    }

    isStale() {
        const preparedAt = this.preparedAt();
        return (
            !preparedAt ||
            !preparedAt.hasSame(DateTime.now(), "day") ||
            DateTime.now().diff(preparedAt, "hours").hours > STALE_HOURS
        );
    }

    // ---- Orders and payments of the tablet ----

    today() {
        return serializeDate(DateTime.now());
    }

    /**
     * Marks as synced what reached the server, and forgets the synced entries of other days.
     * If something reached the server since the last time, the route data is read again.
     */
    async refreshJournal({ refreshData = true } = {}) {
        const uuids = this.journal.list().filter((e) => !e.synced).map((e) => e.uuid);
        let status = {};
        if (uuids.length && !this.offline.isOffline()) {
            try {
                status = await this.orm.silent.call(PARTNER_MODEL, "get_route_sync_status", [uuids]);
            } catch (error) {
                if (!(error instanceof ConnectionLostError)) {
                    throw error;
                }
            }
        }
        this.journal.update(status, this.today());
        this.state.journal = this.journal.list();
        const pending = new Set(this.journal.list().filter((e) => !e.synced).map((e) => e.uuid));
        if (refreshData && uuids.some((uuid) => !pending.has(uuid))) {
            await this.refreshRouteData();
        }
    }

    pendingCount() {
        return this.state.journal.filter((entry) => !entry.synced).length;
    }

    pendingEntries(customerId) {
        return this.state.journal.filter(
            (entry) => entry.partnerId === customerId && !entry.synced && entry.kind === "payment"
        );
    }

    /** Orders of today, and older orders not sent yet. */
    customerOrders(customerId) {
        return this.state.journal.filter(
            (entry) =>
                entry.partnerId === customerId &&
                entry.kind === "order" &&
                (entry.day === this.today() || !entry.synced)
        );
    }

    async onCopyEntry(entry) {
        const text = [entry.displayName, formatDateTime(DateTime.fromMillis(entry.timeStamp))]
            .concat(entry.details || [])
            .join("\n");
        try {
            await browser.navigator.clipboard.writeText(text);
            this.notification.add(_t("Copied to the clipboard."), { type: "success" });
        } catch {
            this.notification.add(_t("The clipboard isn't available."), { type: "warning" });
        }
    }

    /**
     * Sends a call that creates or updates a record from the tablet, and keeps it in the journal.
     *
     * Online, the call is done right away, so that an error (e.g. a product that can't be sold
     * anymore) is shown while the form is still open. If the connection is lost, or there is no
     * connection, the call is queued in the offline plugin and sent when the connection is back.
     * The queue keeps one call per record: a new version of a queued order replaces the old one.
     * The server ignores a version it already has, so a call that reached the server just before
     * the connection was lost can be queued safely.
     *
     * @returns {Promise<boolean>} whether the server received it right away
     */
    async send(model, method, vals, entry) {
        let synced = false;
        if (!this.offline.isOffline()) {
            try {
                await this.orm.call(model, method, [vals]);
                synced = true;
            } catch (error) {
                if (!(error instanceof ConnectionLostError)) {
                    throw error;
                }
            }
        }
        const timeStamp = entry.timeStamp || Date.now();
        if (!synced) {
            this.offline.scheduleORM(model, method, [vals], {}, {
                id: vals.offline_uuid,
                extras: {
                    timeStamp,
                    actionName: _t("Route Sales"),
                    displayName: entry.displayName,
                },
            });
        }
        this.journal.save({
            ...entry,
            uuid: vals.offline_uuid,
            day: entry.day || this.today(),
            timeStamp,
            synced,
        });
        this.state.journal = this.journal.list();
        if (synced) {
            this.refreshRouteData();
        }
        return synced;
    }

    // ---- Navigation ----

    onOdooHome() {
        if (this.homeMenu) {
            this.homeMenu.toggle(true);
        } else {
            browser.location.href = "/odoo";
        }
    }

    /**
     * Odoo is installed as a whole, not this screen alone like other apps of the tablets: the
     * offline startup of Odoo only covers its own urls (/odoo/...).
     */
    canInstall() {
        return this.pwa.isAvailable && !isDisplayStandalone();
    }

    onInstall() {
        this.pwa.show();
    }

    onHome() {
        this.state.mode = false;
    }

    onShowCustomers() {
        this.state.mode = "customers";
        this.refreshJournal();
    }

    onSelectCustomer(customerId) {
        this.state.customerId = customerId;
        this.state.mode = "customer";
    }

    onBack() {
        const previous = {
            customers: false,
            customer: "customers",
            order: "customer",
            catalog: "order",
            review: this.state.order?.confirmed ? "customer" : "order",
            payment: "customer",
        };
        this.state.mode = previous[this.state.mode];
    }

    customer() {
        return this.state.data?.customers.find((c) => c.id === this.state.customerId);
    }

    visibleCustomers() {
        const search = normalize(this.state.search.trim());
        const customers = this.state.data?.customers || [];
        if (!search) {
            return customers;
        }
        return customers.filter((customer) =>
            normalize(`${customer.name} ${customer.city} ${customer.street} ${customer.phone}`).includes(search)
        );
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
    }

    /** Same colors as the state of the orders in the sales lists. */
    orderStateClass(order) {
        if (["draft", "sent"].includes(order.state_code)) {
            return "text-bg-info";
        }
        return order.state_code === "sale" ? "text-bg-success" : "text-bg-300";
    }

    /** Same colors as the invoice status in the list of the orders. */
    invoiceStatusClass(order) {
        return {
            invoiced: "text-bg-success",
            "to invoice": "text-bg-info",
            upselling: "text-bg-warning",
        }[order.invoice_status_code] || "text-bg-300";
    }

    formatDay(value) {
        return value ? formatDate(deserializeDateTime(value)) : "";
    }

    // ---- Debt ----

    debt(customer) {
        return customer.overdue + customer.not_due;
    }

    isOverCreditLimit(customer) {
        return customer.credit_limit !== false && customer.credit_limit > 0 && this.debt(customer) > customer.credit_limit;
    }

    // ---- Order ----

    onNewOrder() {
        const customer = this.customer();
        this.state.order = {
            uuid: crypto.randomUUID(),
            revision: 0,
            confirmed: false,
            lines: this.usualLines(customer),
        };
        this.state.productSearch = "";
        this.state.mode = "order";
    }

    usualLines(customer, exclude = new Set()) {
        return customer.usual_products
            .filter((usual) => !exclude.has(usual.product_id))
            .map((usual) => ({
                ...this.makeLine(customer, usual.product_id),
                price: usual.price,
                discount: usual.discount,
                taxPercent: usual.tax_percent,
                usualQty: usual.qty,
            }));
    }

    /**
     * Changes a quotation of the recent orders like a new one: its lines, then the usual products
     * of the customer. The version of the journal is newer, if the quotation was changed today.
     */
    onEditQuotation(order) {
        const entry = this.state.journal.find(
            (e) => e.kind === "order" && (e.uuid === order.offline_uuid || e.orderId === order.id)
        );
        if (entry) {
            this.onOpenOrder(entry);
            if (!entry.order.confirmed) {
                this.state.mode = "order";
            }
            return;
        }
        const customer = this.customer();
        const lines = order.lines.map((line) => ({
            key: `line-${line.line_id}`,
            lineId: line.line_id,
            productId: line.product_id,
            name: line.name,
            uomName: line.uom_name,
            price: line.price_unit,
            discount: line.discount,
            taxPercent: line.tax_percent,
            usualQty: 0,
            qty: line.qty,
            note: line.note || "",
            origNote: line.note || "",
        }));
        this.state.order = {
            uuid: order.offline_uuid || crypto.randomUUID(),
            revision: order.offline_revision || 0,
            orderId: order.id,
            name: order.name,
            confirmed: false,
            lines: [...lines, ...this.usualLines(customer, new Set(lines.map((l) => l.productId)))],
        };
        this.state.productSearch = "";
        this.state.mode = "order";
    }

    isQuotation(order) {
        return ["draft", "sent"].includes(order.state_code);
    }

    /** Opens an order of the journal: to change it if it is a quotation, to see it otherwise. */
    onOpenOrder(entry) {
        this.state.order = {
            uuid: entry.uuid,
            revision: entry.revision,
            confirmed: entry.order.confirmed,
            orderId: entry.orderId,
            name: entry.orderName,
            timeStamp: entry.timeStamp,
            day: entry.day,
            // Lines saved by an older version of the screen have neither key nor text
            lines: entry.order.lines.map((line) => ({
                key: line.lineId ? `line-${line.lineId}` : `product-${line.productId}`,
                note: "",
                origNote: "",
                ...line,
            })),
        };
        this.state.productSearch = "";
        this.state.mode = "review";
    }

    makeLine(customer, productId) {
        const product = this.product(productId);
        return {
            key: `product-${productId}`,
            productId,
            name: product?.name || "",
            uomName: product?.uom_name || "",
            price: this.state.data.prices[customer.price_key]?.[productId] ?? 0,
            discount: 0,
            taxPercent: this.state.data.taxes[customer.tax_key]?.[productId] ?? 0,
            usualQty: 0,
            qty: 0,
            note: "",
            origNote: "",
        };
    }

    product(productId) {
        return this.state.data.products.find((p) => p.id === productId);
    }

    orderLine(productId) {
        return this.state.order.lines.find((line) => line.productId === productId);
    }

    /** Sets the quantity of a product, adding it to the order if needed. */
    setProductQty(productId, qty) {
        qty = Math.max(qty, 0);
        const lines = this.state.order.lines;
        let line = this.orderLine(productId);
        if (!line) {
            if (!qty) {
                return;
            }
            line = { ...this.makeLine(this.customer(), productId), qty };
            lines.push(line);
            return;
        }
        line.qty = qty;
        // A product added from the catalog leaves the order with its last unit; usual ones stay
        if (!qty && !line.usualQty) {
            lines.splice(lines.indexOf(line), 1);
        }
    }

    onUseUsualQuantities() {
        for (const line of this.state.order.lines) {
            if (!line.qty && line.usualQty) {
                line.qty = line.usualQty;
            }
        }
    }

    onLineQtyChange(line, ev) {
        line.qty = Math.max(this.parseNumber(ev.target.value), 0);
        ev.target.value = line.qty ? this.formatQty(line.qty) : "";
    }

    onLineStep(line, step) {
        line.qty = Math.max((line.qty || 0) + step, 0);
    }

    onToggleLineNote(line) {
        line.showNote = !line.showNote;
    }

    onLineNoteInput(line, ev) {
        line.note = ev.target.value;
    }

    onLineDiscountChange(line, ev) {
        line.discount = Math.min(Math.max(this.parseNumber(ev.target.value), 0), 100);
        ev.target.value = this.formatQty(line.discount);
    }

    /** Estimate of the order total; the server computes the real one. */
    orderTotals(lines = this.state.order.lines) {
        let untaxed = 0;
        let tax = 0;
        for (const line of lines) {
            const subtotal = this.lineSubtotal(line);
            untaxed += subtotal;
            tax += (subtotal * line.taxPercent) / 100;
        }
        return { untaxed, tax, total: untaxed + tax };
    }

    lineSubtotal(line) {
        return line.qty * line.price * (1 - line.discount / 100);
    }

    orderedLines() {
        return this.state.order.lines.filter((line) => line.qty > 0);
    }

    lineNoteChanged(line) {
        return line.lineId ? line.note.trim() !== line.origNote : Boolean(line.note.trim());
    }

    onReview() {
        if (this.orderedLines().length) {
            this.state.mode = "review";
        }
    }

    onEditOrder() {
        this.state.mode = "order";
    }

    /**
     * Saves the order as a quotation, or confirms it. Each save is a new version of the order,
     * sent with the same uuid.
     */
    async onSaveOrder(confirm) {
        const order = this.state.order;
        const lines = this.orderedLines();
        if (!lines.length || order.confirmed || this.state.sending) {
            return;
        }
        const customer = this.customer();
        const total = this.formatAmount(this.orderTotals(lines).total);
        const revision = order.revision + 1;
        const vals = {
            offline_uuid: order.uuid,
            revision,
            partner_id: customer.id,
            confirm,
            lines: lines.map((line) => ({
                product_id: line.productId,
                qty: line.qty,
                discount: line.discount,
                ...(line.lineId ? { line_id: line.lineId } : {}),
                // The description of a line only changes if its text changed
                ...(this.lineNoteChanged(line) ? { note: line.note.trim() } : {}),
            })),
            ...(order.orderId ? { order_id: order.orderId } : {}),
        };
        const entry = {
            kind: "order",
            partnerId: customer.id,
            orderId: order.orderId,
            orderName: order.name,
            revision,
            timeStamp: order.timeStamp,
            day: order.day,
            displayName: (order.name ? `${order.name} · ` : "") + (confirm
                ? _t("Order of %(customer)s, %(total)s", { customer: customer.name, total })
                : _t("Quotation of %(customer)s, %(total)s", { customer: customer.name, total })),
            details: lines.map(
                (line) => `${this.formatQty(line.qty)} ${line.uomName} ${line.name}` +
                    (line.discount ? ` (-${this.formatQty(line.discount)}%)` : "") +
                    (line.note.trim() ? `\n   ${line.note.trim()}` : "")
            ),
            // Every line, also the usual ones not ordered this time, to change the order later
            order: { confirmed: confirm, lines: order.lines.map((line) => ({ ...line })) },
        };
        this.state.sending = true;
        try {
            const sent = await this.send(ORDER_MODEL, "save_from_tablet", vals, entry);
            let message;
            if (confirm) {
                message = sent ? _t("Order confirmed.") : _t("Order confirmed. It will be sent when the connection is back.");
            } else {
                message = sent ? _t("Quotation saved.") : _t("Quotation saved. It will be sent when the connection is back.");
            }
            this.notification.add(message, { type: sent ? "success" : "info" });
            this.state.order = null;
            this.state.mode = "customer";
        } finally {
            this.state.sending = false;
        }
    }

    // ---- Catalog ----

    onShowCatalog() {
        this.state.productSearch = "";
        this.state.mode = "catalog";
    }

    onProductSearchInput(ev) {
        this.state.productSearch = ev.target.value;
    }

    onSelectCategory(categoryId) {
        this.state.categoryId = categoryId;
    }

    onCategorySelectChange(ev) {
        this.state.categoryId = Number(ev.target.value) || false;
    }

    catalogProducts() {
        const search = normalize(this.state.productSearch.trim());
        const categoryId = this.state.categoryId;
        return this.state.data.products.filter(
            (product) =>
                (!categoryId || product.categ_id === categoryId) &&
                (!search || normalize(`${product.name} ${product.default_code}`).includes(search))
        );
    }

    /** Categories of the catalog with their number of products, like the standard search panel. */
    catalogCategories() {
        const counts = {};
        for (const product of this.state.data.products) {
            counts[product.categ_id] = (counts[product.categ_id] || 0) + 1;
        }
        return this.state.data.categories.map((category) => ({ ...category, count: counts[category.id] || 0 }));
    }

    catalogPrice(productId) {
        return this.orderLine(productId)?.price ?? this.makeLine(this.customer(), productId).price;
    }

    catalogQty(productId) {
        return this.orderLine(productId)?.qty || 0;
    }

    onCatalogCardClick(productId) {
        if (!this.catalogQty(productId)) {
            this.setProductQty(productId, 1);
        }
    }

    onCatalogStep(productId, step) {
        this.setProductQty(productId, this.catalogQty(productId) + step);
    }

    onCatalogQtyChange(productId, ev) {
        this.setProductQty(productId, this.parseNumber(ev.target.value));
        ev.target.value = this.formatQty(this.catalogQty(productId));
    }

    onCatalogImageError(ev) {
        // Offline and not in the browser cache
        ev.target.classList.add("o_sale_route_no_image");
    }

    // ---- Payment ----

    onNewPayment() {
        this.state.payment = {
            amount: 0,
            journalId: this.state.data.journals[0]?.id || false,
            invoiceIds: [],
            memo: "",
        };
        this.state.mode = "payment";
    }

    payableInvoices() {
        return this.customer().invoices.filter((invoice) => !invoice.is_refund);
    }

    onToggleInvoice(invoice) {
        const payment = this.state.payment;
        const selected = payment.invoiceIds.includes(invoice.id);
        payment.invoiceIds = selected
            ? payment.invoiceIds.filter((id) => id !== invoice.id)
            : [...payment.invoiceIds, invoice.id];
        // Propose the total of the selected invoices
        payment.amount = this.payableInvoices()
            .filter((inv) => payment.invoiceIds.includes(inv.id))
            .reduce((sum, inv) => sum + inv.residual, 0);
    }

    onPaymentAmountChange(ev) {
        this.state.payment.amount = Math.max(this.parseNumber(ev.target.value), 0);
        ev.target.value = this.state.payment.amount ? this.formatNumber(this.state.payment.amount) : "";
    }

    onPaymentJournalChange(ev) {
        this.state.payment.journalId = Number(ev.target.value);
    }

    onPaymentMemoInput(ev) {
        this.state.payment.memo = ev.target.value;
    }

    async onSavePayment() {
        const payment = this.state.payment;
        if (!(payment.amount > 0) || !payment.journalId || this.state.sending) {
            return;
        }
        const customer = this.customer();
        const amount = this.formatAmount(payment.amount);
        const invoices = this.payableInvoices().filter((inv) => payment.invoiceIds.includes(inv.id));
        const vals = {
            offline_uuid: crypto.randomUUID(),
            partner_id: customer.id,
            amount: payment.amount,
            journal_id: payment.journalId,
            invoice_ids: payment.invoiceIds,
            memo: payment.memo.trim(),
            date: this.today(),
        };
        const entry = {
            kind: "payment",
            partnerId: customer.id,
            revision: 1,
            displayName: _t("Payment of %(customer)s, %(amount)s", { customer: customer.name, amount }),
            details: invoices.map((inv) => inv.name).concat(payment.memo.trim() ? [payment.memo.trim()] : []),
        };
        this.state.sending = true;
        try {
            const sent = await this.send(PAYMENT_MODEL, "create_from_tablet", vals, entry);
            this.notification.add(
                sent ? _t("Payment sent.") : _t("Payment saved. It will be sent when the connection is back."),
                { type: sent ? "success" : "info" }
            );
            this.state.payment = null;
            this.state.mode = "customer";
        } finally {
            this.state.sending = false;
        }
    }

    // ---- Formatting ----

    parseNumber(value) {
        try {
            return parseFloat(value || "0");
        } catch {
            return 0;
        }
    }

    formatAmount(amount, currencyId) {
        return formatCurrency(amount, currencyId || this.state.data.currency_id);
    }

    formatNumber(value) {
        return formatFloat(value, { digits: [16, 2] });
    }

    formatQty(value) {
        return formatFloat(value, { digits: [16, 3], trailingZeros: false });
    }

    formatDate(value) {
        return value ? formatDate(deserializeDate(value)) : "";
    }

    formatDateTime(value) {
        return value ? formatDateTime(deserializeDateTime(value)) : "";
    }

    formatTime(timeStamp) {
        return DateTime.fromMillis(timeStamp).toLocaleString(DateTime.TIME_SIMPLE);
    }
}

registry.category("actions").add("sale_route_offline.route", RouteScreen);
