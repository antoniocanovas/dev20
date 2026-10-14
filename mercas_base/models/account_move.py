from odoo import Command, _, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_post(self):
        result = super().action_post()
        for move in self:
            if move.move_type not in ("in_invoice", "in_refund"):
                continue
            lots = move.invoice_line_ids.lot_id
            if lots:
                lots._mercas_recompute_invoiced_status()
        return result

    def action_compensate(self):
        """Create a compensation journal entry that pays the vendor bill and generates
        an outstanding credit on the partner's customer invoices."""
        self.ensure_one()

        if self.payment_state in ("paid", "in_payment"):
            raise UserError(_("This invoice is already paid or in the process of being paid."))
        if self.amount_residual <= 0:
            raise UserError(_("There is no outstanding amount on this invoice."))

        journal = self.company_id.compensation_journal_id
        if not journal:
            raise UserError(
                _("Configure the offsetting journal on the Mercas tab of the company.")
            )

        bill_payable_line = self.line_ids.filtered(
            lambda l: l.account_id.account_type == "liability_payable"
            and not l.reconciled
        )[:1]
        if not bill_payable_line:
            raise UserError(
                _("No outstanding payable line was found on the invoice.")
            )

        partner = self.partner_id.commercial_partner_id
        receivable_account = partner.property_account_receivable_id
        if not receivable_account:
            raise UserError(
                _("Partner '%s' has no receivable account configured.") % partner.name
            )

        amount = self.amount_residual
        label = _("Offset %s") % self.name

        compensation = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": journal.id,
            "date": self.invoice_date or self.date,
            "ref": label,
            "line_ids": [
                Command.create({
                    "account_id": bill_payable_line.account_id.id,
                    "partner_id": partner.id,
                    "debit": amount,
                    "credit": 0.0,
                    "name": label,
                }),
                Command.create({
                    "account_id": receivable_account.id,
                    "partner_id": partner.id,
                    "debit": 0.0,
                    "credit": amount,
                    "name": label,
                }),
            ],
        })
        compensation.action_post()

        comp_payable_line = compensation.line_ids.filtered(
            lambda l: l.account_id == bill_payable_line.account_id
        )
        (comp_payable_line | bill_payable_line).reconcile()
