import uuid
from datetime import timedelta

from markupsafe import Markup

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
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
        # The purchases are invoiced to the suppliers only by the billing administrators
        cls.billing_admin = new_test_user(
            cls.env, login='touch_billing_admin', name='Touch Billing Admin',
            groups='sales_team.group_sale_salesman_all_leads,purchase.group_purchase_user,'
                   'stock.group_stock_user,stock.group_production_lot,account.group_account_manager',
        )

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

    def test_screen_data_only_market_goods(self):
        """ The catalog of sales and purchases has only the products of the categories of
        market goods; the boxes are still there, whatever their category, to choose them. """
        other = self.env['product.category'].create({'name': 'Touch Supplies', 'is_merca': False})
        empty = self.env['product.category'].create({'name': 'Touch Fruit'})
        self.assertTrue(empty.is_merca, "By default")
        supply = self.env['product.product'].create({
            'name': 'Touch Gloves', 'type': 'consu', 'categ_id': other.id, 'sale_ok': True, 'purchase_ok': True,
        })
        self.box.categ_id = other
        data = self.Touch.get_screen_data()
        product_ids = {product['id'] for product in data['products']}
        self.assertNotIn(supply.id, product_ids)
        self.assertIn(self.pear.id, product_ids)
        self.assertIn(self.box.id, product_ids, "The boxes are chosen apart")
        self.assertIn(self.lettuce.id, product_ids, "Without category, it is shown")
        category_ids = {category['id'] for category in data['categories']}
        self.assertNotIn(empty.id, category_ids, "A category of market goods without products isn't shown")
        self.assertNotIn(other.id, category_ids, "Nor one of other goods, even with boxes")
        self.assertFalse(self.lettuce.categ_id)

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

    def test_purchase_price(self):
        """ The price proposed to buy is the one of the purchase order: the vendor price list of
        the supplier for the quantity (net of its discount), or else the cost of the product,
        never the sale price. """
        self.lettuce.standard_price = 0.3
        self.assertEqual(self.Touch.get_line_price('purchase', self.supplier.id, self.lettuce.id), 0.3)
        self.env['product.supplierinfo'].create([{
            'partner_id': self.supplier.id,
            'product_tmpl_id': self.lettuce.product_tmpl_id.id,
            'price': 0.5,
            'min_qty': 0,
        }, {
            'partner_id': self.supplier.id,
            'product_tmpl_id': self.lettuce.product_tmpl_id.id,
            'price': 0.4,
            'discount': 10,
            'min_qty': 100,
        }])
        self.assertEqual(self.Touch.get_line_price('purchase', self.supplier.id, self.lettuce.id, 10), 0.5)
        self.assertAlmostEqual(self.Touch.get_line_price('purchase', self.supplier.id, self.lettuce.id, 100), 0.36)
        # Another supplier, without price list: the cost
        self.assertEqual(self.Touch.get_line_price('purchase', self.customer.id, self.lettuce.id, 10), 0.3)

    def test_sale_price(self):
        """ The price proposed to sell is the one of the sale order: the price list of the
        customer (net of its discount), or else the sale price of the product. """
        self.assertEqual(self.Touch.get_line_price('sale', self.customer.id, self.lettuce.id, 5), 0.8)
        self.env['res.config.settings'].create({'group_product_pricelist': True}).execute()
        pricelist = self.env['product.pricelist'].create({
            'name': 'Touch Wholesale',
            'item_ids': [Command.create({
                'applied_on': '0_product_variant',
                'product_id': self.lettuce.id,
                'compute_price': 'fixed',
                'fixed_price': 0.6,
                'min_quantity': 10,
            })],
        })
        self.customer.property_product_pricelist = pricelist
        self.assertEqual(self.Touch.get_line_price('sale', self.customer.id, self.lettuce.id, 5), 0.8)
        self.assertEqual(self.Touch.get_line_price('sale', self.customer.id, self.lettuce.id, 10), 0.6)

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

    def test_product_weights(self):
        """ The screen works out the net weight from the gross one less the boxes: it gets
        the weight of the boxes and whether the goods are sold by weight. """
        self.box.weight = 0.6
        pear = self.Touch._get_product_data(self.pear)
        self.assertTrue(pear['weighed'])
        self.assertEqual(pear['uom_per_weight'], 1.0)
        self.assertFalse(self.Touch._get_product_data(self.lettuce)['weighed'])
        self.assertEqual(self.Touch._get_product_data(self.box)['weight'], 0.6)
        # The line sold keeps the tare of its boxes
        vals = {'uuid': str(uuid.uuid4()), 'partner_id': self.supplier.id,
                'lines': [{'product_id': self.pear.id, 'qty': 10.0, 'box_qty': 5, 'box_product_id': self.box.id}]}
        order = self.env['purchase.order'].browse(self.Touch.purchase(vals)['order']['id'])
        line = order.order_line.filtered(lambda l: l.product_id == self.pear)
        self.assertAlmostEqual(line.mercas_tare, 3.0)
        self.assertAlmostEqual(line.mercas_gross_weight, 13.0)

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

    def test_damaged_label(self):
        """ A damaged label: the lot is found by the code scanned or typed, the exact one
        first, also once invoiced, and its labels are reprinted as many as boxes were bought. """
        self._buy(30.0, lot_name='LABEL-7', box_qty=3, box_product_id=self.box.id)
        self._buy(10.0, lot_name='LABEL-77')
        lot = self.env['stock.lot'].search([('name', '=', 'LABEL-7')])
        found = self.Touch.search_label_lots('label-7')
        self.assertEqual([found[0]['id'], found[0]['exact']], [lot.id, True], "The exact lot first, typed in lowercase")
        self.assertEqual([(entry['name'], entry['exact']) for entry in found[1:]], [('LABEL-77', False)])
        self.assertEqual(found[0]['supplier'], self.supplier.name)
        lot.invoiced = True
        self.assertIn(lot.id, [entry['id'] for entry in self.Touch.search_label_lots('LABEL')],
                      "Also the labels of a lot already invoiced")
        self.assertIn(lot.id, [entry['id'] for entry in self.Touch.search_label_lots('')], "The last received")
        self.assertFalse(any(entry['exact'] for entry in self.Touch.search_label_lots('LABEL_7')),
                         "The code isn't a pattern for the exact lot")
        action = self.Touch.get_lot_label_action([lot.id])
        self.assertEqual(action['res_model'], 'mercas.label.print.wizard')
        wizard = self.env['mercas.label.print.wizard'].with_user(self.user).with_context(action['context']).create({})
        self.assertEqual([(line.lot_id, line.quantity) for line in wizard.line_ids], [(lot, 3)])
        with self.assertRaises(ValidationError):
            self.Touch.get_lot_label_action([])
        with self.assertRaises(ValidationError):
            self.Touch.get_lot_label_action([lot.id, 999999999])

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

    def _cash_journal(self):
        journal = self.env['account.journal'].search([('type', '=', 'cash'), ('company_id', '=', self.company.id)], limit=1)
        return journal or self.env['account.journal'].create({'name': 'Counter Cash', 'type': 'cash', 'code': 'TCSH'})

    def _give_back_boxes(self, qty, **settle):
        """ The customer takes boxes with a sale and gives `qty` of them back. """
        self._buy(100.0, lot_name='SETTLE-%s' % uuid.uuid4().hex[:6])
        lot = self.env['stock.lot'].search([('name', 'like', 'SETTLE-')], order='id desc', limit=1)
        self.Touch.sell({'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'lines': [
            {'product_id': self.pear.id, 'lot_id': lot.id, 'qty': 50.0, 'box_qty': 5, 'box_product_id': self.box.id},
        ]})
        return self.Touch.move_boxes({
            'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'direction': 'return',
            'lines': [{'product_id': self.box.id, 'qty': qty}], **settle,
        })

    def test_boxes_given_back_paid_now(self):
        journal = self._cash_journal()
        result = self._give_back_boxes(3, settle='pay', journal_id=journal.id)
        bill = self.env['account.move'].browse(result['order']['invoice_ids'])
        self.assertIn(bill.payment_state, ('paid', 'in_payment'))
        self.assertEqual(result['order']['amount'], 3.0)
        self.assertEqual(result['order']['settled'], 'pay')
        self.assertFalse(self.Touch.get_partner_info(self.customer.id)['credits'], "Nothing left in their favour")
        with self.assertRaises(ValidationError):
            self._give_back_boxes(1, settle='pay')
        with self.assertRaises(ValidationError):
            self._give_back_boxes(1, settle='other')

    def test_boxes_given_back_as_credit(self):
        """ The boxes given back stay as a credit, applied when the customer pays their next
        invoice at the counter: only the rest is collected. """
        self.assertFalse(self.Touch.get_screen_data()['can_compensate'])
        with self.assertRaises(UserError):
            self._give_back_boxes(3, settle='compensate')
        self.company.compensation_journal_id = self.env['account.journal'].create(
            {'name': 'Touch Offsetting', 'type': 'general', 'code': 'TOFF'})
        self.assertTrue(self.Touch.get_screen_data()['can_compensate'])
        result = self._give_back_boxes(3, settle='compensate')
        self.assertEqual(result['order']['settled'], 'compensate')
        bill = self.env['account.move'].browse(result['order']['invoice_ids'])
        self.assertIn(bill.payment_state, ('paid', 'in_payment'))
        info = self.Touch.get_partner_info(self.customer.id)
        self.assertEqual([credit['residual'] for credit in info['credits']], [-3.0])
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.customer.id,
            'invoice_line_ids': [Command.create({'product_id': self.lettuce.id, 'quantity': 10, 'price_unit': 1.0})],
        })
        invoice.action_post()
        journal = self._cash_journal()
        credit_ids = [credit['id'] for credit in info['credits']]
        with self.assertRaises(ValidationError):
            self.Touch.register_payment({'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'amount': 0,
                                         'journal_id': journal.id, 'credit_line_ids': credit_ids})
        payment = self.Touch.register_payment({
            'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'amount': 7.0, 'journal_id': journal.id,
            'invoice_ids': [invoice.id], 'credit_line_ids': credit_ids,
        })
        self.assertEqual(payment['credit'], 3.0)
        self.assertEqual(payment['amount'], 7.0)
        self.assertIn(invoice.payment_state, ('paid', 'in_payment'))
        self.assertFalse(self.Touch.get_partner_info(self.customer.id)['credits'])
        # A credit larger than the invoice: the invoice is paid with it alone, the rest stays
        self._give_back_boxes(5, settle='compensate')
        small = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.customer.id,
            'invoice_line_ids': [Command.create({'product_id': self.lettuce.id, 'quantity': 2, 'price_unit': 1.0})],
        })
        small.action_post()
        credit_ids = [credit['id'] for credit in self.Touch.get_partner_info(self.customer.id)['credits']]
        payment = self.Touch.register_payment({
            'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'amount': 0,
            'invoice_ids': [small.id], 'credit_line_ids': credit_ids,
        })
        self.assertFalse(payment['id'], "Nothing collected")
        self.assertEqual(payment['credit'], 2.0)
        self.assertEqual(small.payment_state, 'paid')
        self.assertEqual([c['residual'] for c in self.Touch.get_partner_info(self.customer.id)['credits']], [-3.0])

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

    def test_lot_inventory_notifies_screens(self):
        self._buy(40.0, lot_name='COUNT-1')
        lot = self.env['stock.lot'].search([('name', '=', 'COUNT-1')])
        notified = []
        self.patch(type(self.env['mercas.touch']), '_notify_lots_changed',
                   lambda self, products: notified.append(products))
        lot.with_user(self.user)._mercas_apply_inventory(30.0)
        self.assertEqual(lot.product_qty, 30.0)
        self.assertEqual(notified, [lot.product_id])
        lot.with_user(self.user)._mercas_apply_inventory(30.0)
        self.assertEqual(len(notified), 1, "Nothing to tell when the count didn't change")

    def test_lots_and_invoicing(self):
        self.Touch = self.Touch.with_user(self.billing_admin)
        firm_order = self._buy(10.0, 1.0, lot_name='FIRM-1', firm=True)['order']
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
        # Invoiced from the lot, the standard bill of its purchase leaves it out
        self.assertEqual(self.Touch.get_order_summary('purchase', firm_order['id'])['bill_pending'], False)
        with self.assertRaises(UserError):
            self.Touch.invoice_purchase(firm_order['id'])
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

    def test_pallets(self):
        """ The boxes of a sale go on pallets from the screen: in draft, and corrected after
        the sale by the counter itself; the delivery follows them. """
        self._buy(100.0, lot_name='PALLET-1')
        lot = self.env['stock.lot'].search([('name', '=', 'PALLET-1')])
        PackageType = self.env['stock.package.type']
        europallet = self.env['product.product'].create({'name': 'Touch Europallet', 'type': 'consu', 'is_box': True})
        euro = PackageType.create({'name': 'Touch Euro', 'mercas_is_pallet': True, 'base_weight': 25.0,
                                   'mercas_box_product_id': europallet.id})
        single = PackageType.create({'name': 'Touch Single', 'mercas_is_pallet': True, 'base_weight': 15.0})
        draft = self.Touch.save_draft('sale', {'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'lines': [
            {'product_id': self.pear.id, 'lot_id': lot.id, 'qty': 40.0, 'price_unit': 2.0,
             'box_qty': 8, 'box_product_id': self.box.id},
            {'product_id': self.lettuce.id, 'qty': 3.0, 'price_unit': 1.0},
        ]})
        pear_line_id = draft['line_ids'][0]
        data = self.Touch.get_pallets(draft['id'])
        self.assertEqual([line['id'] for line in data['lines']], [pear_line_id], "Only the lines with boxes")
        self.assertEqual({t['id'] for t in data['types']} & {euro.id, single.id}, {euro.id, single.id})
        self.assertFalse(data['order']['delivered'])
        result = self.Touch.save_pallets(draft['id'], [
            {'package_type_id': euro.id, 'lines': [{'sale_line_id': pear_line_id, 'box_qty': 5}]},
            {'package_type_id': single.id, 'height': 1200.0, 'lines': [{'sale_line_id': pear_line_id, 'box_qty': 3}]},
        ])
        self.assertEqual(result['pallet_count'], 2)
        self.assertFalse(result['mismatch'])
        with self.assertRaises(ValidationError):
            self.Touch.save_pallets(draft['id'], [{'package_type_id': self.box.id, 'lines': []}])
        with self.assertRaises(ValidationError):
            self.Touch.save_pallets(draft['id'], [
                {'package_type_id': euro.id, 'lines': [{'sale_line_id': pear_line_id, 'box_qty': 9}]},
            ])

        sold = self.Touch.sell({'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'order_id': draft['id'],
                                'lines': [
                                    {'line_id': pear_line_id, 'product_id': self.pear.id, 'lot_id': lot.id, 'qty': 40.0,
                                     'price_unit': 2.0, 'box_qty': 8, 'box_product_id': self.box.id},
                                    {'line_id': draft['line_ids'][1], 'product_id': self.lettuce.id, 'qty': 3.0,
                                     'price_unit': 1.0},
                                ]})['order']
        self.assertEqual(sold['pallet_count'], 2)
        self.assertEqual(sold['box_count'], 8)
        order = self.env['sale.order'].browse(sold['id'])
        packages = order.mercas_pallet_ids.package_id
        pear_lines = order.picking_ids.move_line_ids.filtered(lambda ml: ml.product_id == self.pear)
        self.assertEqual(sorted(pear_lines.mapped(lambda ml: (ml.result_package_id.id, ml.quantity))),
                         sorted([(packages[0].id, 25.0), (packages[1].id, 15.0)]))
        self.assertEqual(pear_lines.lot_id, lot)
        self.assertEqual(order.order_line.filtered('mercas_pallet_box_line').product_id, europallet)

        # Corrected after the sale: everything on the first pallet, now single-use
        data = self.Touch.get_pallets(order.id)
        self.assertTrue(data['order']['delivered'])
        result = self.Touch.save_pallets(order.id, [{
            'id': data['pallets'][0]['id'], 'package_type_id': single.id,
            'lines': [{'sale_line_id': pear_line_id, 'box_qty': 8}],
        }])
        self.assertEqual(result['pallet_count'], 1)
        self.assertEqual(result['mismatch'], [{'product': europallet.display_name, 'pallets': 0, 'sale': 1}])
        pear_lines = order.picking_ids.move_line_ids.filtered(lambda ml: ml.product_id == self.pear and ml.quantity)
        self.assertEqual(pear_lines.result_package_id, packages[0])
        self.assertEqual(sum(pear_lines.mapped('quantity')), 40.0)

        action = self.Touch.get_print_action('sale.order', order.id, 'packing')
        self.assertEqual(action['report_name'], 'mercas_base.report_mercas_packing_list')

    def test_print_sale_documents(self):
        """ The documents of a sale for the A4 printer go in a single PDF: the ones checked,
        in their order (delivery slip, DeCA, packing list, invoice). """
        self._buy(30.0, lot_name='PRINTALL-1')
        lot = self.env['stock.lot'].search([('name', '=', 'PRINTALL-1')])
        pallet_type = self.env['stock.package.type'].create({'name': 'Print Pallet', 'mercas_is_pallet': True})
        sold = self.Touch.sell({'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'lines': [
            {'product_id': self.pear.id, 'lot_id': lot.id, 'qty': 10.0, 'price_unit': 2.0,
             'box_qty': 2, 'box_product_id': self.box.id},
        ]})['order']
        self.assertEqual(sold['print']['documents'], ['delivery'], "No pallets, no invoice and the DeCA to complete")
        self.assertTrue(sold['print']['deca_missing'])
        order = self.env['sale.order'].browse(sold['id'])
        pear_line = order.order_line.filtered(lambda line: line.product_id == self.pear)
        self.Touch.save_pallets(order.id, [
            {'package_type_id': pallet_type.id, 'lines': [{'sale_line_id': pear_line.id, 'box_qty': 2}]},
        ])
        self.Touch.invoice_sale(order.id)
        summary = self.Touch.get_order_summary('sale', order.id)
        self.assertEqual(summary['print']['documents'], ['delivery', 'packing', 'invoice'])

        action = self.Touch.get_sale_documents_print_action(order.id, ['invoice', 'delivery', 'packing'])
        self.assertEqual(action['report_name'], 'mercas_touch.report_sale_documents')
        self.assertEqual(action['data']['kinds'], ['delivery', 'packing', 'invoice'], "In the order they print")
        with self.assertRaises(UserError):
            self.Touch.get_sale_documents_print_action(order.id, ['deca'])
        with self.assertRaises(ValidationError):
            self.Touch.get_sale_documents_print_action(order.id, ['labels'])

        Report = self.env['ir.actions.report'].with_user(self.user)
        html = Report._render_qweb_html(action['report_name'], order.ids, data=action['data'])[0].decode()
        # Each document is marked with its record: the delivery, the sale (packing list), the invoice
        markers = [f'data-oe-model="{record._name}" data-oe-id="{record.id}"'
                   for record in (order.picking_ids, order, order.invoice_ids)]
        positions = [html.find(marker) for marker in markers]
        self.assertTrue(all(position >= 0 for position in positions), positions)
        self.assertEqual(positions, sorted(positions), "In the order they print")
        html = Report._render_qweb_html(action['report_name'], order.ids, data={'kinds': ['packing']})[0].decode()
        self.assertNotIn(markers[0], html)
        self.assertNotIn(markers[2], html)

        # Without PDF rendering in the tests, the report falls back to HTML as the others
        self.assertEqual(Report._render_qweb_pdf(action['report_name'], order.ids, data=action['data'])[1], 'html')

    def test_sale_comment_and_documents_by_email(self):
        """ The comments of a sale are printed on its delivery slip and its invoice, until the
        invoice is sent. The documents go by email: the invoice to the contact of invoicing,
        with the standard sending; the delivery slip to the contact of delivery; a single email
        when both have the same address. """
        self._buy(30.0, lot_name='MAIL-1')
        lot = self.env['stock.lot'].search([('name', '=', 'MAIL-1')])
        self.customer.email = 'billing@example.com'
        shipping = self.env['res.partner'].create({
            'name': 'Touch Warehouse', 'type': 'delivery', 'parent_id': self.customer.id,
            'email': 'warehouse@example.com',
        })

        def sell():
            order = self.Touch.sell({'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'lines': [
                {'product_id': self.pear.id, 'lot_id': lot.id, 'qty': 5.0, 'price_unit': 2.0},
            ]})['order']
            return order, self.env['sale.order'].browse(order['id'])

        order, sale = sell()
        sale.partner_shipping_id = shipping
        self.assertEqual(self.Touch.set_sale_comment(order['id'], '  Fragile goods  '),
                         {'comment': 'Fragile goods', 'comment_locked': False})
        picking = sale.picking_ids
        html = self.env['ir.actions.report']._render_qweb_html('stock.action_report_delivery', picking.ids)[0]
        self.assertIn(b'Fragile goods', html)

        mail = self.Touch.get_order_summary('sale', order['id'])['mail']
        self.assertEqual(mail['documents'], ['delivery'])
        self.assertTrue(mail['deca_missing'], "The DeCA isn't complete")
        self.assertEqual(mail['emails'], {'invoice': 'billing@example.com', 'shipping': 'warehouse@example.com'})
        with self.assertRaises(UserError):
            self.Touch.send_sale_documents(order['id'], ['invoice'])

        self.Touch.invoice_sale(order['id'])
        invoice = sale.invoice_ids
        self.assertEqual(invoice.mercas_comment, 'Fragile goods')
        html = self.env['ir.actions.report']._render_qweb_html('account.account_invoices', invoice.ids)[0]
        self.assertIn(b'Fragile goods', html)

        sent = self.Touch.send_sale_documents(order['id'], ['delivery', 'invoice'])
        self.assertEqual(sent, [
            {'email': 'warehouse@example.com', 'documents': ['delivery']},
            {'email': 'billing@example.com', 'documents': ['invoice']},
        ])
        self.assertTrue(invoice.is_move_sent)
        self.assertTrue(invoice.invoice_pdf_report_id)
        message = picking.message_ids.filtered(lambda m: shipping in m.partner_ids)
        self.assertEqual(len(message), 1)
        self.assertEqual(len(message.attachment_ids), 1)
        summary = self.Touch.get_order_summary('sale', order['id'])
        self.assertTrue(summary['comment_locked'], "The invoice was sent: its PDF is kept")
        with self.assertRaises(UserError):
            self.Touch.set_sale_comment(order['id'], 'Too late')

        # The same address for both contacts: a single email, the one of the invoice
        order, sale = sell()
        shipping.email = 'BILLING@example.com'
        sale.partner_shipping_id = shipping
        self.Touch.invoice_sale(order['id'])
        sent = self.Touch.send_sale_documents(order['id'], ['invoice', 'delivery'])
        self.assertEqual(sent, [{'email': 'billing@example.com', 'documents': ['invoice', 'delivery']}])
        message = sale.invoice_ids.message_ids.filtered(lambda m: self.customer in m.partner_ids)
        self.assertEqual(len(message), 1)
        self.assertEqual(len(message.attachment_ids), 2, "The invoice and the delivery slip")

        # A contact without email: nothing is sent
        shipping.email = False
        with self.assertRaises(UserError):
            self.Touch.send_sale_documents(order['id'], ['delivery'])

    def test_sale_comment_reaches_invoices_made_later(self):
        """ The comments typed on the screen are printed on the invoice of the sale, however
        and whenever it is made: from the backend afterwards, a draft made before the comments,
        or a posted invoice not yet sent nor printed whose comments change. """
        self._buy(30.0, lot_name='COMMENT-1')
        lot = self.env['stock.lot'].search([('name', '=', 'COMMENT-1')])

        def sell():
            order = self.Touch.sell({'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'lines': [
                {'product_id': self.pear.id, 'lot_id': lot.id, 'qty': 5.0, 'price_unit': 2.0},
            ]})['order']
            return order['id'], self.env['sale.order'].browse(order['id'])

        def invoice_html(invoice):
            return self.env['ir.actions.report']._render_qweb_html('account.account_invoices', invoice.ids)[0]

        # 1. Comments on the screen, invoice made later from the backend (standard wizard)
        order_id, sale = sell()
        self.Touch.set_sale_comment(order_id, 'Keep refrigerated')
        wizard = self.env['sale.advance.payment.inv'].with_context(
            active_model='sale.order', active_ids=sale.ids).create({'advance_payment_method': 'delivered'})
        wizard.create_invoices()
        invoice = sale.invoice_ids
        self.assertEqual(invoice.state, 'draft')
        self.assertEqual(invoice.mercas_comment, 'Keep refrigerated')
        self.assertIn(b'Keep refrigerated', invoice_html(invoice))
        invoice.action_post()
        self.assertIn(b'Keep refrigerated', invoice_html(invoice))

        # 2. Draft invoice made before the comments
        order_id, sale = sell()
        sale._create_invoices()
        invoice = sale.invoice_ids
        self.assertFalse(invoice.mercas_comment)
        self.Touch.set_sale_comment(order_id, 'Deliver before 8:00')
        self.assertEqual(invoice.mercas_comment, 'Deliver before 8:00')
        self.assertIn(b'Deliver before 8:00', invoice_html(invoice))

        # 3. Posted, not sent nor printed: the comments can still change, and the invoice follows
        invoice.action_post()
        self.assertFalse(self.Touch.get_order_summary('sale', order_id)['comment_locked'])
        self.Touch.set_sale_comment(order_id, 'Deliver before 9:00')
        html = invoice_html(invoice)
        self.assertIn(b'Deliver before 9:00', html)
        self.assertNotIn(b'Deliver before 8:00', html)

    def test_deca(self):
        """ The DeCA of a sale opens a dialog with the carrier proposed, as the company says,
        and what is still missing; it is printed from there. """
        self.company.mercas_default_carrier = 'last'
        self._buy(30.0, lot_name='DECA-1')
        lot = self.env['stock.lot'].search([('name', '=', 'DECA-1')])

        def sell(qty):
            order = self.Touch.sell({'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'lines': [
                {'product_id': self.pear.id, 'lot_id': lot.id, 'qty': qty},
            ]})['order']
            return order, self.env['sale.order'].browse(order['id']).picking_ids

        order, picking = sell(5.0)
        self.assertFalse(picking.carrier_contact_id, "No delivery of the customer had a carrier yet")
        action = self.Touch.get_deca_action(order['id'])
        self.assertEqual((action['res_model'], action['res_id'], action['target']), ('stock.picking', picking.id, 'new'))
        self.assertIn(self.env._("Main vehicle or tractor licence plate"), picking.mercas_deca_missing)
        with self.assertRaises(UserError):
            picking.with_user(self.user).action_mercas_print_deca()

        carrier = self.env['res.partner'].create({'name': 'Touch Carrier', 'vat': 'ESA58818501'})
        self.customer.vat = 'ESB12345674'
        self.company.partner_id.vat = 'ESA12345674'
        picking.with_user(self.user).write({'carrier_contact_id': carrier.id, 'tractor_license_plate': '1234BCD'})
        self.assertFalse(picking.mercas_deca_missing)
        action = picking.with_user(self.user).action_mercas_print_deca()
        self.assertEqual(action['report_name'], 'l10n_es_deca_oca.report_deca')
        self.assertTrue(action['close_on_report_download'])

        _order, picking = sell(5.0)
        self.assertEqual(picking.carrier_contact_id, carrier, "The last carrier of the customer")
        self.assertEqual(picking.tractor_license_plate, '1234BCD')
        self.company.mercas_default_carrier = 'customer'
        _order, picking = sell(5.0)
        self.assertEqual(picking.carrier_contact_id, self.customer)
        self.assertFalse(picking.tractor_license_plate)
        self.company.mercas_default_carrier = 'none'
        order, picking = sell(5.0)
        self.assertFalse(picking.carrier_contact_id)

        # A delivery made before the setting, or before l10n_es_deca_oca was installed (whose
        # weight isn't computed): the dialog proposes the carrier and computes the weight
        self.company.mercas_default_carrier = 'last'
        self.env.flush_all()
        self.env.cr.execute("UPDATE stock_move SET deca_weight = NULL WHERE picking_id = %s", [picking.id])
        self.env.cr.execute("UPDATE stock_picking SET deca_weight = NULL WHERE id = %s", [picking.id])
        self.env.invalidate_all()
        self.assertFalse(picking.deca_weight)
        self.Touch.get_deca_action(order['id'])
        self.assertEqual(picking.carrier_contact_id, self.customer, "The last carrier of the customer")
        self.assertEqual(picking.deca_weight, 5.0)

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

    def test_quotation_saved_while_made(self):
        """ The sale being made is a quotation in draft: created with the first line, then
        updated with each change, and sold at the end. """
        self._buy(100.0, lot_name='QUOTE-1')
        lot = self.env['stock.lot'].search([('name', '=', 'QUOTE-1')])
        vals = {'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'lines': [
            {'product_id': self.pear.id, 'lot_id': lot.id, 'qty': 10.0, 'price_unit': 1.5, 'note': 'Green'},
        ]}
        quotation = self.Touch.save_draft('sale', vals)
        order = self.env['sale.order'].browse(quotation['id'])
        self.assertEqual(order.state, 'draft')
        self.assertEqual(order.mercas_touch_uuid, vals['uuid'])
        [first_id] = quotation['line_ids']
        self.assertEqual(quotation['lines'][0]['note'], 'Green')
        # A section added in the backend is kept
        order.order_line = [Command.create({'display_type': 'line_section', 'name': 'Fruit'})]
        # Change the first line and add another
        quotation = self.Touch.save_draft('sale', dict(vals, order_id=order.id, lines=[
            {'line_id': first_id, 'product_id': self.pear.id, 'lot_id': lot.id, 'qty': 12.0, 'price_unit': 1.6},
            {'product_id': self.lettuce.id, 'qty': 3.0, 'price_unit': 0.7},
        ]))
        self.assertEqual(quotation['line_ids'][0], first_id, "The line is updated, not replaced")
        first = order.order_line.browse(first_id)
        self.assertEqual((first.product_uom_qty, first.price_unit), (12.0, 1.6))
        self.assertEqual(quotation['lines'][0]['note'], 'Green', "The text is kept when not sent")
        self.assertEqual(len(order.order_line.filtered(lambda l: not l.display_type)), 2)
        # Remove the first line
        self.Touch.save_draft('sale', dict(vals, order_id=order.id, lines=[
            {'line_id': quotation['line_ids'][1], 'product_id': self.lettuce.id, 'qty': 3.0, 'price_unit': 0.7},
        ]))
        self.assertFalse(first.exists())
        self.assertTrue(order.order_line.filtered(lambda l: l.display_type == 'line_section'))
        # In the list of quotations, and resumed as it is
        self.assertIn(order.id, [q['id'] for q in self.Touch.get_drafts('sale', '')])
        self.assertEqual(self.Touch.get_draft('sale', order.id)['lines'][0]['product']['id'], self.lettuce.id)
        # Sold: the same quotation is confirmed and delivered
        result = self.Touch.sell(dict(vals, order_id=order.id, lines=[
            {'line_id': quotation['line_ids'][1], 'product_id': self.lettuce.id, 'qty': 3.0, 'price_unit': 0.7},
        ]))
        self.assertEqual(result['order']['id'], order.id)
        self.assertEqual(order.state, 'sale')
        self.assertNotIn(order.id, [q['id'] for q in self.Touch.get_drafts('sale', '')])
        # Sent again after it was sold: nothing changes
        self.assertEqual(self.Touch.sell(dict(vals, order_id=order.id))['order']['id'], order.id)
        with self.assertRaises(UserError):
            self.Touch.save_draft('sale', dict(vals, order_id=order.id))

    def test_sell_bulk_with_quality_and_size(self):
        """ Goods bought in bulk: the quality and the size are chosen on each line of the sale,
        and can be changed afterwards, keeping the text of the line. """
        quality = self.env['product.attribute'].create({
            'name': 'Touch Quality', 'create_variant': 'no_variant', 'mercas_role': 'quality',
            'value_ids': [Command.create({'name': 'Extra'}), Command.create({'name': 'First'})],
        })
        size = self.env['product.attribute'].create({
            'name': 'Touch Size', 'create_variant': 'no_variant', 'mercas_role': 'size',
            'value_ids': [Command.create({'name': '03'}), Command.create({'name': '04'})],
        })
        self.pear.product_tmpl_id.attribute_line_ids = [
            Command.create({'attribute_id': attribute.id, 'value_ids': [Command.set(attribute.value_ids.ids)]})
            for attribute in quality | size
        ]
        products = {product['id']: product for product in self.Touch.get_screen_data()['products']}
        attributes = products[self.pear.id]['attributes']
        self.assertEqual([attribute['name'] for attribute in attributes], ['Touch Quality', 'Touch Size'])
        self.assertFalse(products[self.lettuce.id]['attributes'])
        value = {(attribute['name'], v['name']): v['id'] for attribute in attributes for v in attribute['values']}
        extra, first = value['Touch Quality', 'Extra'], value['Touch Quality', 'First']
        size_03 = value['Touch Size', '03']

        self._buy(100.0, lot_name='BULK-1')
        lot = self.env['stock.lot'].search([('name', '=', 'BULK-1')])
        vals = {'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'lines': [
            {'product_id': self.pear.id, 'lot_id': lot.id, 'qty': 10.0, 'price_unit': 1.5,
             'attribute_value_ids': [extra, size_03], 'note': 'Ripe ones'},
        ]}
        draft = self.Touch.save_draft('sale', vals)
        line = self.env['sale.order.line'].browse(draft['line_ids'][0])
        self.assertEqual((line.mercas_quality, line.mercas_size), ('Extra', '03'))
        self.assertIn('Extra', line.name, "The description shows the values")
        self.assertEqual(draft['lines'][0]['attribute_value_ids'], [extra, size_03])
        self.assertEqual(draft['lines'][0]['note'], 'Ripe ones')

        # Changed afterwards: the description follows, the text of the line is kept
        vals = dict(vals, order_id=draft['id'], lines=[
            {'line_id': line.id, 'product_id': self.pear.id, 'lot_id': lot.id, 'qty': 10.0,
             'price_unit': 1.5, 'attribute_value_ids': [first]},
        ])
        draft = self.Touch.save_draft('sale', vals)
        self.assertEqual(draft['line_ids'], [line.id])
        self.assertEqual((line.mercas_quality, line.mercas_size), ('First', ''))
        self.assertIn('First', line.name)
        self.assertNotIn('Extra', line.name)
        self.assertEqual(draft['lines'][0]['note'], 'Ripe ones')

        # One value for each attribute, of the attributes of the product
        for wrong in ([extra, first], [self.env['product.template.attribute.value'].search([], limit=1).id + 10**6]):
            with self.assertRaises(ValidationError):
                self.Touch.save_draft('sale', dict(vals, lines=[dict(vals['lines'][0], attribute_value_ids=wrong)]))

        result = self.Touch.sell(vals)
        summary = self.Touch.get_order_summary('sale', result['order']['id'])
        self.assertEqual(summary['lines'][0]['attributes'], 'First')

    def test_resume_backend_quotation(self):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [Command.create({'product_id': self.lettuce.id, 'product_uom_qty': 2, 'price_unit': 0.9})],
        })
        quotation = self.Touch.get_draft('sale', order.id)
        self.assertEqual(quotation['partner_id'], self.customer.id)
        self.assertEqual(quotation['lines'][0]['qty'], 2)
        self.assertEqual(quotation['lines'][0]['price'], 0.9)
        # A product that can't be sold anymore stays in the quotation
        self.lettuce.sale_ok = False
        self.Touch.save_draft('sale', {'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'order_id': order.id,
                                   'lines': [{'line_id': quotation['lines'][0]['line_id'],
                                              'product_id': self.lettuce.id, 'qty': 5.0, 'price_unit': 0.9}]})
        self.assertEqual(order.order_line.product_uom_qty, 5)
        # The customer of a quotation can't change
        with self.assertRaises(ValidationError):
            self.Touch.save_draft('sale', {'uuid': str(uuid.uuid4()), 'partner_id': self.supplier.id,
                                       'order_id': order.id, 'lines': []})
        self.Touch.cancel_draft('sale', order.id)
        self.assertEqual(order.state, 'cancel')

    def test_purchase_draft(self):
        """ The purchase being made is a request for quotation in draft. The lot asked for is
        kept by name and only made when the purchase is received. """
        spain = self.env.ref('base.es')
        vals = {'uuid': str(uuid.uuid4()), 'partner_id': self.supplier.id, 'lines': [
            {'product_id': self.pear.id, 'qty': 40.0, 'price_unit': 0.8, 'lot_name': 'RFQ-1', 'firm': True,
             'origin_country_id': spain.id, 'box_qty': 4, 'box_product_id': self.box.id, 'note': 'Ripe'},
        ]}
        draft = self.Touch.save_draft('purchase', vals)
        order = self.env['purchase.order'].browse(draft['id'])
        self.assertEqual(order.state, 'draft')
        line = order.order_line.browse(draft['line_ids'][0])
        self.assertEqual(line.mercas_touch_lot_name, 'RFQ-1')
        self.assertFalse(self.env['stock.lot'].search([('name', '=', 'RFQ-1')]))
        resumed = self.Touch.get_draft('purchase', order.id)['lines'][0]
        self.assertEqual((resumed['lot_name'], resumed['firm'], resumed['origin_country_id'], resumed['note']),
                         ('RFQ-1', True, spain.id, 'Ripe'))
        self.assertIn(order.id, [d['id'] for d in self.Touch.get_drafts('purchase', 'Touch Supplier')])
        result = self.Touch.purchase(dict(vals, order_id=order.id, lines=[
            dict(vals['lines'][0], line_id=line.id, qty=45.0),
        ]))
        self.assertEqual(result['order']['id'], order.id)
        self.assertEqual(order.state, 'purchase')
        lot = line.lot_id
        self.assertEqual((lot.name, lot.partner_id, lot.mercas_firm_negotiation, lot.origin_country_id),
                         ('RFQ-1', self.supplier, True, spain))
        self.assertEqual(self.pear.with_context(lot_id=lot.id).qty_available, 45.0)
        # Sent again after it was received: nothing changes
        self.assertEqual(self.Touch.purchase(dict(vals, order_id=order.id))['order']['id'], order.id)

    def test_cancel_purchase_draft(self):
        draft = self.Touch.save_draft('purchase', {'uuid': str(uuid.uuid4()), 'partner_id': self.supplier.id,
                                                   'lines': [{'product_id': self.lettuce.id, 'qty': 3.0}]})
        self.Touch.cancel_draft('purchase', draft['id'])
        self.assertEqual(self.env['purchase.order'].browse(draft['id']).state, 'cancel')
        with self.assertRaises(ValidationError):
            self.Touch.get_drafts('invoice')

    def test_invoice_sale(self):
        order = self.Touch.sell({'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id,
                                 'lines': [{'product_id': self.lettuce.id, 'qty': 4.0, 'price_unit': 2.5}]})['order']
        invoice = self.Touch.invoice_sale(order['id'])
        move = self.env['account.move'].browse(invoice['id'])
        self.assertEqual(move.state, 'posted')
        self.assertEqual(invoice['residual'], 10.0)
        self.assertEqual(self.Touch.invoice_sale(order['id'])['id'], move.id, "Invoiced once")
        action = self.Touch.get_print_action('sale.order', order['id'], 'invoice')
        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertIn(move.id, [inv['id'] for inv in self.Touch.get_partner_info(self.customer.id)['invoices']])
        quotation = self.Touch.save_draft('sale', {'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id,
                                                   'lines': [{'product_id': self.lettuce.id, 'qty': 1.0}]})
        with self.assertRaises(UserError):
            self.Touch.invoice_sale(quotation['id'])

    def test_invoice_sale_over_risk(self):
        """ With account_financial_risk, an invoice over the customer's risk stays in draft and
        the screen opens the standard dialog, where a risk manager posts it. """
        if 'risk_invoice_open_limit' not in self.env['res.partner']._fields:
            self.skipTest("account_financial_risk isn't installed")
        self.company.allow_overrisk_invoice_validation = False
        self.customer.risk_invoice_open_limit = 1.0
        order = self.Touch.sell({'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id,
                                 'lines': [{'product_id': self.lettuce.id, 'qty': 4.0, 'price_unit': 2.5}]})['order']
        sale = self.env['sale.order'].browse(order['id'])
        result = self.Touch.invoice_sale(order['id'])
        self.assertEqual(result['action']['res_model'], 'partner.risk.exceeded.wiz')
        self.assertTrue(result['order']['invoice_draft'])
        self.assertEqual(sale.invoice_ids.state, 'draft')
        to_invoice = self.Touch.get_drafts('sale', state_filter='to_invoice')
        self.assertIn(order['id'], [draft['id'] for draft in to_invoice], "Still to invoice")
        # Sent again: the same draft invoice asks again, no second invoice
        result = self.Touch.invoice_sale(order['id'])
        self.assertEqual(result['action']['res_model'], 'partner.risk.exceeded.wiz')
        self.assertEqual(len(sale.invoice_ids), 1)
        self.env['partner.risk.exceeded.wiz'].browse(result['action']['res_id']).button_continue()
        self.assertEqual(sale.invoice_ids.state, 'posted')
        invoice = self.Touch.invoice_sale(order['id'])
        self.assertEqual(invoice['id'], sale.invoice_ids.id)
        self.assertFalse(invoice['order']['invoice_draft'])

    def test_boxes_deliver_over_risk(self):
        """ The boxes given back to a supplier are delivered, and their invoice over the risk
        stays in draft with the standard dialog. """
        if 'risk_invoice_open_limit' not in self.env['res.partner']._fields:
            self.skipTest("account_financial_risk isn't installed")
        self.company.allow_overrisk_invoice_validation = False
        self.supplier.risk_invoice_open_limit = 1.0
        self._buy(10.0, box_qty=4, box_product_id=self.box.id)
        result = self.Touch.move_boxes({
            'uuid': str(uuid.uuid4()), 'partner_id': self.supplier.id, 'direction': 'deliver',
            'lines': [{'product_id': self.box.id, 'qty': 4}],
        })
        self.assertEqual(result['action']['res_model'], 'partner.risk.exceeded.wiz')
        order = self.env['sale.order'].browse(result['order']['id'])
        self.assertEqual(order.state, 'sale')
        self.assertTrue(all(picking.state == 'done' for picking in order.picking_ids))
        self.assertEqual(order.invoice_ids.state, 'draft')

    def test_origin_countries_and_states(self):
        """ Without the origin filter of the company, every country, and the states of the
        country chosen; with it, only the countries marked as origin, with all their states. """
        Country, State = self.env['res.country'], self.env['res.country.state']
        spain, france = self.env.ref('base.es'), self.env.ref('base.fr')
        self.company.origin_filter = False
        origin = self.Touch.get_screen_data()['origin']
        self.assertEqual(len(origin['countries']), Country.search_count([]))
        states = self.Touch.get_origin_states(spain.id)
        self.assertEqual(len(states), State.search_count([('country_id', '=', spain.id)]))
        self.assertTrue(all(state['country_id'] == spain.id for state in states))

        Country.search([]).mercas_origin = False
        (spain | france).mercas_origin = True
        self.company.origin_filter = True
        origin = self.Touch.get_screen_data()['origin']
        self.assertEqual({c['id'] for c in origin['countries']}, {spain.id, france.id})
        self.assertEqual(self.Touch.get_origin_states(spain.id), states)
        self.assertEqual(self.Touch.get_origin_states(self.env.ref('base.it').id), [])

    def test_draft_filters_and_summary(self):
        """ Besides the drafts in progress, the confirmed orders still to invoice and all of
        them can be listed, looked up and invoiced. """
        draft = self.Touch.save_draft('sale', {'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id,
                                               'lines': [{'product_id': self.lettuce.id, 'qty': 1.0}]})
        sold = self.Touch.sell({'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id,
                                'lines': [{'product_id': self.lettuce.id, 'qty': 2.0, 'price_unit': 3.0}]})['order']
        self.assertEqual(sold['invoice_status'], 'to invoice')

        def ids(state_filter):
            return {order['id'] for order in self.Touch.get_drafts('sale', 'Touch Customer', state_filter)}
        self.assertIn(draft['id'], ids('draft'))
        self.assertNotIn(sold['id'], ids('draft'))
        self.assertEqual(ids('to_invoice') & {draft['id'], sold['id']}, {sold['id']})
        self.assertEqual(ids('all') & {draft['id'], sold['id']}, {draft['id'], sold['id']})
        with self.assertRaises(ValidationError):
            self.Touch.get_drafts('sale', '', 'paid')

        summary = self.Touch.get_order_summary('sale', sold['id'])
        self.assertEqual(summary['lines'][0]['product'], self.lettuce.display_name)
        self.assertEqual(summary['lines'][0]['subtotal'], 6.0)
        self.assertIs(summary['invoice'], False)
        invoice = self.Touch.invoice_sale(sold['id'])
        self.assertEqual(invoice['order']['invoice_status'], 'invoiced')
        self.assertNotIn(sold['id'], ids('to_invoice'))
        self.assertIn(sold['id'], ids('all'))
        self.assertEqual(self.Touch.get_order_summary('sale', sold['id'])['invoice']['id'], invoice['id'])

    def test_bill_only_billing_admins(self):
        """ The counter buys, but doesn't invoice the purchases: no buttons, nor the calls. """
        order = self.Touch.purchase({'uuid': str(uuid.uuid4()), 'partner_id': self.supplier.id, 'lines': [
            {'product_id': self.lettuce.id, 'qty': 5.0, 'price_unit': 0.5},
        ]})['order']
        self.assertFalse(self.Touch.get_screen_data()['can_bill'])
        self.assertFalse(order['bill_pending'])
        self.assertEqual(order['lot_invoice_modes'], [])
        with self.assertRaises(AccessError):
            self.Touch.invoice_purchase(order['id'])
        with self.assertRaises(AccessError):
            self.Touch.invoice_purchase_lots(order['id'], 'settle')
        with self.assertRaises(AccessError):
            self.Touch.invoice_lots([1], 'settle')
        admin = self.Touch.with_user(self.billing_admin)
        self.assertTrue(admin.get_screen_data()['can_bill'])
        self.assertTrue(admin.get_order_summary('purchase', order['id'])['bill_pending'])

    def test_invoice_purchase(self):
        """ The lots under firm negotiation are billed with the standard bill of the purchase,
        sections and boxes included, and count as invoiced in the lot. All the bills can be
        looked up from the purchase, and the drafts deleted. """
        self.Touch = self.Touch.with_user(self.billing_admin)
        order = self.Touch.purchase({'uuid': str(uuid.uuid4()), 'partner_id': self.supplier.id, 'lines': [
            {'product_id': self.pear.id, 'qty': 10.0, 'price_unit': 1.2, 'lot_name': 'BILL-1', 'firm': True,
             'box_qty': 2, 'box_product_id': self.box.id},
            {'product_id': self.lettuce.id, 'qty': 5.0, 'price_unit': 0.5},
        ]})['order']
        self.assertIn(order['id'], [o['id'] for o in self.Touch.get_drafts('purchase', '', 'to_invoice')])
        self.assertTrue(order['bill_pending'])
        self.assertEqual(order['lot_invoice_modes'], [])
        self.assertFalse(order['invoice_count'])

        action = self.Touch.invoice_purchase(order['id'])
        self.assertEqual((action['res_model'], action['target']), ('account.move', 'new'))
        bill = self.env['account.move'].browse(action['res_id'])
        self.assertEqual((bill.move_type, bill.state), ('in_invoice', 'draft'))
        purchase = self.env['purchase.order'].browse(order['id'])
        self.assertEqual(bill.invoice_line_ids.filtered('product_id').product_id, self.pear | self.lettuce | self.box)
        self.assertEqual(bool(bill.invoice_line_ids.filtered(lambda l: l.display_type == 'line_section')),
                         bool(purchase.order_line.filtered(lambda l: l.display_type == 'line_section')),
                         "The sections of the purchase are kept")
        lot = self.env['stock.lot'].search([('name', '=', 'BILL-1')])
        self.assertTrue(bill.invoice_line_ids.filtered(lambda l: l.lot_id == lot).mercas_is_firm_line)

        # A bill in draft made by mistake can be deleted; a posted one can't
        with self.assertRaises(ValidationError):
            self.Touch.delete_purchase_invoice(self._buy(1.0, lot_name='BILL-2')['order']['id'], bill.id)
        with self.assertRaises(UserError):
            self.Touch.get_purchase_invoice_print_action(order['id'], bill.id)
        self.assertEqual(self.Touch.delete_purchase_invoice(order['id'], bill.id), [])
        self.assertFalse(bill.exists())
        bill = self.env['account.move'].browse(self.Touch.invoice_purchase(order['id'])['res_id'])
        bill.invoice_date = bill.date
        bill.action_post()
        with self.assertRaises(UserError):
            self.Touch.delete_purchase_invoice(order['id'], bill.id)
        action = self.Touch.get_purchase_invoice_print_action(order['id'], bill.id)
        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertEqual(action['context']['active_ids'], [bill.id])
        self.assertEqual(lot.net_invoiced_kg, 10.0)
        self.assertTrue(lot.invoiced)
        self.assertFalse(lot.invoiceable)

        summary = self.Touch.get_order_summary('purchase', order['id'])
        self.assertFalse(summary['bill_pending'])
        self.assertEqual(summary['lot_invoice_modes'], [])
        self.assertEqual(summary['invoice']['id'], bill.id)
        figures = next(line['lot_figures'] for line in summary['lines'] if line['lot'] == 'BILL-1')
        self.assertEqual(figures, {'stock': 10.0, 'sold': 0.0, 'firm': True, 'invoiced': 10.0},
                         "A firm lot is invoiced in kg")
        self.assertFalse(next(line['lot_figures'] for line in summary['lines'] if not line['lot']))
        self.assertEqual([invoice['id'] for invoice in self.Touch.get_purchase_invoices(order['id'])], [bill.id])
        with self.assertRaises(UserError):
            self.Touch.invoice_purchase(order['id'])

    def test_settlement_takes_the_boxes(self):
        """ A lot under sale settlement is invoiced from the lot: its first invoice, an advance
        or the settlement, also takes the boxes bought with it still to invoice, which aren't
        invoiced again. """
        self.Touch = self.Touch.with_user(self.billing_admin)
        order = self._buy(20.0, 1.0, lot_name='BOX-SETTLE', box_qty=4, box_product_id=self.box.id)['order']
        lot = self.env['stock.lot'].search([('name', '=', 'BOX-SETTLE')])

        def sell(qty):
            self.Touch.sell({'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id,
                             'lines': [{'product_id': self.pear.id, 'lot_id': lot.id, 'qty': qty, 'price_unit': 2.0}]})

        def invoice(mode):
            action = self.Touch.invoice_purchase_lots(order['id'], mode)
            self.assertEqual(action['target'], 'new')
            move = self.env['account.move'].browse(action['res_id'])
            if move.state == 'draft':
                move.invoice_date = move.date
                move.action_post()
            self.assertTrue(move.invoice_line_ids.filtered(lambda line: line.lot_id == lot))
            return move.invoice_line_ids.filtered(lambda line: line.product_id == self.box)

        sell(5.0)
        summary = self.Touch.get_order_summary('purchase', order['id'])
        self.assertEqual(summary['lot_invoice_modes'], ['advance'])
        self.assertEqual(
            [(line['lot_name'], line['qty']) for line in summary['settlement_lines']], [('BOX-SETTLE', 20.0)],
            "Warned: not in the bill of the purchase, invoiced from its lot")
        self.assertTrue(summary['bill_pending'], "The boxes are still to invoice")
        box_line = invoice('advance')
        self.assertEqual(box_line.quantity, 4)
        self.assertTrue(box_line.purchase_line_id)
        self.assertFalse(self.Touch.get_order_summary('purchase', order['id'])['bill_pending'])

        sell(15.0)
        self.assertTrue(lot.completed)
        self.assertEqual(self.Touch.get_order_summary('purchase', order['id'])['lot_invoice_modes'], ['settle'])
        self.assertFalse(invoice('settle'), "The boxes were already invoiced with the advance")
        summary = self.Touch.get_order_summary('purchase', order['id'])
        self.assertEqual(summary['settlement_lines'], [], "Settled: nothing left to warn about")
        figures = next(line['lot_figures'] for line in summary['lines'] if line['lot'] == 'BOX-SETTLE')
        self.assertEqual((figures['stock'], figures['sold'], figures['firm']), (0.0, 20.0, False))
        self.assertEqual(figures['invoiced'], lot.net_invoiced_amount, "Under sale settlement, in amount")
        self.assertTrue(figures['invoiced'])
        self.assertEqual(summary['invoice_count'], 2)
        with self.assertRaises(UserError):
            self.Touch.invoice_purchase(order['id'])


