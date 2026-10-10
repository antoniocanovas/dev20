from odoo import fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    crotal_id = fields.Many2one('stock.crotal', 'Crotal', index='btree_not_null')
    # Data of the animal, stored to filter and group the lots
    crotal_partner_id = fields.Many2one(related='crotal_id.partner_id', string='Animal Supplier', store=True)
    crotal_sex = fields.Selection(related='crotal_id.sex', string='Sex', store=True)
    crotal_halal = fields.Boolean(related='crotal_id.halal', string='Halal', store=True)
    crotal_breed = fields.Char(related='crotal_id.breed', string='Breed', store=True)
    crotal_quality = fields.Char(related='crotal_id.quality', string='Quality', store=True)
    crotal_birth_date = fields.Date(related='crotal_id.birth_date', string='Birth Date', store=True)
    crotal_slaughter_date = fields.Date(related='crotal_id.slaughter_date', string='Slaughter Date', store=True)
    crotal_birth_country = fields.Char(related='crotal_id.birth_country', string='Born In', store=True)
    crotal_reared_country = fields.Char(related='crotal_id.reared_country', string='Reared In', store=True)
    can_meat_freeze = fields.Boolean(compute='_compute_can_meat_freeze')

    def _compute_can_meat_freeze(self):
        for lot in self:
            lot.can_meat_freeze = bool(lot.product_id.frozen_product_id) and lot.product_id.uom_id.compare(
                lot.product_qty, 0) > 0

    def action_meat_freeze(self):
        """ Freeze the whole stock of the lot (all its locations and pieces). """
        quants = self.quant_ids.filtered(lambda q: q.location_id.usage == 'internal')
        return quants.action_meat_freeze()
