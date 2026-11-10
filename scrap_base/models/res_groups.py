from odoo import api, models


class ResGroups(models.Model):
    _inherit = 'res.groups'

    @api.model
    def _scrap_base_enable_lots(self):
        """ Enable "Lots & Serial Numbers", as the setting of Inventory does: the vehicles are
        tracked by their license plate. Called each time the module is installed or updated. """
        groups = self.env.ref('base.group_user') | self.env.ref('base.group_portal')
        groups._apply_group(self.env.ref('stock.group_production_lot'))

    @api.model
    def _scrap_base_enable_analytic(self):
        """ Enable "Analytic Accounting", as the setting of Accounting does: each vehicle has
        its analytic account. Called each time the module is installed or updated. """
        self.env.ref('base.group_user')._apply_group(self.env.ref('analytic.group_analytic_accounting'))

    @api.model
    def _scrap_base_enable_locations(self):
        """ Enable "Storage Locations", as the setting of Inventory does: each vehicle has its
        location. Called each time the module is installed or updated. """
        self.env.ref('base.group_user')._apply_group(self.env.ref('stock.group_stock_multi_locations'))

    @api.model
    def _scrap_base_enable_routings(self):
        """ Enable "Work Orders", as the setting of Manufacturing does: the bills of materials
        of the vehicles have the operations to take them to pieces. Called each time the module
        is installed or updated. """
        self.env.ref('base.group_user')._apply_group(self.env.ref('mrp.group_mrp_routings'))
