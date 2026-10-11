from odoo import fields, models


class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    meat_use = fields.Selection([
        ('cutting', 'Cutting'),
        ('production', 'Production'),
    ], string='Meat Use', default='cutting', required=True,
        help="Cutting: a cutting method of the product (carcass or piece), whose components are its cuts, "
             "used in reverse on the cutting screen.\n"
             "Production: a recipe made on the production screen, e.g. sausages, from weighed ingredient "
             "packages.")
