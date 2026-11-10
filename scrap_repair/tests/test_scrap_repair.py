import uuid

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestScrapRepair(TransactionCase):
    """ Repair of the vehicles to repair and sell: its parts and services, and its sales once
    the vehicle is sold, go to the analytic account of the vehicle. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supplier = cls.env['res.partner'].create({'name': 'CAT Repair Supplier'})
        cls.customer = cls.env['res.partner'].create({'name': 'CAT Repair Customer'})
        cls.template = cls.env['product.product'].create({
            'name': 'CAT Repair Van', 'type': 'consu', 'is_storable': True, 'tracking': 'serial',
            'is_template': True, 'supplier_taxes_id': [Command.clear()],
        })
        cls.part = cls.env['product.product'].create({
            'name': 'CAT Repair Clutch', 'type': 'consu', 'is_storable': True,
            'standard_price': 80.0, 'list_price': 150.0,
        })
        cls.labour = cls.env['product.product'].create({
            'name': 'CAT Repair Labour', 'type': 'service', 'standard_price': 25.0, 'list_price': 40.0,
        })
        cls.stock = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1).lot_stock_id
        cls.env['stock.quant']._update_available_quantity(cls.part, cls.stock, 10)
        cls.worker = new_test_user(
            cls.env, login='cat_repair_worker',
            groups='stock.group_stock_user,stock.group_production_lot,sales_team.group_sale_salesman')
        cls.touch = cls.env['scrap.touch'].with_user(cls.worker)

    def _buy(self, plate, unbuild_type='refurbish', receive=True):
        result = self.env['scrap.touch'].purchase_entry({
            'uuid': str(uuid.uuid4()), 'partner_id': self.supplier.id, 'unbuild_type': unbuild_type,
            'lines': [{'product_id': self.template.id, 'lot_name': plate, 'price_unit': 1000.0}],
        }, receive)
        return self.env['purchase.order'].browse(result['id']).order_line.product_id.product_tmpl_id

    def _analytic_amounts(self, vehicle):
        account = vehicle.scrap_analytic_account_id
        lines = self.env['account.analytic.line'].search([(account.plan_id._column_name(), '=', account.id)])
        return sorted(lines.mapped('amount'))

    def _repair(self, repair):
        repair.move_ids = [Command.create({
            'product_id': self.part.id, 'product_uom_qty': 1, 'repair_line_type': 'add',
        })]
        repair.repair_service_line_ids = [Command.create({'product_id': self.labour.id, 'quantity': 2})]
        repair.action_validate()
        repair.move_ids.quantity = 1
        repair.move_ids.picked = True
        repair.action_repair_end()
        self.assertEqual(repair.state, 'done')

    def test_repair_in_stock(self):
        """ In stock: repaired to sell it, without customer, where it is; the clutch and the
        labour, at their cost, are costs of the vehicle. """
        vehicle = self._buy('REP0001')
        summary = self.touch.get_vehicle(vehicle.id)
        self.assertTrue(summary['can_repair'])
        self.assertFalse(summary['open_repair'])

        repair = self.env['repair.order'].browse(self.touch.repair_vehicle(vehicle.id))
        self.assertEqual(repair.product_id.product_tmpl_id, vehicle)
        self.assertEqual(repair.lot_id.name, 'REP0001')
        self.assertFalse(repair.partner_id)
        self.assertEqual(repair.product_location_src_id, vehicle.scrap_location_id)
        self.assertEqual(self.touch.repair_vehicle(vehicle.id), repair.id, "The one not done yet, again")
        self.assertEqual(self.touch.get_vehicle(vehicle.id)['open_repair'], repair.name)

        self._repair(repair)
        self.assertEqual(self._analytic_amounts(vehicle), [-80.0, -50.0], "The clutch and 2 hours of labour")
        self.assertEqual(vehicle.qty_available, 1, "Still in stock, where it was")
        self.assertNotEqual(self.touch.repair_vehicle(vehicle.id), repair.id, "Done: a new one")

    def test_repair_sold(self):
        """ Sold: the repair is of its customer, and its sales also go to the vehicle. """
        vehicle = self._buy('REP0002')
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [Command.create({'product_id': vehicle.product_variant_id.id, 'product_uom_qty': 1})],
        })
        order.action_confirm()
        picking = order.picking_ids
        picking.move_ids.picked = True
        picking.button_validate()
        self.assertEqual(vehicle.qty_available, 0)

        repair = self.env['repair.order'].browse(self.touch.repair_vehicle(vehicle.id))
        self.assertEqual(repair.partner_id, self.customer)
        self.assertEqual(repair.lot_id.name, 'REP0002')
        self.assertEqual(repair.product_location_src_id.usage, 'customer')
        self._repair(repair)
        self.assertEqual(self._analytic_amounts(vehicle), [-80.0, -50.0])

        repair.action_create_invoice()
        invoice = repair.invoice_ids
        account = str(vehicle.scrap_analytic_account_id.id)
        self.assertTrue(invoice.invoice_line_ids)
        for line in invoice.invoice_line_ids:
            self.assertEqual(line.analytic_distribution, {account: 100}, "The sales of the repair, to the vehicle")

    def test_repair_quotation(self):
        """ The quotation of the repair of a vehicle sold, also to the vehicle. """
        vehicle = self._buy('REP0003')
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [Command.create({'product_id': vehicle.product_variant_id.id, 'product_uom_qty': 1})],
        })
        order.action_confirm()
        order.picking_ids.move_ids.picked = True
        order.picking_ids.button_validate()
        repair = self.env['repair.order'].browse(self.touch.repair_vehicle(vehicle.id))
        repair.repair_service_line_ids = [Command.create({'product_id': self.labour.id, 'quantity': 1})]
        repair.action_create_sale_order()
        account = str(vehicle.scrap_analytic_account_id.id)
        self.assertEqual(repair.sale_order_id.order_line.mapped('analytic_distribution'), [{account: 100}])

    def test_not_repairable(self):
        """ Neither received nor sold, or a vehicle to dismantle: it isn't repaired. """
        to_receive = self._buy('REP0004', receive=False)
        self.assertFalse(self.touch.get_vehicle(to_receive.id)['can_repair'])
        with self.assertRaises(UserError):
            self.touch.repair_vehicle(to_receive.id)
        to_dismantle = self._buy('REP0005', unbuild_type='main')
        self.assertFalse(self.touch.get_vehicle(to_dismantle.id)['can_repair'])
        with self.assertRaises(UserError):
            self.touch.repair_vehicle(to_dismantle.id)
