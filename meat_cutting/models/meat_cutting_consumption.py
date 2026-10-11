from odoo import api, fields, models
from odoo.exceptions import UserError


class MeatCuttingConsumption(models.Model):
    _name = 'meat.cutting.consumption'
    _description = "Meat Cutting Ingredient"
    _order = 'id desc'

    session_id = fields.Many2one('meat.cutting.session', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='session_id.company_id', store=True)
    product_id = fields.Many2one('product.product', 'Ingredient', required=True)
    package_id = fields.Many2one('stock.package', 'Package')
    lot_id = fields.Many2one('stock.lot', 'Lot')
    expiration_date = fields.Datetime(related='lot_id.expiration_date')
    location_id = fields.Many2one('stock.location', 'Location', required=True)
    weight = fields.Float('Weight', digits='Product Unit', required=True)
    uom_id = fields.Many2one(related='product_id.uom_id')
    user_id = fields.Many2one('res.users', 'Operator', default=lambda self: self.env.user)
    date = fields.Datetime(default=fields.Datetime.now, required=True)

    _weight_positive = models.Constraint(
        'CHECK (weight > 0)',
        "The weight must be positive.",
    )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_done(self):
        if any(consumption.session_id.state == 'done' for consumption in self):
            raise UserError(self.env._("You cannot delete ingredients of a validated production."))

    def _get_cutting_screen_values(self):
        return [{
            'id': consumption.id,
            'product_name': consumption.product_id.display_name,
            'package_name': consumption.package_id.name or '',
            'lot_name': consumption.lot_id.name or '',
            'expiration_date': fields.Datetime.to_string(consumption.expiration_date) or '',
            'weight': consumption.weight,
            'uom_name': consumption.uom_id.name,
        } for consumption in self]