@tagged('post_install', '-at_install')
class TestMercasTouchHome(MercasTouchCommon):
    """ Dashboard of the main menu of the counter. """

    def _lot(self, name, qty, expiration=None):
        result = self._buy(qty, 1.0, lot_name=name)
        lot = self.env['stock.lot'].search([('name', '=', name), ('product_id', '=', self.pear.id)])
        self.assertTrue(lot, result)
        if expiration is not None:
            lot.expiration_date = expiration
        return lot

    def test_promotion_with_stock(self):
        self.assertNotIn(self.pear.id, [p['id'] for p in self.Touch.get_home_dashboard()['promotion']])
        self.pear.is_favorite = True
        self.assertNotIn(self.pear.id, [p['id'] for p in self.Touch.get_home_dashboard()['promotion']],
                         "On promotion, but without stock")
        self._lot('HOME-PROMO', 50.0)
        promotion = self.Touch.get_home_dashboard()['promotion']
        pear = next(p for p in promotion if p['id'] == self.pear.id)
        self.assertEqual(pear['available'], 50.0)
        products = {p['id']: p for p in self.Touch.get_screen_data()['products']}
        self.assertTrue(products[self.pear.id]['is_favorite'])
        self.assertFalse(products[self.lettuce.id]['is_favorite'])

    def test_expiring_and_undated_lots(self):
        self.pear.alert_time = 3
        now = fields.Datetime.now()
        soon = self._lot('HOME-SOON', 10.0, now + timedelta(days=2))
        expired = self._lot('HOME-EXPIRED', 10.0, now - timedelta(days=1))
        later = self._lot('HOME-LATER', 10.0, now + timedelta(days=10))
        undated = self._lot('HOME-UNDATED', 10.0)
        not_expiring = self._lot('HOME-NEVER', 10.0)
        not_expiring.mercas_no_expiration = True
        home = self.Touch.get_home_dashboard()
        mine = (soon | expired | later).ids
        expiring = [lot for lot in home['expiring'] if lot['id'] in mine]
        self.assertEqual([lot['id'] for lot in expiring], [expired.id, soon.id], "The expired one first")
        self.assertEqual([lot['days_left'] for lot in expiring], [-1, 2])
        undated_ids = [lot['id'] for lot in home['undated']['lots']]
        self.assertIn(undated.id, undated_ids)
        self.assertNotIn(not_expiring.id, undated_ids, "Marked as a lot that doesn't expire")
        self.assertNotIn(soon.id, undated_ids)
        self.pear.alert_time = 15
        self.assertIn(later.id, [lot['id'] for lot in self.Touch.get_home_dashboard()['expiring']])
        later.alert_date = now + timedelta(days=12)
        self.assertNotIn(later.id, [lot['id'] for lot in self.Touch.get_home_dashboard()['expiring']],
                         "The alert date of the lot, when it has one")

    def test_sell_expired_lot(self):
        """ An expired lot is shown as such when it is chosen, and selling it delivers it
        without the confirmation of product_expiry. """
        lot = self._lot('HOME-OLD', 30.0, fields.Datetime.now() - timedelta(hours=1))
        data = next(item for item in self.Touch.get_product_lots(self.pear.id) if item['id'] == lot.id)
        self.assertTrue(data['expiry_alert'])
        self.assertLessEqual(data['days_left'], 0)
        result = self.Touch.sell({'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'lines': [{
            'product_id': self.pear.id, 'lot_id': lot.id, 'qty': 10.0, 'price_unit': 2.0,
        }]})
        order = self.env['sale.order'].browse(result['order']['id'])
        self.assertEqual(order.picking_ids.mapped('state'), ['done'])

    def test_unread_messages(self):
        """ The messages of a direct chat and of a channel, unread until marked as read. """
        colleague = self.env['res.users'].create({
            'name': 'Home Colleague', 'login': 'home_colleague',
            'group_ids': [Command.link(self.env.ref('base.group_user').id)],
        })
        me = self.Touch.env.user
        chat = self.env['discuss.channel'].with_user(colleague)._get_or_create_chat([me.partner_id.id])
        chat.with_user(colleague).message_post(body="Hay que cargar el camión", message_type='comment')
        channel = self.env['discuss.channel']._create_channel(name="Home Counter", group_id=None)
        channel._add_members(users=me | colleague)
        channel.with_user(colleague).message_post(body=Markup("<p>Llega el tomate</p>"), message_type='comment')
        messages = {message['id']: message for message in self.Touch.get_home_dashboard()['messages']}
        self.assertEqual(messages[chat.id]['name'], colleague.name)
        self.assertEqual(messages[chat.id]['type'], 'chat')
        self.assertEqual(messages[chat.id]['body'], "Hay que cargar el camión")
        self.assertEqual(messages[channel.id]['body'], "Llega el tomate")
        self.assertEqual(messages[channel.id]['author'], colleague.name)
        self.assertEqual(messages[channel.id]['unread'], 1)
        self.Touch.mark_messages_read([chat.id])
        ids = [message['id'] for message in self.Touch.get_home_dashboard()['messages']]
        self.assertNotIn(chat.id, ids)
        self.assertIn(channel.id, ids)
        self.Touch.mark_messages_read()
        self.assertNotIn(channel.id, [message['id'] for message in self.Touch.get_home_dashboard()['messages']])
        with self.assertRaises(ValidationError):
            self.Touch.mark_messages_read(["x"])

    def test_sales_of_the_day(self):
        before = self.Touch.get_home_dashboard()
        lot = self._lot('HOME-SALE', 50.0)
        self.Touch.sell({'uuid': str(uuid.uuid4()), 'partner_id': self.customer.id, 'lines': [{
            'product_id': self.pear.id, 'lot_id': lot.id, 'qty': 12.0, 'price_unit': 2.5,
            'box_qty': 2, 'box_product_id': self.box.id,
        }]})
        after = self.Touch.get_home_dashboard()
        self.assertAlmostEqual(after['sales']['amount'] - before['sales']['amount'], 30.0)
        self.assertAlmostEqual(after['sales']['kg'] - before['sales']['kg'], 12.0)
        self.assertEqual(after['sales']['count'] - before['sales']['count'], 1)
        self.assertEqual(after['sales']['boxes'] - before['sales']['boxes'], 2)
