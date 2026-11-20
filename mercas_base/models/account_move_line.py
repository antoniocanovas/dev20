from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    lot_id = fields.Many2one(
        comodel_name="stock.lot",
        string="Lot",
        index=True,
        ondelete="set null",
    )
    mercas_is_firm_line = fields.Boolean(
        string="Firm Supply Line",
        copy=False,
        help=(
            "Marks vendor bill lines that represent received kg invoiced "
            "under the firm negotiation regime, so pending kg can be "
            "tracked without mixing them with sale settlement advances or "
            "settlements."
        ),
    )
    box_qty = fields.Integer(
        string="Boxes",
        help="Boxes of the goods of the line, from the order line it "
             "invoices (in proportion when it invoices only a part).",
    )
    mercas_tare = fields.Float(
        string="Tare",
        digits="Stock Weight",
        help="Weight of the boxes of the line, kept from the order line: "
             "printed with the gross and net weight on the invoice.",
    )

    def _mercas_weights(self):
        """Boxes, net, tare and gross weight of the line, in the weight unit
        of the products."""
        self.ensure_one()
        net = (
            self.product_id._mercas_net_weight(self.quantity, self.product_uom_id)
            if self.product_id else 0.0
        )
        return {
            "boxes": self.box_qty,
            "net": net,
            "tare": self.mercas_tare,
            "gross": net + self.mercas_tare,
        }
