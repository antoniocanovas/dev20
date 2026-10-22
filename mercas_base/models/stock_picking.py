from odoo import _, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    supplier_ref = fields.Char(
        string="Supplier Delivery Note",
        copy=False,
        index="trigram",
        help="Code of the supplier's delivery note for this receipt. The "
             "Auto-Complete of the vendor bill also finds the purchase by it.",
    )

    def _mercas_validate(self):
        """Validate the transfers of the automatic flows ("Sold & Sent",
        "Purchase & Receive", boxes) without the dialogs of the standard
        validation: immediate transfer, backorder and, with stock_sms, the
        confirmation of the SMS of the delivery.

        A dialog the flow doesn't know would leave the transfer as it was while
        the order looks done, so a transfer still not done is an error."""
        self.with_context(
            skip_immediate=True,
            skip_backorder=True,
            skip_sms=True,
        ).button_validate()
        not_done = self.filtered(lambda picking: picking.state != "done")
        if not_done:
            raise UserError(
                _("The transfer %s couldn't be validated automatically. Validate it from the transfer itself.")
                % ", ".join(not_done.mapped("name"))
            )
