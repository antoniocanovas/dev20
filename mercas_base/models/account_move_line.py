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
