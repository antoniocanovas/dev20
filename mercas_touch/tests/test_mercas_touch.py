import uuid

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


class MercasTouchCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.uom_kg = cls.env.ref('uom.product_uom_kgm')
        cls.supplier = cls.env['res.partner'].create({'name': 'Touch Supplier', 'supplier_rank': 1})
        cls.customer = cls.env['res.partner'].create({'name': 'Touch Customer', 'customer_rank': 1})
        cls.box = cls.env['product.product'].create({
            'name': 'Touch Box',
            'type': 'consu',
            'is_storable': True,
            'is_box': True,
            'list_price': 1.0,
            'standard_price': 1.0,
            'taxes_id': [Command.clear()],
            'supplier_taxes_id': [Command.clear()],
        })
        cls.pear = cls.env['product.product'].create({
            'name': 'Touch Pear',
            'type': 'consu',
            'is_storable': True,
            'tracking': 'lot',
            'uom_id': cls.uom_kg.id,
            'list_price': 2.0,
            'box_product_id': cls.box.id,
            'taxes_id': [Command.clear()],
            'supplier_taxes_id': [Command.clear()],
        })
        cls.lettuce = cls.env['product.product'].create({
            'name': 'Touch Lettuce',
            'type': 'consu',
            'is_storable': True,
            'list_price': 0.8,
            'taxes_id': [Command.clear()],
            'supplier_taxes_id': [Command.clear()],
        })
        # The counter: sells, buys, moves boxes and collects payments
        cls.user = new_test_user(
            cls.env, login='touch_counter', name='Touch Counter',
            groups='sales_team.group_sale_salesman_all_leads,purchase.group_purchase_user,'
                   'stock.group_stock_user,stock.group_production_lot,account.group_account_invoice',
        )
        cls.Touch = cls.env['mercas.touch'].with_user(cls.user)

    @classmethod
    def _buy(cls, qty=100.0, price=1.0, lot_name=None, **line):
        vals = {'product_id': cls.pear.id, 'qty': qty, 'price_unit': price, **line}
        if lot_name:
            vals['lot_name'] = lot_name
        return cls.Touch.purchase({'uuid': str(uuid.uuid4()), 'partner_id': cls.supplier.id, 'lines': [vals]})


