import uuid

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestScrapTouch(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supplier = cls.env['res.partner'].create({'name': 'Scrap Supplier'})
        cls.vehicle = cls.env['product.product'].create({
            'name': 'Vehicle to dismantle', 'type': 'consu', 'is_storable': True, 'tracking': 'serial',
            'is_template': True, 'supplier_taxes_id': [Command.clear()],
        })
        cls.van = cls.env['product.product'].create({
            'name': 'Van to dismantle', 'type': 'consu', 'is_storable': True, 'tracking': 'serial',
            'is_template': True, 'supplier_taxes_id': [Command.clear()],
        })
        cls.batteries = cls.env['product.product'].create({
            'name': 'Used batteries', 'type': 'consu', 'is_storable': True, 'tracking': 'lot',
            'is_template': True,
        })
        cls.tyres = cls.env['product.product'].create({
            'name': 'Used tyres', 'type': 'consu', 'is_storable': True, 'tracking': False,
            'is_template': True,
        })
        cls.other = cls.env['product.product'].create({
            'name': 'Not a template', 'type': 'consu', 'is_storable': True, 'tracking': 'serial',
        })
        cls.user = new_test_user(
            cls.env, login='scrap_touch_user', name='Scrap Touch User',
            groups='purchase.group_purchase_user,stock.group_stock_user,stock.group_production_lot',
        )
        cls.touch = cls.env['scrap.touch'].with_user(cls.user)

    def _line(self, product, lot_name, price_unit=250.0, **vals):
        return {'product_id': product.id, 'lot_name': lot_name, 'price_unit': price_unit, **vals}

    def _vals(self, lines, **vals):
        return {'uuid': str(uuid.uuid4()), 'partner_id': self.supplier.id, 'lines': lines, **vals}

    def _stock(self, lot):
        """ Stock of a serial number, in the location of its vehicle (see scrap_base). """
        self.assertTrue(lot)
        quants = self.env['stock.quant'].search([
            ('product_id', '=', lot.product_id.id), ('lot_id', '=', lot.id),
            ('location_id', '=', lot.product_id.scrap_location_id.id),
        ])
        return sum(quants.mapped('quantity'))

    def _lot(self, name):
        return self.env['stock.lot'].search([('name', '=', name)])

    def test_screen_data(self):
        """ Only the scrap templates tracked by serial number. """
        data = self.touch.get_screen_data()
        ids = [product['id'] for product in data['products']]
        self.assertIn(self.vehicle.id, ids)
        self.assertIn(self.van.id, ids)
        self.assertNotIn(self.batteries.id, ids, "Tracked by lots")
        self.assertNotIn(self.tyres.id, ids, "Not tracked")
        self.assertNotIn(self.other.id, ids, "Not a scrap template")

    def test_search_suppliers(self):
        partners = self.touch.search_partners('Scrap Supp')
        self.assertEqual([partner['id'] for partner in partners], [self.supplier.id])

    def test_purchase_at_once(self):
        """ Several vehicles bought and received in one call, without a draft before. """
        result = self.touch.purchase_entry(self._vals([
            self._line(self.vehicle, '1234 abc', 900.0),
            self._line(self.van, 'mu-5678-bx', 1100.0),
        ]))
        order = self.env['purchase.order'].browse(result['id'])
        self.assertEqual(order.state, 'purchase')
        self.assertEqual(order.partner_id, self.supplier)
        self.assertEqual(order.order_line.mapped('product_qty'), [1, 1])
        self.assertEqual(order.amount_untaxed, 2000)
        self.assertTrue(all(picking.state == 'done' for picking in order.picking_ids))
        self.assertTrue(result['received'])
        self.assertEqual([line['lots'] for line in result['lines']], [['1234ABC'], ['MU5678BX']],
                         "The license plates are written in capitals, without spaces nor hyphens")
        self.assertEqual(self._stock(self._lot('1234ABC')), 1)
        self.assertEqual(self._stock(self._lot('MU5678BX')), 1)
        # Each vehicle is a product of its own, copied from its template (see scrap_base)
        vehicle = self._lot('1234ABC').product_id
        self.assertEqual(vehicle.scrap_template_id, self.vehicle.product_tmpl_id)
        self.assertEqual(order.order_line[0].product_id, vehicle)
        self.assertEqual(result['lines'][0]['location'], vehicle.scrap_location_id.display_name)
        self.assertTrue(result['lines'][0]['location'].endswith('/1234ABC'))

    def test_draft(self):
        """ The purchase is saved in draft with each change, resumed, then bought. """
        vals = self._vals([self._line(self.vehicle, '1111AAA', 500.0)])
        draft = self.touch.save_draft(vals)
        order = self.env['purchase.order'].browse(draft['id'])
        self.assertEqual(order.state, 'draft')
        self.assertEqual(order.order_line.scrap_lot_name, '1111AAA')

        # Saved again with the same uuid (a retry whose answer was lost, so without the ids of
        # the lines): the same draft, with the same vehicle once
        retry = self.touch.save_draft(vals)
        self.assertEqual(retry['id'], order.id)
        self.assertEqual(len(order.order_line), 1)
        first_line_id = retry['line_ids'][0]

        # A second vehicle, and the price of the first one changed
        draft = self.touch.save_draft(self._vals([
            self._line(self.vehicle, '1111AAA', 450.0, line_id=first_line_id),
            self._line(self.van, '2222BBB', 700.0),
        ], order_id=order.id))
        self.assertEqual(draft['line_ids'][0], first_line_id, "The line is kept")
        self.assertEqual(order.order_line.mapped('price_unit'), [450, 700])

        drafts = self.touch.get_drafts('2222BBB')
        self.assertEqual([draft['id'] for draft in drafts], [order.id], "Found by its license plate")
        self.assertEqual(drafts[0]['line_count'], 2)

        resumed = self.touch.get_draft(order.id)
        self.assertEqual(resumed['partner']['id'], self.supplier.id)
        self.assertEqual([line['lot_name'] for line in resumed['lines']], ['1111AAA', '2222BBB'])

        # The first vehicle removed
        second_line_id = draft['line_ids'][1]
        self.touch.save_draft(self._vals([
            self._line(self.van, '2222BBB', 700.0, line_id=second_line_id),
        ], order_id=order.id))
        self.assertEqual(order.order_line.ids, [second_line_id])

        result = self.touch.purchase_entry(self._vals([
            self._line(self.van, '2222BBB', 700.0, line_id=second_line_id),
        ], order_id=order.id))
        self.assertEqual(result['id'], order.id)
        self.assertEqual(order.state, 'purchase')
        self.assertEqual(self._stock(self._lot('2222BBB')), 1)
        self.assertNotIn(order.id, [draft['id'] for draft in self.touch.get_drafts()])

        # Sent twice: already bought, nothing more
        again = self.touch.purchase_entry(self._vals([
            self._line(self.van, '2222BBB', 700.0, line_id=second_line_id),
        ], order_id=order.id))
        self.assertEqual(again['id'], order.id)
        self.assertEqual(len(self._lot('2222BBB')), 1)

    def test_cancel_draft(self):
        draft = self.touch.save_draft(self._vals([self._line(self.vehicle, '3333CCC')]))
        self.touch.cancel_draft(draft['id'])
        order = self.env['purchase.order'].browse(draft['id'])
        self.assertEqual(order.state, 'cancel')
        self.assertNotIn(draft['id'], [order['id'] for order in self.touch.get_drafts()])
        with self.assertRaises(UserError):
            self.touch.purchase_entry(self._vals([self._line(self.vehicle, '3333CCC')], order_id=order.id))

    def test_same_uuid_doesnt_duplicate(self):
        vals = self._vals([self._line(self.vehicle, '4444DDD', 100.0)])
        first = self.touch.purchase_entry(vals)
        second = self.touch.purchase_entry(vals)
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(self.env['purchase.order'].search_count([('partner_id', '=', self.supplier.id)]), 1)

    def test_plate_received_once(self):
        """ The same license plate, written in another way, can't be received again. """
        self.touch.purchase_entry(self._vals([self._line(self.vehicle, '5555EEE')]))
        with self.assertRaises(UserError):
            self.touch.save_draft(self._vals([self._line(self.vehicle, '5555-eee')]))

    def test_plate_received_meanwhile(self):
        """ A license plate received by another purchase after it was saved in a draft. """
        draft = self.touch.save_draft(self._vals([self._line(self.vehicle, '6666FFF')]))
        self.touch.purchase_entry(self._vals([self._line(self.vehicle, '6666FFF')]))
        with self.assertRaises(UserError):
            self.touch.purchase_entry(self._vals([
                self._line(self.vehicle, '6666FFF', line_id=draft['line_ids'][0]),
            ], order_id=draft['id']))

    def test_plate_in_two_lines(self):
        with self.assertRaises(ValidationError):
            self.touch.save_draft(self._vals([
                self._line(self.vehicle, '7777GGG'),
                self._line(self.van, '7777 ggg'),
            ]))

    def test_plate_of_another_vehicle(self):
        """ A license plate bought, not received yet, can't be bought again, with any template;
        once its purchase is cancelled, it can. """
        result = self.touch.purchase_entry(self._vals([self._line(self.vehicle, '7878GGG')]), False)
        with self.assertRaisesRegex(UserError, 'already used'):
            self.touch.save_draft(self._vals([self._line(self.van, '7878GGG')]))
        self.env['purchase.order'].browse(result['id']).button_cancel()
        self.assertTrue(self.touch.save_draft(self._vals([self._line(self.van, '7878GGG')])))

    def test_invalid_lines(self):
        for product in (self.batteries, self.tyres, self.other):
            with self.assertRaises(ValidationError):
                self.touch.save_draft(self._vals([self._line(product, '8888HHH')]))
        with self.assertRaises(ValidationError):
            self.touch.save_draft(self._vals([self._line(self.vehicle, ' - ')]))
        with self.assertRaises(ValidationError):
            self.touch.save_draft(self._vals([self._line(self.vehicle, '9999JJJ', -1)]))
        with self.assertRaises(ValidationError):
            self.touch.purchase_entry(self._vals([]))
        with self.assertRaises(ValidationError):
            self.touch.save_draft({'uuid': 'not-a-uuid', 'partner_id': self.supplier.id, 'lines': []})

    def test_supplier_cant_change(self):
        draft = self.touch.save_draft(self._vals([self._line(self.vehicle, '1010KKK')]))
        other = self.env['res.partner'].create({'name': 'Other Supplier'})
        with self.assertRaises(ValidationError):
            self.touch.save_draft(self._vals([self._line(self.vehicle, '1010KKK')],
                                             order_id=draft['id'], partner_id=other.id))

    def test_purchase_without_receiving(self):
        """ Bought now, received later in the backend: the receipt comes with the license plates. """
        result = self.touch.purchase_entry(self._vals([
            self._line(self.vehicle, '2020 lmn', 300.0),
            self._line(self.van, '3030-pqr', 400.0),
        ]), False)
        order = self.env['purchase.order'].browse(result['id'])
        self.assertEqual(order.state, 'purchase')
        self.assertFalse(result['received'])
        self.assertEqual([line['plate'] for line in result['lines']], ['2020LMN', '3030PQR'])
        picking = order.picking_ids
        self.assertNotEqual(picking.state, 'done')
        self.assertEqual(sorted(picking.move_line_ids.mapped('lot_name')), ['2020LMN', '3030PQR'])
        self.assertFalse(self._lot('2020LMN'))

        picking.move_ids.picked = True
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        self.assertEqual(self._stock(self._lot('2020LMN')), 1)
        self.assertEqual(self._stock(self._lot('3030PQR')), 1)

    def test_filters_receive_and_invoice(self):
        """ The purchases in progress, to receive, to invoice and all; a confirmed purchase
        received and invoiced from its summary. """
        draft = self.touch.save_draft(self._vals([self._line(self.vehicle, '1111QQQ')]))
        bought = self.touch.purchase_entry(self._vals([self._line(self.vehicle, '2222QQQ', 600.0)]), False)
        received = self.touch.purchase_entry(self._vals([self._line(self.van, '3333QQQ')]))

        mine = {draft['id'], bought['id'], received['id']}

        def ids(state_filter, query=''):
            """ Of this test, also in a database with other purchases, as scrap_demo. """
            return {order['id'] for order in self.touch.get_drafts(query, state_filter)} & mine

        self.assertEqual(ids('draft'), {draft['id']})
        self.assertEqual(ids('to_receive'), {bought['id']})
        self.assertEqual(ids('to_invoice'), {received['id']}, "Billed on received quantities")
        self.assertEqual(ids('all'), {draft['id'], bought['id'], received['id']})
        self.assertEqual(ids('all', '3333 qqq'), {received['id']}, "Found by a license plate received")
        with self.assertRaises(ValidationError):
            self.touch.get_drafts('', 'wrong')

        summary = self.touch.get_order_summary(bought['id'])
        self.assertTrue(summary['to_receive'])
        self.assertEqual(summary['partner_data']['id'], self.supplier.id)
        self.assertEqual(summary['lines'][0]['plate'], '2222QQQ')

        summary = self.touch.receive_order(bought['id'])
        self.assertFalse(summary['to_receive'])
        self.assertTrue(summary['received'])
        self.assertEqual(summary['lines'][0]['lots'], ['2222QQQ'])
        self.assertEqual(self._stock(self._lot('2222QQQ')), 1)
        self.assertEqual(ids('to_receive'), set())
        with self.assertRaises(UserError):
            self.touch.receive_order(bought['id'])

        self.user.group_ids |= self.env.ref('account.group_account_invoice')
        action = self.touch.invoice_order(bought['id'])
        self.assertEqual(action['res_model'], 'account.move')
        self.assertEqual(action['target'], 'new')
        order = self.env['purchase.order'].browse(bought['id'])
        self.assertEqual(order.invoice_ids.amount_untaxed, 600)
        self.assertEqual(self.touch.get_order_summary(bought['id'])['bills'][0]['state'], 'draft')
        with self.assertRaises(UserError):
            self.touch.invoice_order(draft['id'])

    def test_vehicle_refs(self):
        """ The vehicles received get their internal reference, by kind of entry (scrap_base). """
        Sequence = self.env['ir.sequence']
        self.env.company.write({
            'scrap_main_sequence_id': Sequence.create({'name': 'Dismantle', 'prefix': 'DES', 'padding': 3}).id,
            'scrap_refurbish_sequence_id': Sequence.create({'name': 'Sell', 'prefix': 'CV', 'padding': 3}).id,
        })
        result = self.touch.purchase_entry(self._vals([self._line(self.vehicle, '1313DDD')]))
        self.assertEqual(result['lines'][0]['refs'], ['DES001'])
        result = self.touch.purchase_entry(self._vals([self._line(self.vehicle, '1414EEE')], unbuild_type='refurbish'), False)
        self.assertEqual(result['lines'][0]['refs'], [], "Not received yet")
        result = self.touch.receive_order(result['id'])
        self.assertEqual(result['lines'][0]['refs'], ['CV001'])

    def test_kinds_of_entry(self):
        """ The purchases to dismantle and to repair and sell are listed apart. """
        scrap = self.touch.save_draft(self._vals([self._line(self.vehicle, '1212AAA')]))
        resale = self.touch.save_draft(self._vals([self._line(self.vehicle, '3434BBB')], unbuild_type='refurbish'))
        self.assertEqual(self.env['purchase.order'].browse(scrap['id']).unbuild_type, 'main', "Scrap entry by default")
        self.assertEqual(self.env['purchase.order'].browse(resale['id']).unbuild_type, 'refurbish')

        mine = {scrap['id'], resale['id']}

        def ids(unbuild_type, state_filter='draft'):
            return {order['id'] for order in self.touch.get_drafts('', state_filter, unbuild_type)} & mine

        self.assertEqual(ids('main'), {scrap['id']})
        self.assertEqual(ids('refurbish'), {resale['id']})

        # A purchase keeps its kind of entry
        with self.assertRaises(ValidationError):
            self.touch.save_draft(self._vals([self._line(self.vehicle, '1212AAA')],
                                             order_id=scrap['id'], unbuild_type='refurbish'))
        with self.assertRaises(ValidationError):
            self.touch.save_draft(self._vals([self._line(self.vehicle, '5656CCC')], unbuild_type='subproduct'))
        with self.assertRaises(ValidationError):
            self.touch.get_drafts('', 'draft', 'other')

        result = self.touch.purchase_entry(self._vals([self._line(self.vehicle, '3434BBB')],
                                                      order_id=resale['id'], unbuild_type='refurbish'))
        self.assertTrue(result['received'])
        self.assertEqual(ids('refurbish', 'all'), {resale['id']})
        self.assertNotIn(resale['id'], ids('main', 'all'))
