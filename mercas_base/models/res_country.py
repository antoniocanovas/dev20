from odoo import fields, models


class ResCountry(models.Model):
    _inherit = "res.country"

    mercas_origin = fields.Boolean(string="Merca Origin", default=False)
