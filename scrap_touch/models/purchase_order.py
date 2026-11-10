from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    scrap_touch_uuid = fields.Char(
        'Touch Screen Identifier', copy=False, readonly=True,
        help="Identifier given by the touch screen that made this purchase, so that sending it twice doesn't duplicate it.")

    _scrap_touch_uuid_unique = models.Constraint(
        'UNIQUE (scrap_touch_uuid)',
        "This purchase was already received from the touch screen.",
    )

