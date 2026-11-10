from odoo import models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    def _get_putaway_strategy(self, product, quantity=0, package=None, packaging=None, additional_qty=None):
        """ A vehicle goes to its own location, named after its license plate, whenever it
        enters a location that holds it, as the stock of the warehouse on its receipt. """
        vehicle_location = product.scrap_location_id
        if vehicle_location.active and vehicle_location._child_of(self):
            return vehicle_location
        return super()._get_putaway_strategy(
            product, quantity=quantity, package=package, packaging=packaging, additional_qty=additional_qty)
