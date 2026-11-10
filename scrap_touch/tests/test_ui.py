import uuid
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestScrapTouchUi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supplier = cls.env['res.partner'].create({'name': 'Tour Scrap Supplier'})
        cls.vehicle = cls.env['product.product'].create({
            'name': 'Tour Vehicle', 'type': 'consu', 'is_storable': True, 'tracking': 'serial',
            'is_template': True,
        })
        cls.user = new_test_user(
            cls.env, login='scrap_tour', name='Scrap Tour',
            groups='base.group_partner_manager,purchase.group_purchase_user,stock.group_stock_user,stock.group_production_lot',
        )

    def test_scrap_entry(self):
        self.start_tour('/odoo/scrap-touch', 'scrap_touch_entry_tour', login='scrap_tour')
        order = self.env['purchase.order'].search([('partner_id', '=', self.supplier.id)])
        self.assertEqual(order.state, 'purchase')
        self.assertEqual(order.order_line.mapped('price_unit'), [1250.0, 900.0])
        self.assertEqual(order.unbuild_type, 'main')
        self.assertTrue(all(picking.state == 'done' for picking in order.picking_ids))
        self.assertEqual(order.order_line.mapped('scrap_lot_name'), ['1234ABC', '5678BCD'])
        lots = self.env['stock.lot'].search([('product_id.scrap_template_id', '=', self.vehicle.product_tmpl_id.id)], order='name')
        self.assertEqual(lots.mapped('name'), ['1234ABC', '5678BCD'],
                         "The license plates are written in capitals, without spaces nor hyphens")

    def test_new_supplier(self):
        self.start_tour('/odoo/scrap-touch', 'scrap_touch_new_partner_tour', login='scrap_tour')
        partner = self.env['res.partner'].search([('name', '=', 'Brand New Yard')])
        self.assertEqual(len(partner), 1)
        self.assertEqual(partner.city, 'Cartagena')
        order = self.env['purchase.order'].search([('partner_id', '=', partner.id)])
        self.assertEqual(order.state, 'purchase')
        self.assertEqual(order.picking_ids.state, 'done', "Received later, from the purchases to receive")
        lot = self.env['stock.lot'].search([('product_id.scrap_template_id', '=', self.vehicle.product_tmpl_id.id), ('name', '=', '4321ZZZ')])
        self.assertEqual(len(lot), 1)

    def test_resale_entry(self):
        self.start_tour('/odoo/scrap-touch', 'scrap_touch_resale_tour', login='scrap_tour')
        order = self.env['purchase.order'].search([('partner_id', '=', self.supplier.id)])
        self.assertEqual(order.unbuild_type, 'refurbish')
        self.assertEqual(order.state, 'purchase')
        self.assertEqual(order.picking_ids.state, 'done')

    def test_cat(self):
        """ Decontamination, dismantling and vehicles. """
        self.env.company.write({'decontamination_days': 10, 'scrap_days': 30})
        Touch = self.env['scrap.touch']
        for plate, unbuild_type in (('TOUR001', 'main'), ('TOUR002', 'refurbish')):
            Touch.purchase_entry({
                'uuid': str(uuid.uuid4()), 'partner_id': self.supplier.id, 'unbuild_type': unbuild_type,
                'lines': [{'product_id': self.vehicle.id, 'lot_name': plate, 'price_unit': 100.0}],
            })
        vehicle = self.env['product.template'].search([('scrap_lot_name', '=', 'TOUR001')])
        today = fields.Date.context_today(vehicle)
        vehicle.discharge_date = today - timedelta(days=12)
        # Only this one late, also in a database with other vehicles
        self.env['product.template'].search([
            ('id', '!=', vehicle.id), ('scrap_unbuild_type', '=', 'main'), ('decontamination_date', '=', False),
            ('discharge_date', '!=', False)]).decontamination_date = today
        # Its bill of materials, copied from the template: dismantled on the screen
        Product = self.env['product.product']
        wheel = Product.create({'name': 'Tour Wheel', 'type': 'consu', 'is_storable': True})
        engine = Product.create({'name': 'Tour Engine', 'type': 'consu', 'is_storable': True})
        self.env['mrp.bom'].create({
            'product_tmpl_id': vehicle.id,
            'bom_line_ids': [
                fields.Command.create({'product_id': wheel.id, 'product_qty': 2}),
                fields.Command.create({'product_id': engine.id, 'product_qty': 1}),
            ],
        })
        stock = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1).lot_stock_id
        shelf = self.env['stock.location'].create({'name': 'Tour Shelf', 'location_id': stock.id})
        oil = Product.create({
            'name': 'Tour Oil', 'type': 'consu', 'is_storable': True,
            'uom_id': self.env.ref('uom.product_uom_litre').id,
        })
        self.env.company.scrap_waste_product_ids = oil
        self.start_tour('/odoo/scrap-touch', 'scrap_touch_cat_tour', login='scrap_tour')
        self.assertEqual(vehicle.decontamination_date, today)
        self.assertEqual(vehicle.scrap_date, today)
        part = vehicle.scrap_dismantle_line_ids.filtered(lambda part: part.stage == 'dismantling')
        self.assertEqual((part.product_id, part.quantity, part.result, part.condition, part.location_dest_id),
                         (wheel, 2, 'dismantled', 'good', shelf))
        self.assertEqual(wheel.with_context(location=shelf.id).qty_available, 2)
        self.assertEqual(vehicle.bom_ids.bom_line_ids.mapped('product_qty'), [0, 1], "The engine is left")
        waste_zone = self.env.company.scrap_waste_location_id
        self.assertEqual(oil.with_context(location=waste_zone.id).qty_available, 5, "3 litres and 2, corrected")
