from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    mercas_touch_uuid = fields.Char(
        'Touch Screen Identifier', copy=False, readonly=True,
        help="Identifier given by the touch screen that made this document, so that sending it twice doesn't duplicate it.")

    _mercas_touch_uuid_unique = models.Constraint(
        'UNIQUE (mercas_touch_uuid)',
        "This document was already received from the touch screen.",
    )


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    mercas_touch_lot_name = fields.Char(
        'Lot to Receive', copy=False,
        help="Name of the lot asked for on the touch screen, given to the lot when the purchase is received.")
