from odoo import fields, models


class ResCountry(models.Model):
    _inherit = "res.country"

    mercas_origin = fields.Boolean(string="Merca Origin", default=False)


class ResCountryState(models.Model):
    _inherit = "res.country.state"

    mercas_origin = fields.Boolean(string="Merca Origin", default=False)
