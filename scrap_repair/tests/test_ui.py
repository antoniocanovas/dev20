import uuid

from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestScrapRepairUi(HttpCase):

    def test_repair_tour(self):
        supplier = self.env['res.partner'].create({'name': 'Tour Repair Supplier'})
        vehicle = self.env['product.product'].create({
            'name': 'Tour Repair Van', 'type': 'consu', 'is_storable': True, 'tracking': 'serial',
            'is_template': True,
        })
        new_test_user(
            self.env, login='scrap_repair_tour', name='Scrap Repair Tour',
            groups='purchase.group_purchase_user,stock.group_stock_user,stock.group_production_lot',
        )
        self.env['scrap.touch'].purchase_entry({
            'uuid': str(uuid.uuid4()), 'partner_id': supplier.id, 'unbuild_type': 'refurbish',
            'lines': [{'product_id': vehicle.id, 'lot_name': 'TOURREP1', 'price_unit': 100.0}],
        })
        self.start_tour('/odoo/scrap-touch', 'scrap_repair_tour', login='scrap_repair_tour')
        repair = self.env['repair.order'].search([('product_id.scrap_template_id', '=', vehicle.product_tmpl_id.id)])
        self.assertEqual(len(repair), 1)
        self.assertEqual(repair.lot_id.name, 'TOURREP1')
