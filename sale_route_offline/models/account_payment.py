from datetime import timedelta

from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import float_is_zero

from .res_partner import check_offline_uuid, is_record_id

# A payment registered offline can be synchronized up to this many days later
MAX_PAYMENT_AGE_DAYS = 30
MAX_MEMO_LENGTH = 200


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    offline_uuid = fields.Char(
        'Offline Identifier', copy=False, readonly=True,
        help="Identifier given by the tablet that registered the payment offline.")

    # The unique index also serves the searches by uuid
    _offline_uuid_unique = models.Constraint(
        'UNIQUE (offline_uuid)',
        "This payment was already received from the tablet.",
    )

    @api.model
    def create_from_tablet(self, vals):
        """ Create the payment registered on the tablet as a draft, or return it if it was already
        created (the tablet retries the call if the connection is lost after the commit). The
        accounting team posts it and reconciles it with the invoices.

        Salespeople have no access to payments: once everything sent by the tablet is checked,
        the payment is created as superuser. The current user remains its creator.

        :param dict vals: {
            'offline_uuid': str, 'partner_id': int, 'amount': float, 'journal_id': int,
            'invoice_ids': [int], 'memo': str, 'date': 'YYYY-MM-DD',
        }
        :return: {'id': int, 'name': str}
        """
        if not isinstance(vals, dict):
            raise ValidationError(self.env._("Invalid payment."))
        offline_uuid = check_offline_uuid(self.env, vals.get('offline_uuid'))
        existing = self.sudo().search([('offline_uuid', '=', offline_uuid)], limit=1)
        if existing:
            if existing.create_uid != self.env.user:
                raise AccessError(self.env._("This payment was registered by another user."))
            return {'id': existing.id, 'name': existing.name}

        customer = self.env['res.partner']._get_route_customer(vals.get('partner_id'))
        company = self.env.company
        journal = self._get_tablet_journal(vals.get('journal_id'))
        amount = vals.get('amount')
        if (
            not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount <= 0
            or float_is_zero(amount, precision_rounding=company.currency_id.rounding)
        ):
            raise ValidationError(self.env._("The amount must be positive."))
        memo = vals.get('memo') or ''
        if not isinstance(memo, str) or len(memo) > MAX_MEMO_LENGTH:
            raise ValidationError(self.env._("The memo is too long."))
        invoices = self._get_tablet_invoices(customer, vals.get('invoice_ids') or [])
        payment = self.sudo().create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': customer.id,
            'amount': company.currency_id.round(amount),
            'currency_id': company.currency_id.id,
            'journal_id': journal.id,
            'date': self._get_tablet_date(vals.get('date')),
            'memo': memo.strip() or False,
            'invoice_ids': [Command.set(invoices.ids)],
            'offline_uuid': offline_uuid,
        })
        return {'id': payment.id, 'name': payment.name}

    def action_post(self):
        res = super().action_post()
        self.filtered('offline_uuid')._reconcile_tablet_invoices()
        return res

    def _reconcile_tablet_invoices(self):
        """ Reconcile the payments registered on the tablet with the invoices chosen by the
        salesperson, like the payment wizard of the invoices does. Partially if the amount is
        lower; what is left of a higher amount stays outstanding. """
        domain = [
            ('parent_state', '=', 'posted'),
            ('account_type', 'in', self._get_valid_payment_account_types()),
            ('reconciled', '=', False),
        ]
        # Without journal entry (no outstanding account), the invoices follow the payment state
        for payment in self.filtered(lambda p: p.move_id and p.invoice_ids):
            payment_lines = payment.move_id.line_ids.filtered_domain(domain)
            invoice_lines = payment.invoice_ids.filtered(lambda move: move.state == 'posted').line_ids.filtered_domain(domain)
            for account in payment_lines.account_id:
                (payment_lines + invoice_lines).filtered_domain([
                    ('account_id', '=', account.id),
                    ('reconciled', '=', False),
                ]).reconcile()

    @api.model
    def _get_tablet_journal(self, journal_id):
        journals = self.env.company._get_route_payment_journals()
        if not is_record_id(journal_id) or journal_id not in journals.ids:
            raise ValidationError(self.env._("Payments can't be registered in this journal."))
        return journals.browse(journal_id)

    @api.model
    def _get_tablet_invoices(self, customer, invoice_ids):
        if not isinstance(invoice_ids, list) or not all(is_record_id(invoice_id) for invoice_id in invoice_ids):
            raise ValidationError(self.env._("Invalid invoices."))
        # Salespeople only read their own invoices; any invoice of the customer can be paid
        invoices = self.env['account.move'].sudo().browse(set(invoice_ids)).exists()
        if len(invoices) != len(set(invoice_ids)) or invoices.filtered(lambda move: (
            move.commercial_partner_id != customer
            or move.company_id != self.env.company
            or move.move_type != 'out_invoice'
            or move.state != 'posted'
        )):
            raise ValidationError(self.env._("The invoices must be posted invoices of the customer."))
        return invoices

    @api.model
    def _get_tablet_date(self, date):
        today = fields.Date.context_today(self)
        if not date:
            return today
        try:
            date = fields.Date.to_date(date)
        except (TypeError, ValueError):
            raise ValidationError(self.env._("Invalid date.")) from None
        if not today - timedelta(days=MAX_PAYMENT_AGE_DAYS) <= date <= today:
            raise ValidationError(self.env._(
                "The payment date must be within the last %s days.", MAX_PAYMENT_AGE_DAYS))
        return date
