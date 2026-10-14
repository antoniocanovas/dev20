from datetime import datetime, time, timedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class StockLotInvoiceWizard(models.TransientModel):
    _name = "stock.lot.invoice.wizard"
    _description = "Invoicing of Completed Lots"

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Supplier",
    )
    date_to = fields.Date(string="Date To")
    show_all = fields.Boolean(
        string="Show All",
        help="Also shows lots that aren't invoiceable yet, although they "
             "can't be selected for invoicing.",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        default=lambda self: self.env.company.currency_id,
    )
    line_ids = fields.One2many(
        comodel_name="stock.lot.invoice.wizard.line",
        inverse_name="wizard_id",
        string="Lots",
    )
    amount_total = fields.Monetary(
        string="Total Amount",
        compute="_compute_amount_total",
        currency_field="currency_id",
        help="Amount of the lots currently selected in the list.",
    )

    @api.depends("line_ids.selected", "line_ids.amount_to_invoice")
    def _compute_amount_total(self):
        for wizard in self:
            wizard.amount_total = sum(
                wizard.line_ids.filtered("selected").mapped("amount_to_invoice")
            )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "line_ids" in fields_list:
            res["line_ids"] = self._prepare_lines(False, False, False)
        return res

    @api.onchange("partner_id", "date_to", "show_all")
    def _onchange_filters(self):
        self.line_ids = self._prepare_lines(self.partner_id, self.date_to, self.show_all)

    def _prepare_lines(self, partner, date_to, show_all):
        base_domain = []
        if partner:
            base_domain.append(("partner_id", "=", partner.id))
        if date_to:
            upper_bound = datetime.combine(date_to + timedelta(days=1), time.min)
            base_domain.append(("create_date", "<", fields.Datetime.to_string(upper_bound)))

        if show_all:
            domain = base_domain + [("invoiced", "=", False)]
        else:
            domain = base_domain + [("invoiceable", "=", True)]
        lots = self.env["stock.lot"].search(domain)

        return [Command.clear()] + [
            Command.create({
                "lot_id": lot.id,
                # Advances (lots with pending stock under sale settlement)
                # aren't preselected: they're an explicit action, not
                # included by default in "Settle".
                "selected": lot.invoiceable and (lot.mercas_firm_negotiation or lot.completed),
            })
            for lot in lots
        ]

    def action_liquidar(self):
        """On the selected lots: sale settlement already completed (final
        settlement) and firm negotiation with pending received quantity.
        Leaves out advances, which require explicit selection."""
        lots = self.line_ids.filtered(
            lambda l: l.selected and l.invoiceable
            and (l.mercas_firm_negotiation or l.completed)
        ).lot_id
        return self._invoice_lots(lots)

    def action_invoice_advance(self):
        """Sale settlement advance, on selected lots only."""
        selected = self.line_ids.filtered("selected")
        wrong_mode = selected.filtered("mercas_firm_negotiation")
        if wrong_mode:
            raise UserError(
                _("The following lots are under firm negotiation: %s. "
                  "Use the 'Firm Invoice' button to invoice them.")
                % ", ".join(wrong_mode.mapped("lot_id.name"))
            )
        return self._invoice_lots(selected.filtered("invoiceable").lot_id)

    def action_invoice_firm(self):
        """Firm invoice (total of pending received quantity), on selected
        lots marked with firm negotiation only."""
        selected = self.line_ids.filtered("selected")
        wrong_mode = selected.filtered(lambda l: not l.mercas_firm_negotiation)
        if wrong_mode:
            raise UserError(
                _("The following lots don't have firm negotiation enabled: "
                  "%s. Enable it on the lot (requires an Accounting "
                  "Manager) before using this button.")
                % ", ".join(wrong_mode.mapped("lot_id.name"))
            )
        return self._invoice_lots(selected.filtered("invoiceable").lot_id)

    def _invoice_lots(self, lots):
        self.ensure_one()
        if not lots:
            raise UserError(_("There are no lots to invoice."))
        return lots.action_create_supplier_invoices()


