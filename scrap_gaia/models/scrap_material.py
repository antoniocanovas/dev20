from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ScrapMaterial(models.Model):
    _name = 'scrap.material'
    _description = "GAIA Material"
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint('UNIQUE(name)', "There is already a GAIA material with this name.")


class ProductScrapMaterial(models.Model):
    """ The share of the weight of a product of each material, estimated: copied from its
    scrap template, editable. """
    _name = 'product.scrap.material'
    _description = "GAIA Material of a Product"
    _order = 'sequence, id'

    product_tmpl_id = fields.Many2one('product.template', required=True, index=True, ondelete='cascade')
    scrap_material_id = fields.Many2one('scrap.material', string="Material", required=True, ondelete='restrict')
    sequence = fields.Integer(related='scrap_material_id.sequence')
    percent = fields.Float("Estimated (%)", digits=(5, 2))
    weight = fields.Float(
        "Weight", digits='Stock Weight', compute='_compute_weight',
        help="Its share of the weight of the product.")

    _material_unique = models.Constraint(
        'UNIQUE(product_tmpl_id, scrap_material_id)', "Each material only once in a product.")

    @api.depends('percent', 'product_tmpl_id.weight')
    def _compute_weight(self):
        for line in self:
            line.weight = line.product_tmpl_id.weight * line.percent / 100

    @api.constrains('percent', 'product_tmpl_id')
    def _check_percent(self):
        for template in self.product_tmpl_id:
            lines = template.scrap_material_line_ids
            if any(line.percent < 0 for line in lines):
                raise ValidationError(self.env._("The GAIA percentages of %s can't be negative.", template.display_name))
            if sum(lines.mapped('percent')) > 100.005:
                raise ValidationError(self.env._("The GAIA percentages of %s add up to more than 100%%.", template.display_name))

    def _scrap_copy_values(self):
        return [fields.Command.create({'scrap_material_id': line.scrap_material_id.id, 'percent': line.percent})
                for line in self]


class StockPickingScrapMaterial(models.Model):
    """ The weight of each material of a delivery, for GAIA: computed from its products,
    editable. """
    _name = 'stock.picking.scrap.material'
    _description = "GAIA Material of a Transfer"
    _order = 'sequence, id'

    picking_id = fields.Many2one('stock.picking', required=True, index=True, ondelete='cascade')
    scrap_material_id = fields.Many2one('scrap.material', string="Material", required=True, ondelete='restrict')
    sequence = fields.Integer(related='scrap_material_id.sequence')
    weight = fields.Float("Weight", digits='Stock Weight')
    weight_uom_name = fields.Char(related='picking_id.scrap_weight_uom_name')
