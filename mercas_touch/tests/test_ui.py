import uuid

from odoo import Command
from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestMercasTouchUi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.uom_kg = cls.env.ref('uom.product_uom_kgm')
        cls.customer = cls.env['res.partner'].create({'name': 'Tour Customer', 'customer_rank': 1})
        cls.supplier = cls.env['res.partner'].create({'name': 'Tour Supplier', 'supplier_rank': 1})
        cls.box = cls.env['product.product'].create({
            'name': 'Tour Box', 'type': 'consu', 'is_storable': True, 'is_box': True, 'list_price': 0.0,
            'taxes_id': [Command.clear()], 'supplier_taxes_id': [Command.clear()],
        })
        cls.pear = cls.env['product.product'].create({
            'name': 'Tour Pear', 'type': 'consu', 'is_storable': True, 'tracking': 'lot',
            'uom_id': cls.uom_kg.id, 'list_price': 2.0, 'box_product_id': cls.box.id,
            'taxes_id': [Command.clear()], 'supplier_taxes_id': [Command.clear()],
        })
        cls.user = new_test_user(
            cls.env, login='touch_tour', name='Touch Tour',
            groups='sales_team.group_sale_salesman_all_leads,purchase.group_purchase_user,'
                   'stock.group_stock_user,stock.group_production_lot,account.group_account_invoice',
        )
        cls.env['mercas.touch'].with_user(cls.user).purchase({
            'uuid': str(uuid.uuid4()), 'partner_id': cls.supplier.id,
            'lines': [{'product_id': cls.pear.id, 'qty': 100.0, 'price_unit': 1.0, 'lot_name': 'TOUR-LOT'}],
        })
        cls.lot = cls.env['stock.lot'].search([('name', '=', 'TOUR-LOT')])

    def test_sale(self):
        if not self.env['account.journal'].search([('type', 'in', ('bank', 'cash')), ('company_id', '=', self.env.company.id)]):
            self.env['account.journal'].create({'name': 'Counter Cash', 'type': 'cash', 'code': 'TCSH'})
        self.start_tour('/odoo/mercas-touch', 'mercas_touch_sale_tour', login='touch_tour')
        order = self.env['sale.order'].search([('partner_id', '=', self.customer.id)])
        self.assertEqual(order.state, 'sale')
        line = order.order_line.filtered(lambda l: l.product_id == self.pear)
        self.assertEqual(line.lot_id.name, 'TOUR-LOT')
        self.assertEqual(line.product_uom_qty, 12)
        self.assertEqual(line.price_unit, 1.5)
        self.assertEqual(line.box_qty, 2)
        self.assertTrue(all(picking.state == 'done' for picking in order.picking_ids))
        invoice = order.invoice_ids
        self.assertEqual(invoice.state, 'posted')
        self.assertIn(invoice.payment_state, ('paid', 'in_payment'), "Invoiced and collected from the sale")

    def test_purchase_and_scrap(self):
        self.start_tour('/odoo/mercas-touch', 'mercas_touch_purchase_tour', login='touch_tour')
        lot = self.env['stock.lot'].search([('name', '=', 'TOUR-NEW'), ('product_id', '=', self.pear.id)])
        self.assertEqual(lot.partner_id, self.supplier)
        self.assertEqual(lot.scrap_kg, 5)
        self.assertEqual(lot.product_qty, 75)

    def test_payment(self):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.customer.id,
            'invoice_line_ids': [Command.create({'product_id': self.pear.id, 'quantity': 50, 'price_unit': 2.0})],
        })
        invoice.action_post()
        if not self.env['account.journal'].search([('type', 'in', ('bank', 'cash')), ('company_id', '=', self.env.company.id)]):
            self.env['account.journal'].create({'name': 'Counter Cash', 'type': 'cash', 'code': 'TCSH'})
        self.start_tour('/odoo/mercas-touch', 'mercas_touch_payment_tour', login='touch_tour')
        self.assertEqual(invoice.payment_state, 'partial')
        self.assertEqual(invoice.amount_residual, 40.0)

    def test_quick_prices(self):
        self.start_tour('/odoo/mercas-touch', 'mercas_touch_price_tour', login='touch_tour')
        order = self.env['sale.order'].search([('partner_id', '=', self.customer.id)])
        lines = order.order_line.filtered(lambda l: l.product_id == self.pear).sorted('id')
        self.assertEqual(lines.mapped('product_uom_qty'), [10, 5])
        self.assertEqual(lines.mapped('price_unit'), [2.5, 3.0])

    def test_resume_quotation(self):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [Command.create({
                'product_id': self.pear.id, 'product_uom_qty': 7, 'lot_id': self.lot.id,
            })],
        })
        self.start_tour('/odoo/mercas-touch', 'mercas_touch_quotation_tour', login='touch_tour')
        self.assertEqual(order.state, 'sale', "The quotation resumed is the one sold")
        self.assertEqual(order.order_line.filtered(lambda l: l.product_id == self.pear).mapped('product_uom_qty'), [7, 4])

    def test_purchase_drafts(self):
        other_supplier = self.env['res.partner'].create({'name': 'Backend Supplier', 'supplier_rank': 1})
        other = self.env['purchase.order'].create({'partner_id': other_supplier.id})
        self.start_tour('/odoo/mercas-touch', 'mercas_touch_purchase_drafts_tour', login='touch_tour')
        first = self.env['purchase.order'].search([('partner_id', '=', self.supplier.id), ('state', '=', 'purchase')],
                                                  order='id desc', limit=1)
        self.assertEqual(first.order_line.filtered(lambda l: l.product_id == self.pear).lot_id.name, 'DRAFT-A')
        self.assertEqual(other.state, 'draft', "The other purchase is kept in draft")
        line = other.order_line.filtered(lambda l: l.product_id == self.pear)
        self.assertEqual((line.product_qty, line.mercas_touch_lot_name), (12, 'DRAFT-B'))
        self.assertFalse(self.env['stock.lot'].search([('name', '=', 'DRAFT-B')]),
                         "No lot is made before the purchase is received")

    def test_to_invoice(self):
        order = self.env['mercas.touch'].with_user(self.user).sell({
            'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id,
            'lines': [{'product_id': self.pear.id, 'lot_id': self.lot.id, 'qty': 3.0, 'price_unit': 2.0}],
        })['order']
        self.start_tour('/odoo/mercas-touch', 'mercas_touch_to_invoice_tour', login='touch_tour')
        self.assertEqual(self.env['sale.order'].browse(order['id']).invoice_status, 'invoiced')
        purchase = self.env['purchase.order'].search([('partner_id', '=', self.supplier.id)])
        self.assertTrue(purchase.invoice_ids, "The bill was made from the purchase")
