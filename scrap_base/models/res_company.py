from odoo import api, fields, models

# Kinds of entry that buy whole vehicles: each one is bought as a product of its own, with its
# analytic account and its location, under the ones set in the company for its kind
VEHICLE_TYPES = ('main', 'refurbish')
# Parent locations created by default for the vehicles of each kind of entry
DEFAULT_LOCATION_NAMES = {
    'main': "Para desguazar",
    'refurbish': "Compra / Venta",
}
WASTE_LOCATION_NAME = "Zona de desecho"


class ResCompany(models.Model):
    _inherit = 'res.company'

    scrap_main_sequence_id = fields.Many2one(
        'ir.sequence', string="Vehicles to Dismantle Sequence",
        domain="[('company_id', 'in', (id, False))]",
        help="Internal reference given to each vehicle bought to dismantle (purchases of scrap type "
             "'Vehículo o Parte para desguace') when it is received.")
    scrap_refurbish_sequence_id = fields.Many2one(
        'ir.sequence', string="Vehicles to Repair and Sell Sequence",
        domain="[('company_id', 'in', (id, False))]",
        help="Internal reference given to each vehicle bought to repair and sell whole (purchases "
             "of scrap type 'Para compra/venta') when it is received.")
    scrap_main_analytic_plan_id = fields.Many2one(
        'account.analytic.plan', string="Vehicles to Dismantle Analytic Plan",
        help="Plan of the analytic account created for each vehicle bought to dismantle, when its "
             "purchase is confirmed.")
    scrap_refurbish_analytic_plan_id = fields.Many2one(
        'account.analytic.plan', string="Vehicles to Repair and Sell Analytic Plan",
        help="Plan of the analytic account created for each vehicle bought to repair and sell "
             "whole, when its purchase is confirmed.")
    scrap_main_location_id = fields.Many2one(
        'stock.location', string="Vehicles to Dismantle Location",
        domain="[('usage', '=', 'internal'), ('company_id', 'in', (id, False))]",
        help="Parent of the location created for each vehicle bought to dismantle, named after "
             "its license plate, where it is received.")
    scrap_refurbish_location_id = fields.Many2one(
        'stock.location', string="Vehicles to Repair and Sell Location",
        domain="[('usage', '=', 'internal'), ('company_id', 'in', (id, False))]",
        help="Parent of the location created for each vehicle bought to repair and sell whole, "
             "named after its license plate, where it is received.")

    scrap_waste_location_id = fields.Many2one(
        'stock.location', string="Waste Zone",
        domain="[('usage', '=', 'internal'), ('company_id', 'in', (id, False))]",
        help="Where the waste taken out of the vehicles while decontaminating them (oil, fuel, "
             "batteries...) enters the stock by default.")
    scrap_waste_product_ids = fields.Many2many(
        'product.product', 'res_company_scrap_waste_product_rel', 'company_id', 'product_id',
        string="Waste Products", domain="[('type', '=', 'consu'), ('company_id', 'in', (id, False))]",
        help="Waste taken out of the vehicles while decontaminating them, offered by the "
             "decontamination of the touch screen.")

    # Legal deadlines of the vehicles to dismantle, as in scrap_unbuild (Odoo 17)
    decontamination_days = fields.Integer(
        'Decontamination Days',
        help="Legal days to decontaminate a vehicle to dismantle, from its discharge date.")
    scrap_days = fields.Integer(
        'Dismantling Days',
        help="Legal days to dismantle a vehicle, from its discharge date.")

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies.sudo()._scrap_set_defaults()
        return companies

    def _get_scrap_sequence(self, unbuild_type):
        """ Sequence of the internal references of the vehicles of a kind of entry, if any. """
        self.ensure_one()
        return self[f'scrap_{unbuild_type}_sequence_id'] if unbuild_type in VEHICLE_TYPES else self.env['ir.sequence']

    def _get_scrap_analytic_plan(self, unbuild_type):
        self.ensure_one()
        return self[f'scrap_{unbuild_type}_analytic_plan_id']

    def _get_scrap_location(self, unbuild_type):
        self.ensure_one()
        return self[f'scrap_{unbuild_type}_location_id']

    @api.model
    def _scrap_base_set_defaults(self):
        """ Called when the module is installed. """
        self.search([])._scrap_set_defaults()

    def _scrap_set_defaults(self):
        """ The analytic plans of the module and a location in the stock of the first
        warehouse, for each kind of entry and for the waste, where the company has none. """
        plans = {
            'main': self.env.ref('scrap_base.analytic_plan_scrap_main', raise_if_not_found=False),
            'refurbish': self.env.ref('scrap_base.analytic_plan_scrap_refurbish', raise_if_not_found=False),
        }
        for company in self:
            warehouse = self.env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
            vals = {}
            for unbuild_type in VEHICLE_TYPES:
                plan_field = f'scrap_{unbuild_type}_analytic_plan_id'
                if not company[plan_field] and plans[unbuild_type]:
                    vals[plan_field] = plans[unbuild_type].id
                location_field = f'scrap_{unbuild_type}_location_id'
                if not company[location_field] and warehouse.lot_stock_id:
                    vals[location_field] = self.env['stock.location'].create({
                        'name': DEFAULT_LOCATION_NAMES[unbuild_type],
                        'location_id': warehouse.lot_stock_id.id,
                        'usage': 'internal',
                        'company_id': company.id,
                    }).id
            if not company.scrap_waste_location_id and warehouse.lot_stock_id:
                vals['scrap_waste_location_id'] = self.env['stock.location'].create({
                    'name': WASTE_LOCATION_NAME,
                    'location_id': warehouse.lot_stock_id.id,
                    'usage': 'internal',
                    'company_id': company.id,
                }).id
            if vals:
                company.write(vals)