class StockLotInvoiceWizardLine(models.TransientModel):
    _name = "stock.lot.invoice.wizard.line"
    _description = "Lot Invoicing Line"

    wizard_id = fields.Many2one(
        comodel_name="stock.lot.invoice.wizard",
        required=True,
        ondelete="cascade",
    )
    selected = fields.Boolean(
        string="Selected",
        default=True,
        help="Can only be edited if part of the material has been "
        "sold/scrapped (settlement) or the lot is marked as firm invoicing "
        "with pending kg to invoice.",
    )
    lot_id = fields.Many2one(
        comodel_name="stock.lot", string="Lot", required=True, readonly=True
    )
    create_date = fields.Date(
        string="Creation Date", compute="_compute_create_date", readonly=True
    )
    ref = fields.Char(related="lot_id.ref", readonly=True)
    company_id = fields.Many2one(
        related="lot_id.company_id", string="Company", readonly=True
    )
    partner_ids = fields.Many2many(
        related="lot_id.partner_ids", string="Transfer to", readonly=True
    )
    product_qty = fields.Float(
        related="lot_id.product_qty", string="Quantity", readonly=True
    )
    completed = fields.Boolean(related="lot_id.completed", readonly=True)
    partner_id = fields.Many2one(
        related="lot_id.partner_id", string="Supplier", readonly=True
    )
    product_id = fields.Many2one(
        related="lot_id.product_id", string="Product", readonly=True
    )
    mercas_firm_negotiation = fields.Boolean(
        related="lot_id.mercas_firm_negotiation",
        string="Firm Negotiation",
        readonly=True,
    )
    invoiceable = fields.Boolean(related="lot_id.invoiceable", readonly=True)
    purchase_kg = fields.Float(
        related="lot_id.purchase_kg", string="Purchased", readonly=True
    )
    received_kg = fields.Float(
        related="lot_id.received_kg", string="Received", readonly=True
    )
    net_invoiced_kg = fields.Float(
        related="lot_id.net_invoiced_kg", string="Net Invoiced", readonly=True
    )
    sale_kg = fields.Float(related="lot_id.sale_kg", string="Sold", readonly=True)
    scrap_kg = fields.Float(
        related="lot_id.scrap_kg", string="Scrapped", readonly=True
    )
    sale_amount = fields.Float(
        related="lot_id.sale_amount", string="Sold Amount", readonly=True
    )
    mercas_margin = fields.Float(
        related="lot_id.mercas_margin", string="Margin (%)", readonly=False
    )
    supplier_price_kg = fields.Float(
        related="lot_id.supplier_price_kg", string="Price/Kg", readonly=False
    )
    supplier_amount = fields.Float(
        related="lot_id.supplier_amount", string="Amount", readonly=False
    )
    net_invoiced_amount = fields.Float(
        related="lot_id.net_invoiced_amount", string="Invoiced Amount", readonly=True
    )
    amount_to_invoice = fields.Float(
        string="Amount to Invoice",
        compute="_compute_amount_to_invoice",
    )

    @api.depends("lot_id.create_date")
    def _compute_create_date(self):
        for line in self:
            line.create_date = line.lot_id.create_date

    @api.onchange("supplier_price_kg")
    def _onchange_supplier_price_kg(self):
        """`supplier_price_kg`/`mercas_margin`/`supplier_amount` are
        `related` fields here -- writing to one propagates to `lot_id` in
        memory, but the round trip back (`lot_id` -> this same line's
        related `supplier_amount`) isn't reliable within the same onchange,
        so all three are explicitly recalculated on the line itself,
        instead of relying on that round trip between models.

        Without a sold amount (`sale_amount = 0`, typical before the first
        sale) there is no basis to compute a margin -- the change is
        silently ignored."""
        for line in self:
            if not line.sale_amount or not line.purchase_kg:
                continue
            supplier_amount = line.supplier_price_kg * line.purchase_kg
            line.mercas_margin = (1.0 - supplier_amount / line.sale_amount) * 100.0
            line.supplier_amount = supplier_amount

    @api.onchange("mercas_margin")
    def _onchange_mercas_margin(self):
        """Symmetric to the one above: recalculates price/kg and amount on
        the line itself when the margin is edited by hand, for the same
        reason (not relying on the related round trip through `lot_id`
        and back)."""
        for line in self:
            supplier_amount = line.sale_amount * (1.0 - line.mercas_margin / 100.0)
            line.supplier_amount = supplier_amount
            line.supplier_price_kg = (
                supplier_amount / line.purchase_kg if line.purchase_kg else 0.0
            )

    @api.depends(
        "mercas_firm_negotiation",
        "received_kg",
        "net_invoiced_kg",
        "net_invoiced_amount",
        "completed",
        "sale_kg",
        "scrap_kg",
        "sale_amount",
        "mercas_margin",
        "purchase_kg",
        "supplier_price_kg",
        "supplier_amount",
        "lot_id.purchase_line_ids.price_unit",
        "lot_id.purchase_line_ids.order_id.state",
        "lot_id.supplier_invoice_line_ids.price_subtotal",
        "lot_id.supplier_invoice_line_ids.move_id.state",
        "lot_id.supplier_invoice_line_ids.move_id.move_type",
        "lot_id.supplier_invoice_line_ids.mercas_is_firm_line",
    )
    def _compute_amount_to_invoice(self):
        for line in self:
            if line.mercas_firm_negotiation:
                purchase_line = line.lot_id.purchase_line_ids.filtered(
                    lambda l: l.order_id.state in ("purchase", "done")
                )[:1]
                price_unit = purchase_line.price_unit if purchase_line else 0.0
                pending = line.received_kg - line.net_invoiced_kg
                gross = pending * price_unit if pending > 0 else 0.0
                unreconciled = line.lot_id._mercas_unreconciled_settlement_amount()
                amount = gross - (unreconciled if unreconciled > 0.01 else 0.0)
                line.amount_to_invoice = amount if amount > 0 else 0.0
            else:
                _, _, gross = line.lot_id._mercas_liquidation_gross()
                pending = gross - line.net_invoiced_amount
                line.amount_to_invoice = pending if pending > 0 else 0.0
