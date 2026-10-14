from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class StockLotChangeWizard(models.TransientModel):
    _name = "stock.lot.change.wizard"
    _description = "Correct the Lot of a Sale Order Line, Delivered or Pending"

    sale_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        string="Sale Order Line",
        required=True,
        readonly=True,
    )
    order_id = fields.Many2one(related="sale_line_id.order_id", readonly=True)
    product_id = fields.Many2one(related="sale_line_id.product_id", readonly=True)
    line_ids = fields.One2many(
        comodel_name="stock.lot.change.wizard.line",
        inverse_name="wizard_id",
        string="Deliveries",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "line_ids" in fields_list and res.get("sale_line_id"):
            sale_line = self.env["sale.order.line"].browse(res["sale_line_id"])
            move_lines = sale_line.move_ids.move_line_ids.filtered(
                lambda ml: ml.state != "cancel" and ml.lot_id
            )
            res["line_ids"] = [
                Command.create({
                    "move_line_id": ml.id,
                    "current_lot_id": ml.lot_id.id,
                    "quantity": ml.quantity,
                    "new_lot_id": ml.lot_id.id,
                })
                for ml in move_lines
            ]
        return res

    def action_apply(self):
        self.ensure_one()
        changed = self.line_ids.filtered(lambda l: l.new_lot_id != l.current_lot_id)
        if not changed:
            raise UserError(_("You haven't changed any lot."))

        wrong_product = changed.filtered(
            lambda l: l.new_lot_id.product_id != self.product_id
        )
        if wrong_product:
            raise UserError(
                _("The destination lot must be of the same product as the sale order line.")
            )

        # An advance (amount/kg invoiced without `invoiced=True`) doesn't
        # block: the final settlement isn't fixed yet. Firm invoicing also
        # doesn't block even if complete, because it's our responsibility to
        # the supplier and doesn't depend on which sale the lot is attributed to.
        lots_involved = changed.current_lot_id | changed.new_lot_id
        blocked = lots_involved.filtered(
            lambda lot: lot.invoiced and not lot.mercas_firm_negotiation
        )
        if blocked:
            raise UserError(
                _("Cannot correct: the following lots already have their "
                  "sale settlement fully invoiced to the supplier: %s")
                % ", ".join(blocked.mapped("name"))
            )

        draft_invoice_lines = self.sale_line_id.invoice_lines.filtered(
            lambda l: l.parent_state == "draft"
        )

        # Optional field from stock_restrict_lot (OCA stock-logistics-workflow):
        # if installed, the move's lot restriction must follow the
        # correction so it doesn't end up pointing at the wrong lot.
        has_restrict_lot_id = "restrict_lot_id" in self.env["stock.move"]._fields

        # The "Correct Lots" group doesn't by itself grant write access to
        # other users' sale orders or invoices; the actual access control is
        # already enforced by this wizard's ACL, so the actual writes (all on
        # a traceability field, not a financial one) are done with sudo so as
        # not to require separate Sales/Accounting permissions.
        for line in changed:
            old_lot = line.current_lot_id
            new_lot = line.new_lot_id
            # Writing lot_id on an already validated (`done`) move line
            # already corrects the physical stock (stock.quant) at the
            # source and destination of that line: this is native
            # stock.move.line.write() behavior (it undoes the effect of the
            # old lot and applies the new one's before/after super().write()),
            # no separate manual adjustment is needed.
            line.move_line_id.sudo().lot_id = new_lot.id
            if has_restrict_lot_id:
                line.move_line_id.move_id.sudo().restrict_lot_id = new_lot.id
            draft_invoice_lines.filtered(lambda l: l.lot_id == old_lot).sudo().write(
                {"lot_id": new_lot.id}
            )
            note = _(
                "Lot correction: %(qty)s %(uom)s from order %(order)s "
                "(%(product)s) moved from %(old)s to %(new)s by %(user)s."
            ) % {
                "qty": line.quantity,
                "uom": line.move_line_id.uom_id.name,
                "order": self.order_id.name,
                "product": self.product_id.display_name,
                "old": old_lot.name,
                "new": new_lot.name,
                "user": self.env.user.name,
            }
            old_lot.message_post(body=note)
            new_lot.message_post(body=note)

        # The sale order line's own lot field holds a single value: if the
        # correction spreads quantity across several destination lots, it
        # keeps the one with the largest corrected quantity as the main reference.
        self.sale_line_id.sudo().lot_id = max(changed, key=lambda l: l.quantity).new_lot_id

        return {"type": "ir.actions.act_window_close"}


class StockLotChangeWizardLine(models.TransientModel):
    _name = "stock.lot.change.wizard.line"
    _description = "Delivery to Correct"

    wizard_id = fields.Many2one(
        comodel_name="stock.lot.change.wizard",
        required=True,
        ondelete="cascade",
    )
    move_line_id = fields.Many2one(
        comodel_name="stock.move.line",
        string="Move Line",
        required=True,
        readonly=True,
    )
    current_lot_id = fields.Many2one(
        comodel_name="stock.lot",
        string="Current Lot",
        readonly=True,
    )
    quantity = fields.Float(string="Quantity", readonly=True)
    new_lot_id = fields.Many2one(
        comodel_name="stock.lot",
        string="Correct Lot",
    )
