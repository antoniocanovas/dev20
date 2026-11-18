from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


class AccountMove(models.Model):
    _inherit = "account.move"

    mercas_comment = fields.Text(
        string="Comments",
        compute="_compute_mercas_comment",
        help="Comments of the sales invoiced, printed on the invoice.",
    )

    @api.depends("invoice_line_ids.sale_line_ids.order_id.mercas_comment")
    def _compute_mercas_comment(self):
        for move in self:
            orders = move.invoice_line_ids.sale_line_ids.order_id
            move.mercas_comment = "\n".join(c for c in orders.mapped("mercas_comment") if c) or False

    def action_post(self):
        result = super().action_post()
        for move in self:
            if move.move_type not in ("in_invoice", "in_refund"):
                continue
            lots = move.invoice_line_ids.lot_id
            if lots:
                lots._mercas_recompute_invoiced_status()
        return result

    def _mercas_is_self_billed(self):
        """A vendor bill or refund of a supplier whose invoices we issue."""
        self.ensure_one()
        return (
            self.is_purchase_document()
            and self.partner_id.commercial_partner_id.mercas_self_billing
        )

    def _search_default_journal(self):
        # The bills of a supplier with self-billing go to the self-billing
        # journal of the company; the others never do by default
        journal = super()._search_default_journal()
        if journal.type != "purchase" or self.statement_line_ids:
            return journal
        company = self.company_id or self.env.company
        if self._mercas_is_self_billed() and company.mercas_self_billing_journal_id:
            return company.mercas_self_billing_journal_id
        if journal.is_self_billing:
            journal = self.env["account.journal"].search([
                *self.env["account.journal"]._check_company_domain(company),
                ("type", "=", "purchase"),
                ("is_self_billing", "=", False),
            ], limit=1) or journal
        return journal

    @api.onchange("partner_id")
    def _onchange_partner_mercas_self_billing(self):
        """Choosing the supplier of a new bill by hand changes its journal."""
        if self.state != "draft" or self.posted_before or not self.is_purchase_document():
            return
        if self.journal_id.is_self_billing != self._mercas_is_self_billed():
            journal = self._search_default_journal()
            if journal.is_self_billing == self._mercas_is_self_billed():
                self.journal_id = journal

    def _post(self, soft=True):
        not_self_billed = self.filtered(
            lambda m: m.journal_id.is_self_billing
            and m.is_purchase_document()
            and not m._mercas_is_self_billed()
        )
        if not_self_billed:
            raise UserError(
                _("%s doesn't have self-billing: its bills can't go to a "
                  "self-billing journal.")
                % ", ".join(not_self_billed.mapped(lambda m: m.partner_id.display_name))
            )
        return super()._post(soft=soft)

    def _set_next_sequence(self):
        # A self-billing invoice is the invoice of the supplier: its number is
        # the vendor reference (asked by SII and the 347, and used to find
        # duplicates). Set here, when the number is given on posting, before
        # the checks of the electronic invoicing.
        super()._set_next_sequence()
        for move in self:
            if move.journal_id.is_self_billing and move.is_purchase_document() and not move.ref:
                move.ref = move.name

    def _get_alerts(self):
        # The standard takes the sections and notes (always at 0) for empty
        # lines: a bill of a purchase with its PRODUCTOS and Envases sections
        # would show the alert, and its button would delete them.
        alerts = super()._get_alerts()
        if "account_remove_empty_lines" in alerts:
            zero_lines = self.invoice_line_ids.filtered(
                lambda line: line.display_type == "product" and line.price_total == 0
            )
            if len(zero_lines) >= 2:
                alerts["account_remove_empty_lines"]["action_call"] = (
                    "account.move.line", "unlink", zero_lines.ids,
                )
            else:
                del alerts["account_remove_empty_lines"]
        settlement = self._mercas_lot_settlement_alert()
        if settlement:
            alerts["mercas_lot_settlement_lines"] = settlement
        return alerts

    def _mercas_lot_settlement_alert(self):
        """The lines of the purchases of a bill left out of it because they
        are invoiced from their lot (see purchase.order.action_create_invoice):
        without a warning the bill looks incomplete."""
        if self.move_type != "in_invoice" or self.state == "cancel":
            return False
        lines = self.invoice_line_ids.purchase_line_id.order_id._mercas_lot_settlement_lines()
        if not lines:
            return False
        detail = "; ".join(
            "%s: %s %s %s (%s)" % (
                line.order_id.name,
                line.product_id.display_name,
                formatLang(self.env, line.product_qty, digits=2),
                line.uom_id.name,
                _("lot %s", line.lot_id.name),
            )
            for line in lines
        )
        return {
            "level": "warning",
            "message": _(
                "Not in this bill: the lines with a lot are invoiced from "
                "their lot (settlement, advance or firm invoice of the lot). %s",
                detail,
            ),
            "action_text": _("See the lots"),
            "action": {
                "type": "ir.actions.act_window",
                "name": _("Lots to invoice"),
                "res_model": "stock.lot",
                "view_mode": "list,form",
                "domain": [("id", "in", lines.lot_id.ids)],
                "target": "current",
            },
        }

    def _add_purchase_order_lines(self, purchase_order_lines):
        # The lines with a lot are invoiced from the lot, as in the bill of
        # the purchase (see purchase.order.action_create_invoice)
        return super()._add_purchase_order_lines(purchase_order_lines._mercas_without_lot_lines())

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
