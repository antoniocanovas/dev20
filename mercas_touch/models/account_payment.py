from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    mercas_touch_uuid = fields.Char(
        'Touch Screen Identifier', copy=False, readonly=True,
        help="Identifier given by the touch screen that made this document, so that sending it twice doesn't duplicate it.")

    _mercas_touch_uuid_unique = models.Constraint(
        'UNIQUE (mercas_touch_uuid)',
        "This document was already received from the touch screen.",
    )
