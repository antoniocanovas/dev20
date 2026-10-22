from markupsafe import Markup

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_amount, format_date, formatLang


class StockLot(models.Model):
    _inherit = "stock.lot"

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Supplier",
        index=True,
    )
    origin_country_id = fields.Many2one(
        comodel_name="res.country",
        string="Country of Origin",
    )
    origin_state_id = fields.Many2one(
        comodel_name="res.country.state",
        string="State of Origin",
        domain="[('country_id', '=', origin_country_id)]",
    )
    purchase_line_ids = fields.One2many(
        comodel_name="purchase.order.line",
        inverse_name="lot_id",
        string="Purchase Lines",
    )
    sale_line_ids = fields.One2many(
        comodel_name="sale.order.line",
        inverse_name="lot_id",
        string="Sale Lines",
    )
    supplier_invoice_line_ids = fields.One2many(
        comodel_name="account.move.line",
        inverse_name="lot_id",
        string="Supplier Invoice Lines",
        domain=[("move_id.move_type", "in", ["in_invoice", "in_refund"])],
    )
    customer_invoice_line_ids = fields.One2many(
        comodel_name="account.move.line",
        inverse_name="lot_id",
        string="Customer Invoice Lines",
        domain=[("move_id.move_type", "in", ["out_invoice", "out_refund"])],
    )
    scrap_line_ids = fields.Many2many(
        comodel_name="stock.move",
        compute="_compute_scrap_line_ids",
        string="Scraps",
    )
    stock_move_line_ids = fields.One2many(
        comodel_name="stock.move.line",
        inverse_name="lot_id",
        string="Stock Moves",
    )

    # ── Settlement ─────────────────────────────────────────────────────────────

    purchase_kg = fields.Float(
        string="Purchased",
        compute="_compute_purchase_kg",
        digits=(16, 3),
    )
    sale_kg = fields.Float(
        string="Sold",
        compute="_compute_sale_fields",
        digits=(16, 3),
    )
    sale_amount = fields.Float(
        string="Sold Amount",
        compute="_compute_sale_fields",
        digits=(16, 2),
    )
    scrap_kg = fields.Float(
        string="Scrapped",
        compute="_compute_scrap_kg",
        digits=(16, 3),
    )
    mercas_sale_classification = fields.Html(
        string="Sales by Quality and Size",
        compute="_compute_mercas_sale_classification",
        sanitize=False,
        help="Delivered sales of the lot by quality and size: quantity, "
             "amount and average price. Empty when no sale has them.",
    )
    completed = fields.Boolean(
        string="Completed",
        compute="_compute_completed",
        store=True,
    )
    mercas_firm_negotiation = fields.Boolean(
        string="Firm Negotiation",
        copy=False,
        tracking=True,
        help=(
            "The supplier is paid in full for what was received of this "
            "lot, regardless of what was sold, instead of settling by sale. "
            "Takes its initial value from the source purchase line. Only an "
            "Accounting Manager can change it, and only while the lot has "
            "no firm invoicing recorded."
        ),
    )
    can_edit_firm_negotiation = fields.Boolean(
        compute="_compute_can_edit_firm_negotiation",
    )
    received_kg = fields.Float(
        string="Received",
        compute="_compute_received_kg",
        store=True,
        digits=(16, 3),
        help="Kg physically received from the supplier (validated incoming transfers).",
    )
    net_invoiced_kg = fields.Float(
        string="Net Invoiced",
        compute="_compute_net_invoiced_kg",
        store=True,
        digits=(16, 3),
        help="Kg of validated supplier invoices minus kg of validated credit notes.",
    )
    net_invoiced_amount = fields.Float(
        string="Net Invoiced Amount",
        compute="_compute_net_invoiced_amount",
        store=True,
        digits=(16, 2),
        help="Amount of posted supplier invoices minus posted credit notes of this lot.",
    )
    invoiced = fields.Boolean(
        string="Invoiced",
        copy=False,
        help=(
            "Indicates whether the lot is considered fully invoiced to the "
            "supplier. Updated automatically, but can be forced manually; "
            "once edited by hand it stops being recalculated on its own."
        ),
    )
    invoiced_locked = fields.Boolean(
        string="Invoiced Manually Locked",
        copy=False,
    )
    invoiceable = fields.Boolean(
        string="Invoiceable",
        compute="_compute_invoiceable",
        store=True,
        help=(
            "Candidate to invoice to the supplier: under the full-payment "
            "regime, it has received kg pending invoicing; under the "
            "sale-settlement regime, there is a pending amount on what has "
            "been sold (and scrapped) so far, whether it is completed "
            "(final settlement) or still has stock available (advance)."
        ),
    )

    mercas_margin = fields.Float(
        string="Margin (%)",
        digits=(10, 2),
    )
    can_edit_margin = fields.Boolean(
        compute="_compute_can_edit_margin",
    )
    supplier_amount = fields.Float(
        string="Supplier Amount",
        compute="_compute_supplier_fields",
        digits=(16, 2),
    )
    supplier_price_kg = fields.Float(
        string="Supplier Price/Kg",
        compute="_compute_supplier_fields",
        inverse="_inverse_supplier_price_kg",
        digits=(16, 4),
    )
    margin = fields.Float(
        string="Margin Amount",
        compute="_compute_supplier_fields",
        digits=(16, 2),
    )

    @api.depends_context("uid")
    def _compute_can_edit_firm_negotiation(self):
        is_manager = self.env.user.has_group("account.group_account_manager")
        for lot in self:
            lot.can_edit_firm_negotiation = is_manager

    @api.depends(
        "stock_move_line_ids.quantity",
        "stock_move_line_ids.state",
        "stock_move_line_ids.location_id.usage",
        "stock_move_line_ids.location_dest_id.usage",
    )
    def _compute_received_kg(self):
        for lot in self:
            received_mls = lot.stock_move_line_ids.filtered(
                lambda ml: ml.state == "done"
                and ml.location_id.usage == "supplier"
                and ml.location_dest_id.usage == "internal"
            )
            lot.received_kg = sum(received_mls.mapped("quantity"))

    @api.depends(
        "supplier_invoice_line_ids.quantity",
        "supplier_invoice_line_ids.move_id.state",
        "supplier_invoice_line_ids.move_id.move_type",
        "supplier_invoice_line_ids.mercas_is_firm_line",
    )
    def _compute_net_invoiced_kg(self):
        """Kg invoiced under the firm negotiation regime (lines marked
        `mercas_is_firm_line`). Sale advances/settlements don't count here:
        they don't represent received kg at the purchase price."""
        for lot in self:
            posted = lot.supplier_invoice_line_ids.filtered(
                lambda l: l.move_id.state == "posted" and l.mercas_is_firm_line
            )
            net = 0.0
            for line in posted:
                if line.move_id.move_type == "in_invoice":
                    net += line.quantity
                elif line.move_id.move_type == "in_refund":
                    net -= line.quantity
            lot.net_invoiced_kg = net

    @api.depends(
        "supplier_invoice_line_ids.price_subtotal",
        "supplier_invoice_line_ids.move_id.state",
        "supplier_invoice_line_ids.move_id.move_type",
    )
    def _compute_net_invoiced_amount(self):
        for lot in self:
            posted = lot.supplier_invoice_line_ids.filtered(
                lambda l: l.move_id.state == "posted"
            )
            net = 0.0
            for line in posted:
                if line.move_id.move_type == "in_invoice":
                    net += line.price_subtotal
                elif line.move_id.move_type == "in_refund":
                    net -= line.price_subtotal
            lot.net_invoiced_amount = net

    def _mercas_company(self):
        """`company_id` (compute='_compute_company_id', from product_id.company_id)
        is empty for any lot whose product has no company set (a product
        shared across companies) unless something wrote it explicitly (e.g.
        `_mercas_autocreate_lots` does, from the purchase order's own
        company) -- reading Mercas company settings via `self.company_id.x`
        directly would then silently see nothing instead of the intended
        configuration. Fall back to the current company in that case."""
        self.ensure_one()
        return self.company_id or self.env.company

    def _mercas_liquidation_gross(self):
        """Gross sale-settlement value of this lot: the final one
        (sale_amount net of margin) if completed (no stock left), or an
        advance estimate if there is still stock -- in both cases it is
        always the amount of what was actually sold, net of margin (scrap
        is never paid). The quantity/price that this amount is spread over
        depends on `company.liquidation_mode`:
        - "average_price": sold + scrapped (scrap dilutes the price/kg of
          the single line, without appearing separately).
        - "average_price_scrap_split": sold only (scrap is invoiced
          separately at price 0, see `_mercas_prepare_invoice_lines`).
        Returns (quantity, price, amount)."""
        self.ensure_one()
        if self.completed:
            amount = self.supplier_amount
        elif not self.sale_kg:
            return 0.0, 0.0, 0.0
        else:
            amount = self.sale_amount * (1.0 - self.mercas_margin / 100.0)

        if self._mercas_company().liquidation_mode == "average_price_scrap_split":
            qty = self.sale_kg
        elif self.completed:
            qty = self.purchase_kg
        else:
            qty = self.sale_kg + self.scrap_kg
        price_kg = amount / qty if qty > 0 else 0.0
        return qty, price_kg, amount

    @api.depends(
        "invoiced", "mercas_firm_negotiation", "received_kg", "net_invoiced_kg",
        "completed", "net_invoiced_amount", "sale_kg", "scrap_kg", "sale_amount",
        "mercas_margin", "purchase_kg", "supplier_price_kg", "supplier_amount",
    )
    def _compute_invoiceable(self):
        for lot in self:
            if lot.invoiced:
                lot.invoiceable = False
            elif lot.mercas_firm_negotiation:
                lot.invoiceable = lot.received_kg > lot.net_invoiced_kg
            else:
                _, _, gross = lot._mercas_liquidation_gross()
                lot.invoiceable = gross - lot.net_invoiced_amount > 0.01

    def _mercas_recompute_invoiced_status(self):
        """Reevaluate `invoiced` after posting a supplier invoice or credit
        note with lot lines. Does not touch manually locked lots (invoiced_locked)."""
        for lot in self:
            if lot.invoiced_locked:
                continue
            if lot.mercas_firm_negotiation:
                if lot.received_kg <= 0:
                    continue
                new_value = lot.net_invoiced_kg >= lot.received_kg
            else:
                if not lot.completed:
                    # Advances with pending stock never close the lot.
                    continue
                _, _, gross = lot._mercas_liquidation_gross()
                if gross <= 0:
                    continue
                new_value = lot.net_invoiced_amount >= gross - 0.01
            if lot.invoiced != new_value:
                lot.with_context(mercas_auto_invoiced=True).write({"invoiced": new_value})

    def action_open_scrap(self):
        """Open the standard scrap form of the lot, like its own "Scrap"
        action, with the quantity left at 0 for the user to fill in.

        `company_id` falls back to the current company when the lot's own
        (computed from product_id.company_id) is empty -- a product shared
        across companies (no company set) leaves the lot without one too.

        `location_id` is set explicitly from this lot's own stock instead
        of leaving it to the generic default (the "first" warehouse for the
        company, oblivious to the lot) -- with more than one warehouse that
        default can easily point at a location where this lot has no stock
        at all."""
        self.ensure_one()
        action = self.action_scrap()
        quant = self.quant_ids.filtered(
            lambda q: q.quantity > 0 and q.location_id.usage == "internal"
        )[:1]
        action["context"] = dict(
            action["context"],
            default_quantity=0,
            default_company_id=self._mercas_company().id,
        )
        if quant:
            action["context"]["default_location_id"] = quant.location_id.id
        action["target"] = "new"
        return action

    def _mercas_has_firm_invoicing(self):
        self.ensure_one()
        return bool(self.supplier_invoice_line_ids.filtered(
            lambda l: l.move_id.state == "posted" and l.mercas_is_firm_line
        ))

    def _mercas_unreconciled_settlement_amount(self):
        """Net amount already invoiced by sale settlement (advances or other
        settlements), pending to be deducted on the first firm invoice of
        this lot. Once deducted, the deduction line itself (not marked as
        firm) cancels it to zero forever."""
        self.ensure_one()
        non_firm = self.supplier_invoice_line_ids.filtered(
            lambda l: l.move_id.state == "posted" and not l.mercas_is_firm_line
        )
        amount = 0.0
        for line in non_firm:
            if line.move_id.move_type == "in_invoice":
                amount += line.price_subtotal
            elif line.move_id.move_type == "in_refund":
                amount -= line.price_subtotal
        return amount

    def write(self, vals):
        if "invoiced" in vals and not self.env.context.get("mercas_auto_invoiced"):
            vals = dict(vals, invoiced_locked=True)
        if "mercas_firm_negotiation" in vals:
            propagating = self.env.context.get("mercas_propagate_firm_negotiation")
            for lot in self:
                if lot.mercas_firm_negotiation == vals["mercas_firm_negotiation"]:
                    continue
                if lot._mercas_has_firm_invoicing():
                    raise UserError(
                        _("The firm negotiation of lot '%s' cannot be "
                          "changed: it already has firm invoicing recorded.")
                        % lot.name
                    )
                if not propagating and not self.env.user.has_group(
                    "account.group_account_manager"
                ):
                    raise UserError(
                        _("Only an Accounting Manager can change the firm "
                          "negotiation of a lot.")
                    )
        return super().write(vals)

    @api.constrains("purchase_line_ids")
    def _check_single_purchase_partner(self):
        for lot in self:
            partners = lot.purchase_line_ids.order_id.partner_id
            if len(partners) > 1:
                raise ValidationError(
                    _(
                        "Lot '%(lot)s' has purchase lines from different "
                        "suppliers (%(partners)s). For traceability, a lot "
                        "can only be associated with a single supplier."
                    )
                    % {
                        "lot": lot.name,
                        "partners": ", ".join(partners.mapped("name")),
                    }
                )

    @api.depends("name", "product_qty", "quant_ids.reserved_quantity", "partner_id", "create_date")
    @api.depends_context("lot_display_with_qty")
    def _compute_display_name(self):
        if not self.env.context.get("lot_display_with_qty"):
            return super()._compute_display_name()
        for lot in self:
            on_hand = lot.product_qty
            available = on_hand - sum(lot.quant_ids.mapped("reserved_quantity"))
            parts = ["%s (%s/%s)" % (
                lot.name,
                self._format_qty(on_hand),
                self._format_qty(available),
            )]
            if lot.partner_id:
                parts.append(lot.partner_id.name)
            if lot.create_date:
                parts.append(format_date(self.env, lot.create_date))
            lot.display_name = " - ".join(parts)

    @api.model
    def _format_qty(self, qty):
        if qty == int(qty):
            return str(int(qty))
        return "%.2f" % qty

    @api.depends("product_qty")
    def _compute_completed(self):
        for lot in self:
            lot.completed = lot.product_qty <= 0

    @api.depends("purchase_line_ids.product_qty", "purchase_line_ids.order_id.state")
    def _compute_purchase_kg(self):
        for lot in self:
            lines = lot.purchase_line_ids.filtered(
                lambda l: l.order_id.state in ("purchase", "done")
            )
            lot.purchase_kg = sum(lines.mapped("product_qty"))

    @api.depends(
        "stock_move_line_ids.quantity",
        "stock_move_line_ids.state",
        "stock_move_line_ids.move_id.sale_line_id",
        "stock_move_line_ids.move_id.sale_line_id.price_unit",
        "stock_move_line_ids.move_id.sale_line_id.discount",
    )
    def _compute_sale_fields(self):
        for lot in self:
            sale_mls = lot.stock_move_line_ids.filtered(
                lambda ml: ml.state == "done" and ml.move_id.sale_line_id
            )
            lot.sale_kg = sum(sale_mls.mapped("quantity"))
            amount = 0.0
            for ml in sale_mls:
                sl = ml.move_id.sale_line_id
                amount += ml.quantity * sl.price_unit * (1.0 - sl.discount / 100.0)
            lot.sale_amount = amount

    @api.depends(
        "stock_move_line_ids.quantity",
        "stock_move_line_ids.state",
        "stock_move_line_ids.move_id.sale_line_id",
    )
    def _compute_mercas_sale_classification(self):
        for lot in self:
            lot.mercas_sale_classification = lot._mercas_sale_classification_html()

    def _mercas_sale_classification_groups(self):
        """Delivered sales of the lot by (quality, size), in the order they
        were first sold: [{'quality', 'size', 'qty', 'amount'}]. The same
        moves and amounts as Sold Kg / Sold Amount."""
        self.ensure_one()
        sale_mls = self.stock_move_line_ids.filtered(
            lambda ml: ml.state == "done" and ml.move_id.sale_line_id
        ).sorted(lambda ml: (ml.move_id.date or ml.create_date, ml.id))
        groups = {}
        for ml in sale_mls:
            sale_line = ml.move_id.sale_line_id
            key = (sale_line.mercas_quality or "", sale_line.mercas_size or "")
            group = groups.setdefault(
                key, {"quality": key[0], "size": key[1], "qty": 0.0, "amount": 0.0}
            )
            group["qty"] += ml.quantity
            group["amount"] += ml.quantity * sale_line.price_unit * (1.0 - sale_line.discount / 100.0)
        return list(groups.values())

    def _mercas_sale_classification_html(self):
        groups = self._mercas_sale_classification_groups()
        if not any(group["quality"] or group["size"] for group in groups):
            return False
        currency = self._mercas_company().currency_id
        uom = self.product_id.uom_id.name or ""
        rows = Markup().join(
            Markup(
                "<tr><td>%s</td><td>%s</td><td class='text-end'>%s %s</td>"
                "<td class='text-end'>%s</td><td class='text-end'>%s</td></tr>"
            ) % (
                group["quality"] or "—",
                group["size"] or "—",
                formatLang(self.env, group["qty"], digits=3),
                uom,
                format_amount(self.env, group["amount"], currency),
                format_amount(self.env, group["amount"] / group["qty"], currency) if group["qty"] else "",
            )
            for group in groups
        )
        return Markup(
            "<table class='table table-sm o_mercas_sale_classification'><thead><tr>"
            "<th>%s</th><th>%s</th><th class='text-end'>%s</th>"
            "<th class='text-end'>%s</th><th class='text-end'>%s</th>"
            "</tr></thead><tbody>%s</tbody></table>"
        ) % (_("Quality"), _("Size"), _("Quantity"), _("Amount"), _("Average Price"), rows)

    @api.depends(
        "stock_move_line_ids.quantity",
        "stock_move_line_ids.state",
        "stock_move_line_ids.location_id.usage",
        "stock_move_line_ids.location_dest_id.usage",
    )
    @api.depends("stock_move_line_ids.is_scrap")
    def _compute_scrap_line_ids(self):
        scraps = self.env["stock.move.line"]._read_group(
            [("lot_id", "in", self.ids), ("is_scrap", "=", True)],
            ["lot_id"], ["move_id:recordset"],
        )
        scraps_by_lot = dict(scraps)
        for lot in self:
            lot.scrap_line_ids = scraps_by_lot.get(lot, self.env["stock.move"])

    @api.depends(
        "stock_move_line_ids.state",
        "stock_move_line_ids.quantity",
        "stock_move_line_ids.location_id.usage",
        "stock_move_line_ids.location_dest_id.usage",
    )
    def _compute_scrap_kg(self):
        for lot in self:
            loss_mls = lot.stock_move_line_ids.filtered(
                lambda ml: ml.state == "done"
                and ml.location_id.usage == "internal"
                and ml.location_dest_id.usage in ("production", "inventory")
            )
            gain_mls = lot.stock_move_line_ids.filtered(
                lambda ml: ml.state == "done"
                and ml.location_id.usage == "inventory"
                and ml.location_dest_id.usage == "internal"
            )
            lot.scrap_kg = (
                sum(loss_mls.mapped("quantity")) - sum(gain_mls.mapped("quantity"))
            )

    @api.depends_context("uid")
    def _compute_can_edit_margin(self):
        is_manager = self.env.user.has_group("sales_team.group_sale_manager")
        for lot in self:
            lot.can_edit_margin = is_manager

    @api.depends(
        "stock_move_line_ids.quantity",
        "stock_move_line_ids.state",
        "stock_move_line_ids.move_id.sale_line_id",
        "stock_move_line_ids.move_id.sale_line_id.price_unit",
        "stock_move_line_ids.move_id.sale_line_id.discount",
        "purchase_line_ids.product_qty",
        "purchase_line_ids.order_id.state",
        "mercas_margin",
    )
    def _compute_supplier_fields(self):
        for lot in self:
            supplier_amount = lot.sale_amount * (1.0 - lot.mercas_margin / 100.0)
            lot.supplier_amount = supplier_amount
            lot.supplier_price_kg = (
                supplier_amount / lot.purchase_kg if lot.purchase_kg else 0.0
            )
            lot.margin = lot.sale_amount - supplier_amount

    def _inverse_supplier_price_kg(self):
        """Editing the price/kg by hand recalculates the equivalent margin --
        `mercas_margin` remains the only field that is actually persisted,
        everything else is always derived from it (see
        `_compute_supplier_fields`), so writing here simply works out which
        margin would produce the entered price and stores that instead.

        Without a sold amount (`sale_amount = 0`, typical before the first
        sale) there is no basis to compute a margin -- the change is
        silently ignored and the field reverts to its computed value (0)
        on recompute."""
        for lot in self:
            if not lot.sale_amount or not lot.purchase_kg:
                continue
            target_amount = lot.supplier_price_kg * lot.purchase_kg
            lot.mercas_margin = (1.0 - target_amount / lot.sale_amount) * 100.0

    @api.onchange("supplier_price_kg")
    def _onchange_supplier_price_kg(self):
        """The `inverse` of a compute field only runs on save -- here the
        same logic is repeated so the margin recalculates on screen while
        the price is being edited, without waiting for save."""
        self._inverse_supplier_price_kg()

    def _mercas_invoice_origin_suffix(self):
        """Text '<date> | <order> | <supplier ref> | <lot>' to append to the
        name of a lot's main line."""
        self.ensure_one()
        purchase_line = self.purchase_line_ids.filtered(
            lambda l: l.order_id.state in ("purchase", "done")
        )[:1]
        parts = []
        if purchase_line and purchase_line.order_id.date_order:
            parts.append(purchase_line.order_id.date_order.strftime("%d/%m/%Y"))
        if purchase_line and purchase_line.order_id.name:
            parts.append(purchase_line.order_id.name)
        if purchase_line and purchase_line.order_id.partner_ref:
            parts.append(purchase_line.order_id.partner_ref)
        parts.append(self.name)
        return " | ".join(parts), purchase_line

    def _mercas_sale_breakdown_text(self):
        """Accumulated breakdown, one line of text per validated sale move of
        this lot: 'DD/MM/YYYY => Order => Quantity uom => Unit price
        currency_symbol'. Always accumulated (every sale so far, not only
        the new ones since the last invoice) -- same as Sold Kg/Sold Amount
        are already accumulated, so no new tracking is needed of which sale
        already appeared on a previous invoice. Informational text only, it
        does not affect any amount."""
        self.ensure_one()
        sale_mls = self.stock_move_line_ids.filtered(
            lambda ml: ml.state == "done" and ml.move_id.sale_line_id
        ).sorted(lambda ml: ml.move_id.date or ml.create_date)
        lines = []
        for ml in sale_mls:
            sale_line = ml.move_id.sale_line_id
            price = sale_line.price_unit * (1.0 - sale_line.discount / 100.0)
            date_str = format_date(self.env, ml.move_id.date) if ml.move_id.date else ""
            uom = ml.uom_id.name or ""
            currency_symbol = sale_line.currency_id.symbol or ""
            line = "%s => %s => %.2f %s => %.2f %s" % (
                date_str, sale_line.order_id.name, ml.quantity, uom,
                price, currency_symbol,
            )
            classification = sale_line._mercas_classification_text()
            if classification:
                line = "%s => %s" % (line, classification)
            lines.append(line)
        return "\n".join(lines)

    def _mercas_scrap_breakdown_text(self):
        """Accumulated breakdown of this lot's scrap adjustments, one line of
        text per move: 'DD/MM/YYYY => Quantity UoM'. Same move criteria as
        `_compute_scrap_kg` (formal scraps and negative inventory
        adjustments as positive, positive adjustments as negative -- so the
        sum matches the net of the scrap line itself). Accumulated, same
        reason as `_mercas_sale_breakdown_text`: no tracking is needed of
        which adjustment already appeared on a previous invoice."""
        self.ensure_one()
        loss_mls = self.stock_move_line_ids.filtered(
            lambda ml: ml.state == "done"
            and ml.location_id.usage == "internal"
            and ml.location_dest_id.usage in ("production", "inventory")
        )
        gain_mls = self.stock_move_line_ids.filtered(
            lambda ml: ml.state == "done"
            and ml.location_id.usage == "inventory"
            and ml.location_dest_id.usage == "internal"
        )
        entries = [(ml, ml.quantity) for ml in loss_mls]
        entries += [(ml, -ml.quantity) for ml in gain_mls]
        entries.sort(key=lambda entry: entry[0].move_id.date or entry[0].create_date)
        lines = []
        for ml, qty in entries:
            date_str = format_date(self.env, ml.move_id.date) if ml.move_id.date else ""
            uom = ml.uom_id.name or ""
            lines.append("%s => %.2f %s" % (date_str, qty, uom))
        return "\n".join(lines)

    def _mercas_prepare_invoice_lines(self):
        """Supplier invoice lines for this lot, depending on the regime. For
        the sale-settlement regime, if there are previous posted advances,
        adds one deduction line per advance (same as the Odoo standard for
        sale down payments)."""
        self.ensure_one()
        origin_suffix, purchase_line = self._mercas_invoice_origin_suffix()

        if self.mercas_firm_negotiation:
            pending_qty = self.received_kg - self.net_invoiced_kg
            unreconciled = self._mercas_unreconciled_settlement_amount()
            if pending_qty <= 0 and unreconciled <= 0.01:
                return []
            price_unit = purchase_line.price_unit if purchase_line else 0.0
            lines = []
            if pending_qty > 0:
                lines.append(Command.create({
                    "product_id": self.product_id.id,
                    "quantity": pending_qty,
                    "price_unit": price_unit,
                    "lot_id": self.id,
                    "mercas_is_firm_line": True,
                    "name": "%s\n%s" % (self.product_id.display_name or "", origin_suffix),
                }))
            if unreconciled > 0.01:
                # There can only be a pending amount from sale advances/
                # settlement on the lot's first firm invoice: from then on
                # the negotiation is locked as firm and that path is
                # blocked, so this line is never needed again.
                lines.append(Command.create({
                    "product_id": self.product_id.id,
                    "quantity": 1,
                    "price_unit": -unreconciled,
                    "lot_id": self.id,
                    "name": _("(-) Advances pending to deduct"),
                }))
            return lines

        gross_qty, gross_price, gross_amount = self._mercas_liquidation_gross()
        if gross_amount - self.net_invoiced_amount <= 0.01:
            return []

        company = self._mercas_company()
        label = _("Settlement") if self.completed else _("Settlement advance (estimated)")
        name = "%s - %s\n%s" % (self.product_id.display_name or "", label, origin_suffix)
        if company.liquidation_show_sale_breakdown:
            breakdown = self._mercas_sale_breakdown_text()
            if breakdown:
                name = "%s\n%s" % (name, breakdown)
        lines = [Command.create({
            "product_id": self.product_id.id,
            "quantity": gross_qty,
            "price_unit": gross_price,
            "lot_id": self.id,
            "name": name,
        })]

        # "Scrap separate" mode: informational line at price 0 with the
        # total scrapped so far -- make it explicit on the invoice that it
        # isn't paid, instead of diluting it into the price/kg of the line above.
        if (
            company.liquidation_mode == "average_price_scrap_split"
            and self.scrap_kg > 0
        ):
            scrap_name = "%s - %s\n%s" % (
                self.product_id.display_name or "", _("Scrap"), origin_suffix,
            )
            if company.liquidation_show_sale_breakdown:
                scrap_breakdown = self._mercas_scrap_breakdown_text()
                if scrap_breakdown:
                    scrap_name = "%s\n%s" % (scrap_name, scrap_breakdown)
            lines.append(Command.create({
                "product_id": self.product_id.id,
                "quantity": self.scrap_kg,
                "price_unit": 0.0,
                "lot_id": self.id,
                "name": scrap_name,
            }))

        prior_moves = self.supplier_invoice_line_ids.filtered(
            lambda l: l.move_id.state == "posted"
        ).mapped("move_id").sorted("invoice_date")
        for move in prior_moves:
            move_lines = self.supplier_invoice_line_ids.filtered(lambda l: l.move_id == move)
            contribution = sum(move_lines.mapped("price_subtotal"))
            if move.move_type == "in_refund":
                contribution = -contribution
            if not contribution:
                continue
            lines.append(Command.create({
                "product_id": self.product_id.id,
                "quantity": 1,
                "price_unit": -contribution,
                "lot_id": self.id,
                "name": _("(-) Advance already invoiced: %(invoice)s on %(date)s") % {
                    "invoice": move.name,
                    "date": format_date(self.env, move.invoice_date) if move.invoice_date else "",
                },
            }))
        return lines

    def action_create_supplier_invoices(self):
        lots = self.filtered(lambda l: l.invoiceable and l.partner_id)
        if not lots:
            raise UserError(
                _("There are no invoiceable lots (completed, with a "
                  "pending sale advance, or with pending received quantity "
                  "under the full-payment regime) that are unbilled and "
                  "have a supplier assigned.")
            )

        # `invoiceable` only looks at posted invoices (net_invoiced_kg/amount),
        # so a lot with a draft invoice still shows up as invoiceable and
        # would generate duplicate lines again if allowed through.
        with_draft = lots.filtered(
            lambda l: l.supplier_invoice_line_ids.move_id.filtered(
                lambda m: m.state == "draft"
            )
        )
        if with_draft:
            raise UserError(
                _("The following lots already have draft invoices: %s. "
                  "Confirm or delete those invoices before generating new ones.")
                % ", ".join(with_draft.mapped("name"))
            )

        by_partner = {}
        for lot in lots:
            by_partner.setdefault(lot.partner_id.id, self.env["stock.lot"])
            by_partner[lot.partner_id.id] |= lot

        invoices = self.env["account.move"]
        for partner_id, partner_lots in by_partner.items():
            lines = []
            for lot in partner_lots:
                lines += lot._mercas_prepare_invoice_lines()
            if not lines:
                continue

            invoice = self.env["account.move"].create({
                "move_type": "in_invoice",
                "partner_id": partner_id,
                "invoice_date": fields.Date.context_today(self),
                "invoice_line_ids": lines,
            })

            # `invoiced` is recalculated on posting (see account_move.py): under
            # the full-payment regime, when invoiced covers received; under
            # the sale-settlement regime, only when the lot is also completed
            # (an advance with pending stock never closes the lot on its own).
            # The cost of sale lines is only synced on the final settlement:
            # on an advance the price is an estimate.
            for lot in partner_lots.filtered(
                lambda l: not l.mercas_firm_negotiation and l.completed
            ):
                lot._sync_sale_lines_cost()

            if self.env.company.auto_confirm_supplier_invoice:
                invoice.action_post()

            invoices |= invoice

        if not invoices:
            return

        if len(invoices) == 1:
            return {
                "type": "ir.actions.act_window",
                "res_model": "account.move",
                "res_id": invoices.id,
                "view_mode": "form",
                "target": "current",
            }
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "domain": [("id", "in", invoices.ids)],
            "view_mode": "list,form",
            "target": "current",
        }

    def _sync_sale_lines_cost(self):
        """Updates purchase_price on sale lines if sale_margin is installed."""
        if "purchase_price" not in self.env["sale.order.line"]._fields:
            return
        for lot in self:
            sale_lines = lot.stock_move_line_ids.filtered(
                lambda ml: ml.state == "done" and ml.move_id.sale_line_id
            ).mapped("move_id.sale_line_id")
            if sale_lines:
                sale_lines.write({"purchase_price": lot.supplier_price_kg})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "mercas_margin" not in vals:
                partner_id = vals.get("partner_id")
                company_id = vals.get("company_id", self.env.company.id)
                partner = (
                    self.env["res.partner"].browse(partner_id)
                    if partner_id
                    else self.env["res.partner"]
                )
                company = self.env["res.company"].browse(company_id)
                vals["mercas_margin"] = (
                    partner.mercas_margin
                    if partner and partner.mercas_margin
                    else company.mercas_margin
                )
        return super().create(vals_list)