@tagged('post_install', '-at_install')
class TestMercasTouch(MercasTouchCommon):

    def test_screen_data(self):
        data = self.Touch.get_screen_data()
        products = {product['id']: product for product in data['products']}
        self.assertEqual(products[self.pear.id]['tracking'], 'lot')
        self.assertEqual(products[self.pear.id]['box_product_id'], self.box.id)
        self.assertTrue(products[self.box.id]['is_box'])
        self.assertEqual(products[self.pear.id]['categ_id'], self.pear.categ_id.id)
        self.assertTrue(data['journals'])

    def test_search_partners(self):
        found = self.Touch.search_partners('Touch', 'customer')
        self.assertEqual(found[0]['id'], self.customer.id, "The customers come first")
        found = self.Touch.search_partners('Touch', 'supplier')
        self.assertEqual(found[0]['id'], self.supplier.id, "The suppliers come first")
        with self.assertRaises(ValidationError):
            self.Touch.search_partners('', 'employee')

    def test_purchase_creates_lots_and_receives(self):
        result = self._buy(120.0, 0.9, box_qty=6, box_product_id=self.box.id, firm=True)
        order = self.env['purchase.order'].browse(result['order']['id'])
        self.assertEqual(order.state, 'purchase')
        self.assertTrue(result['order']['received'])
        line = order.order_line.filtered(lambda l: l.product_id == self.pear)
        self.assertTrue(line.lot_id, "A tracked line gets a new lot")
        self.assertEqual(line.lot_id.partner_id, self.supplier)
        self.assertTrue(line.lot_id.mercas_firm_negotiation)
        self.assertEqual(line.price_unit, 0.9)
        self.assertEqual(self.pear.with_context(lot_id=line.lot_id.id).qty_available, 120.0)
        self.assertEqual(order.order_line.filtered(lambda l: l.product_id == self.box).product_qty, 6,
                         "The boxes come in the same receipt")
        self.assertEqual(result['order']['lots'][0]['lot_name'], line.lot_id.name)

    def test_purchase_with_lot_name_and_origin(self):
        spain = self.env.ref('base.es')
        result = self._buy(50.0, lot_name='PEAR-001', origin_country_id=spain.id)
        lot = self.env['stock.lot'].search([('name', '=', 'PEAR-001'), ('product_id', '=', self.pear.id)])
        self.assertEqual(len(lot), 1)
        self.assertEqual(lot.origin_country_id, spain)
        self.assertEqual(result['order']['lots'][0]['lot_id'], lot.id)

    def test_purchase_is_idempotent(self):
        vals = {'uuid': str(uuid.uuid4()), 'partner_id': self.supplier.id,
                'lines': [{'product_id': self.pear.id, 'qty': 10.0}]}
        first = self.Touch.purchase(vals)
        second = self.Touch.purchase(vals)
        self.assertEqual(first['order']['id'], second['order']['id'])
        self.assertEqual(self.env['purchase.order'].search_count([('mercas_touch_uuid', '=', vals['uuid'])]), 1)

    def test_product_lots(self):
        self._buy(30.0, lot_name='OLD')
        self._buy(20.0, lot_name='NEW')
        lots = self.Touch.get_product_lots(self.pear.id)
        self.assertEqual([lot['name'] for lot in lots], ['OLD', 'NEW'], "Oldest lot first")
        self.assertEqual(lots[0]['available'], 30.0)
        self.assertEqual(lots[0]['supplier'], self.supplier.name)
        # A lot already invoiced to its supplier isn't sold anymore
        self.env['stock.lot'].search([('name', '=', 'OLD')]).invoiced = True
        self.assertEqual([lot['name'] for lot in self.Touch.get_product_lots(self.pear.id)], ['NEW'])

    def test_sell_with_lot_boxes_price_and_note(self):
        self._buy(100.0, lot_name='SELL-1')
        lot = self.env['stock.lot'].search([('name', '=', 'SELL-1')])
        result = self.Touch.sell({
            'uuid': str(uuid.uuid4()),
            'partner_id': self.customer.id,
            'lines': [
                {'product_id': self.pear.id, 'lot_id': lot.id, 'qty': 40.0, 'price_unit': 1.75,
                 'box_qty': 4, 'box_product_id': self.box.id, 'note': 'Ripe ones'},
                {'product_id': self.lettuce.id, 'qty': 3.0},
            ],
        })
        self.assertNotIn('action', result)
        order = self.env['sale.order'].browse(result['order']['id'])
        self.assertEqual(order.state, 'sale')
        self.assertTrue(result['order']['delivered'])
        pear_line = order.order_line.filtered(lambda l: l.product_id == self.pear)
        self.assertEqual(pear_line.lot_id, lot)
        self.assertEqual(pear_line.price_unit, 1.75)
        self.assertEqual(pear_line.name.splitlines()[-1], 'Ripe ones', "The text goes under the description")
        self.assertEqual(order.order_line.filtered(lambda l: l.product_id == self.box).product_uom_qty, 4)
        self.assertEqual(self.pear.with_context(lot_id=lot.id).qty_available, 60.0)
        self.assertEqual(self.Touch.get_product_lots(self.pear.id)[0]['available'], 60.0)
        # The customer now has the boxes
        info = self.Touch.get_partner_info(self.customer.id)
        self.assertEqual(info['boxes'][0]['product_id'], self.box.id)
        self.assertEqual(info['boxes'][0]['customer'], 4)

    def test_sell_is_idempotent(self):
        vals = {'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id,
                'lines': [{'product_id': self.lettuce.id, 'qty': 2.0}]}
        first = self.Touch.sell(vals)
        second = self.Touch.sell(vals)
        self.assertEqual(first['order']['id'], second['order']['id'])
        self.assertEqual(self.env['sale.order'].search_count([('mercas_touch_uuid', '=', vals['uuid'])]), 1)

    def test_sell_checks_the_lines(self):
        self._buy(10.0, lot_name='CHECK-1')
        lot = self.env['stock.lot'].search([('name', '=', 'CHECK-1')])
        partner = self.customer.id
        bad_lines = [
            [],
            [{'product_id': self.pear.id, 'qty': 0}],
            [{'product_id': self.pear.id, 'qty': 1, 'price_unit': -1}],
            [{'product_id': self.lettuce.id, 'qty': 1, 'lot_id': lot.id}],
            [{'product_id': self.pear.id, 'qty': 1, 'box_qty': 1.5}],
            [{'product_id': self.pear.id, 'qty': 1, 'box_product_id': self.lettuce.id}],
            [{'product_id': self.pear.id, 'qty': 1, 'note': 'x' * 501}],
        ]
        for lines in bad_lines:
            with self.subTest(lines=lines), self.assertRaises(ValidationError):
                self.Touch.sell({'uuid': str(uuid.uuid4()), 'partner_id': partner, 'lines': lines})
        with self.assertRaises(ValidationError):
            self.Touch.sell({'uuid': 'not-a-uuid', 'partner_id': partner,
                             'lines': [{'product_id': self.lettuce.id, 'qty': 1}]})
        # A tracked product without lot can't be delivered
        with self.assertRaises(UserError):
            self.Touch.sell({'uuid': str(uuid.uuid4()), 'partner_id': partner,
                             'lines': [{'product_id': self.pear.id, 'qty': 1}]})

    def test_find_by_barcode(self):
        self._buy(15.0, lot_name='SCAN-1')
        lot = self.env['stock.lot'].search([('name', '=', 'SCAN-1')])
        found = self.Touch.find_by_barcode('SCAN-1')
        self.assertEqual(found['lots'][0]['id'], lot.id)
        self.assertEqual(found['lots'][0]['available'], 15.0)
        self.lettuce.barcode = '8400000000017'
        found = self.Touch.find_by_barcode('8400000000017')
        self.assertEqual(found, {'lots': [], 'product_id': self.lettuce.id})

    def test_boxes_return_and_deliver(self):
        # The customer takes 5 boxes with a sale and gives back 3
        self._buy(100.0, lot_name='BOX-1')
        lot = self.env['stock.lot'].search([('name', '=', 'BOX-1')])
        self.Touch.sell({'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'lines': [
            {'product_id': self.pear.id, 'lot_id': lot.id, 'qty': 50.0, 'box_qty': 5, 'box_product_id': self.box.id},
        ]})
        result = self.Touch.move_boxes({
            'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'direction': 'return',
            'lines': [{'product_id': self.box.id, 'qty': 3}],
        })
        order = self.env['purchase.order'].browse(result['order']['id'])
        self.assertTrue(order.mercas_is_box_return)
        self.assertEqual(order.invoice_ids.state, 'posted', "The deposit is refunded")
        self.assertEqual(result['boxes'][0]['customer'], 2)
        # Boxes of a supplier given back to them
        self._buy(10.0, box_qty=4, box_product_id=self.box.id)
        result = self.Touch.move_boxes({
            'uuid': str(uuid.uuid4()), 'partner_id': self.supplier.id, 'direction': 'deliver',
            'lines': [{'product_id': self.box.id, 'qty': 4}],
        })
        order = self.env['sale.order'].browse(result['order']['id'])
        self.assertTrue(order.mercas_is_box_delivery)
        self.assertEqual(order.state, 'sale')
        with self.assertRaises(ValidationError):
            self.Touch.move_boxes({'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'direction': 'return',
                                   'lines': [{'product_id': self.pear.id, 'qty': 1}]})

    def test_scrap_lot(self):
        self._buy(40.0, lot_name='SCRAP-1')
        lot = self.env['stock.lot'].search([('name', '=', 'SCRAP-1')])
        summary = self.Touch.scrap_lot(lot.id, 5.0)
        self.assertEqual(summary['scrapped'], 5.0)
        self.assertEqual(summary['stock'], 35.0)
        with self.assertRaises(UserError):
            self.Touch.scrap_lot(lot.id, 100.0)
        with self.assertRaises(ValidationError):
            self.Touch.scrap_lot(lot.id, 0)

    def test_lots_and_invoicing(self):
        self._buy(10.0, 1.0, lot_name='FIRM-1', firm=True)
        self._buy(10.0, 1.0, lot_name='SETTLE-1')
        firm = self.env['stock.lot'].search([('name', '=', 'FIRM-1')])
        settle = self.env['stock.lot'].search([('name', '=', 'SETTLE-1')])
        lots = {lot['name']: lot for lot in self.Touch.get_lots('-1')}
        self.assertTrue(lots['FIRM-1']['invoiceable'])
        self.assertTrue(lots['FIRM-1']['firm'])
        self.assertEqual(lots['SETTLE-1']['stock'], 10.0)
        # Only lots under firm negotiation take a firm invoice
        with self.assertRaises(UserError):
            self.Touch.invoice_lots([firm.id, settle.id], 'firm')
        with self.assertRaises(UserError):
            self.Touch.invoice_lots([firm.id], 'advance')
        action = self.Touch.invoice_lots([firm.id], 'firm')
        invoice = self.env['account.move'].browse(action['res_id'])
        self.assertEqual(invoice.move_type, 'in_invoice')
        self.assertEqual(invoice.partner_id, self.supplier)
        with self.assertRaises(ValidationError):
            self.Touch.invoice_lots([firm.id], 'all')

    def test_register_payment(self):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.customer.id,
            'invoice_line_ids': [Command.create({'product_id': self.lettuce.id, 'quantity': 10, 'price_unit': 10.0})],
        })
        invoice.action_post()
        info = self.Touch.get_partner_info(self.customer.id)
        self.assertEqual(info['invoices'][0]['id'], invoice.id)
        self.assertEqual(info['debt']['not_due'] + info['debt']['overdue'], 100.0)
        journal = self.env['account.journal'].search([('type', '=', 'cash'), ('company_id', '=', self.company.id)], limit=1)
        journal = journal or self.env['account.journal'].create({'name': 'Counter Cash', 'type': 'cash', 'code': 'TCSH'})
        vals = {'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'amount': 60.0,
                'journal_id': journal.id, 'invoice_ids': [invoice.id], 'memo': 'Counter'}
        payment = self.Touch.register_payment(vals)
        self.assertEqual(invoice.payment_state, 'partial')
        self.assertEqual(invoice.amount_residual, 40.0)
        self.assertEqual(self.Touch.register_payment(vals)['id'], payment['id'], "Sent twice, made once")
        # Without invoices: an advance of the customer
        advance = self.Touch.register_payment({'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id,
                                               'amount': 15.0, 'journal_id': journal.id})
        self.assertNotEqual(self.env['account.payment'].browse(advance['id']).state, 'draft', "It is posted")
        with self.assertRaises(ValidationError):
            self.Touch.register_payment({'uuid': str(uuid.uuid4()), 'partner_id': self.supplier.id,
                                         'amount': 10.0, 'journal_id': journal.id, 'invoice_ids': [invoice.id]})

    def test_print_actions(self):
        self._buy(20.0, lot_name='PRINT-1')
        lot = self.env['stock.lot'].search([('name', '=', 'PRINT-1')])
        order = self.Touch.sell({'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'lines': [
            {'product_id': self.pear.id, 'lot_id': lot.id, 'qty': 5.0, 'box_qty': 1, 'box_product_id': self.box.id},
        ]})['order']
        action = self.Touch.get_print_action('sale.order', order['id'], 'delivery')
        self.assertEqual(action['type'], 'ir.actions.report')
        action = self.Touch.get_print_action('sale.order', order['id'], 'labels')
        self.assertEqual(action['res_model'], 'mercas.label.print.wizard')
        with self.assertRaises(ValidationError):
            self.Touch.get_print_action('res.partner', self.customer.id, 'labels')

    def test_sell_over_risk(self):
        """ With sale_financial_risk, a customer over their risk keeps the sale as a quotation
        and the screen opens the standard dialog, where a risk manager can go on. """
        if 'risk_sale_order_limit' not in self.env['res.partner']._fields:
            self.skipTest("sale_financial_risk isn't installed")
        self.company.allow_overrisk_sale_confirmation = False
        self.customer.risk_sale_order_limit = 1.0
        result = self.Touch.sell({'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id,
                                  'lines': [{'product_id': self.lettuce.id, 'qty': 5.0, 'price_unit': 1.0}]})
        self.assertEqual(result['action']['res_model'], 'partner.risk.exceeded.wiz')
        order = self.env['sale.order'].browse(result['order']['id'])
        self.assertEqual(order.state, 'draft')
        self.env['partner.risk.exceeded.wiz'].browse(result['action']['res_id']).button_continue()
        self.assertEqual(order.state, 'sale')
        self.assertTrue(all(picking.state == 'done' for picking in order.picking_ids))

    def test_actions_are_ready_for_the_client(self):
        """ The actions opened by the screen come with their views, as from a button. """
        self._buy(10.0, lot_name='ACTION-1', box_qty=1, box_product_id=self.box.id)
        order = self.env['purchase.order'].search([('mercas_touch_uuid', '!=', False)], order='id desc', limit=1)
        action = self.Touch.get_print_action('purchase.order', order.id, 'labels')
        self.assertEqual(action['views'], [(False, 'form')])
        self.assertEqual(action['target'], 'new')
