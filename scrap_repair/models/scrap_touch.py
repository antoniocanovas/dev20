from odoo import api, models


class ScrapTouch(models.AbstractModel):
    """ Repair of the vehicles to repair and sell, from their summary on the touch screen. """
    _inherit = 'scrap.touch'

    def _get_vehicle_summary(self, vehicle):
        summary = super()._get_vehicle_summary(vehicle)
        repairs = vehicle._scrap_open_repairs() if vehicle.scrap_unbuild_type == 'refurbish' else self.env['repair.order']
        summary.update({
            'can_repair': (vehicle._scrap_can_repair() and self.env.user.has_group('stock.group_stock_user')),
            'open_repair': repairs[:1].name or '',
        })
        return summary

    @api.model
    def repair_vehicle(self, template_id):
        """ The repair of the vehicle not done yet, or a new one, to open it. """
        return self._get_vehicle(template_id)._scrap_get_repair().id
