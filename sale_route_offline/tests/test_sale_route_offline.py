import uuid

from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestSaleRouteOffline(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.company_data['company']
        user_vals = {'company_id': company.id, 'company_ids': [Command.set(company.ids)]}
        cls.salesman = new_test_user(
            cls.env, login='route_salesman',
            groups='sales_team.group_sale_salesman,sale.group_discount_per_so_line', **user_vals)
        cls.other_salesman = new_test_user(
            cls.env, login='other_salesman', groups='sales_team.group_sale_salesman', **user_vals)
        cls.billing_user = new_test_user(cls.env, login='route_billing', groups='account.group_account_invoice', **user_vals)
        cls.group_user._apply_group(cls.env.ref('product.group_product_pricelist'))
        cls.pricelist = cls.env['product.pricelist'].create({
            'name': 'Route Pricelist',
            'item_ids': [Command.create({
                'applied_on': '0_product_variant',
                'product_id': cls.product_a.id,
                'compute_price': 'fixed',
                'fixed_price': 80.0,
            })],
        })
        cls.customer, cls.other_customer = cls.env['res.partner'].create([{
            'name': 'Route Customer',
            'user_id': cls.salesman.id,
            'property_product_pricelist': cls.pricelist.id,
            'credit_limit': 150.0,
        }, {
            'name': 'Other Customer',
            'user_id': cls.other_salesman.id,
        }])
        cls.contact = cls.env['res.partner'].create({'name': 'Route Contact', 'parent_id': cls.customer.id})
        company.account_use_credit_limit = True
        # Invoices of the admin, not visible to the salesman through the access rules
        cls.overdue_invoice = cls.init_invoice('out_invoice', cls.customer, invoice_date='2019-01-01', amounts=[100.0], post=True)
        cls.recent_invoice = cls.init_invoice(
            'out_invoice', cls.customer, invoice_date=fields.Date.today(), amounts=[40.0], post=True)
        cls.other_invoice = cls.init_invoice('out_invoice', cls.other_customer, amounts=[10.0], post=True)
        cls.bank_journal = cls.company_data['default_journal_bank']
        cls.cash_journal = cls.company_data['default_journal_cash']

    def _order_vals(self, **kwargs):
        return {
            'offline_uuid': str(uuid.uuid4()),
            'partner_id': self.customer.id,
            'revision': 1,
            'lines': [{'product_id': self.product_a.id, 'qty': 3, 'discount': 10}],
            **kwargs,
        }

    def _payment_vals(self, **kwargs):
        return {
            'offline_uuid': str(uuid.uuid4()),
            'partner_id': self.customer.id,
            'amount': 100.0,
            'journal_id': self.cash_journal.id,
            'invoice_ids': [self.overdue_invoice.id],
            'memo': 'Cash on the route',
            **kwargs,
        }

    # ---- get_route_data ----

    def test_get_route_data_content(self):
        self.company_data['company'].route_order_count = 1
        SaleOrder = self.env['sale.order'].with_user(self.salesman)
        old_order = SaleOrder.create({
            'partner_id': self.contact.id,
            'date_order': '2026-01-01 10:00:00',
            'order_line': [Command.create({'product_id': self.product_a.id, 'product_uom_qty': 4})],
        })
        last_order = SaleOrder.create({
            'partner_id': self.customer.id,
            'order_line': [Command.create({'product_id': self.product_a.id, 'product_uom_qty': 2})],
        })
        (old_order | last_order).action_confirm()

        data = self.env['res.partner'].with_user(self.salesman).get_route_data()

        self.assertEqual([customer['id'] for customer in data['customers']], self.customer.ids,
                         "Only the customers of the salesman, without their contacts")
        customer = data['customers'][0]
        self.assertAlmostEqual(customer['overdue'], self.overdue_invoice.amount_total)
        self.assertAlmostEqual(customer['not_due'], self.recent_invoice.amount_total)
        self.assertEqual(customer['credit_limit'], 150.0)
        self.assertEqual([inv['id'] for inv in customer['invoices']], [self.overdue_invoice.id, self.recent_invoice.id])
        self.assertTrue(customer['invoices'][0]['overdue'])
        self.assertFalse(customer['invoices'][1]['overdue'])
        self.assertEqual([order['id'] for order in customer['orders']], last_order.ids, "Only the last order")
        order_data = customer['orders'][0]
        self.assertEqual(order_data['lines'][0]['product_id'], self.product_a.id)
        self.assertEqual(order_data['lines'][0]['line_id'], last_order.order_line.id)
        self.assertEqual(order_data['state_code'], 'sale')
        self.assertEqual(order_data['invoice_status_code'], last_order.invoice_status)
        self.assertTrue(order_data['invoice_status'])
        self.assertTrue(order_data['delivery_date'], "Expected date of the confirmed order")
        self.assertFalse(order_data['commitment_date'])

        # Orders of the customer and of its contact make the usual products
        [usual] = customer['usual_products']
        self.assertEqual(usual['product_id'], self.product_a.id)
        self.assertEqual(usual['count'], 2)
        self.assertAlmostEqual(usual['qty'], 3.0)
        self.assertAlmostEqual(usual['price'], 80.0, msg="Price of the pricelist of the customer")
        expected_tax = sum(self.product_a.taxes_id.filtered(lambda t: not t.price_include).mapped('amount'))
        self.assertAlmostEqual(usual['tax_percent'], expected_tax)

        product = next(product for product in data['products'] if product['id'] == self.product_a.id)
        self.assertEqual(product['categ_id'], self.product_a.categ_id.id)
        self.assertTrue(product['image_unique'])
        self.assertIn(self.product_a.categ_id.id, [category['id'] for category in data['categories']])
        self.assertAlmostEqual(data['prices'][customer['price_key']][self.product_a.id], 80.0)
        self.assertEqual({journal['id'] for journal in data['journals']},
                         set(self.company_data['company']._get_route_payment_journals().ids))
        self.assertTrue(data['generated_at'])

    def test_get_route_data_journals(self):
        self.company_data['company'].route_payment_journal_ids = self.cash_journal
        data = self.env['res.partner'].with_user(self.salesman).get_route_data()
        self.assertEqual([journal['id'] for journal in data['journals']], self.cash_journal.ids)

    def test_get_route_data_requires_salesman(self):
        with self.assertRaises(AccessError):
            self.env['res.partner'].with_user(self.billing_user).get_route_data()

    # ---- sale.order.save_from_tablet ----

    def test_create_order_idempotent(self):
        vals = self._order_vals()
        SaleOrder = self.env['sale.order'].with_user(self.salesman)
        result = SaleOrder.save_from_tablet(vals)
        # The connection was lost after the commit: the tablet sends the same order again
        self.assertEqual(SaleOrder.save_from_tablet(vals), result)

        order = self.env['sale.order'].search([('offline_uuid', '=', vals['offline_uuid'])])
        self.assertEqual(order.id, result['id'])
        self.assertEqual(order.state, 'draft')
        self.assertEqual(order.user_id, self.salesman)
        self.assertEqual(order.create_uid, self.salesman)
        self.assertEqual(order.partner_id, self.customer)
        self.assertEqual(order.order_line.price_unit, 80.0, "The price is computed by the server")
        self.assertEqual(order.order_line.discount, 10.0)
        self.assertEqual(order.order_line.product_uom_qty, 3.0)
        self.assertEqual(order.offline_revision, 1)

    def test_update_order_by_revision(self):
        vals = self._order_vals()
        SaleOrder = self.env['sale.order'].with_user(self.salesman)
        SaleOrder.save_from_tablet(vals)
        new_lines = [
            {'product_id': self.product_a.id, 'qty': 5, 'discount': 0},
            {'product_id': self.product_b.id, 'qty': 1, 'discount': 0},
        ]
        result = SaleOrder.save_from_tablet(dict(vals, revision=2, lines=new_lines))
        order = self.env['sale.order'].browse(result['id'])
        self.assertEqual(order.order_line.mapped('product_uom_qty'), [5.0, 1.0], "The lines are replaced")
        self.assertEqual(order.offline_revision, 2)

        # The first version arrives late, and the second one again: both are ignored
        SaleOrder.save_from_tablet(vals)
        SaleOrder.save_from_tablet(dict(vals, revision=2, lines=new_lines[:1]))
        self.assertEqual(order.order_line.mapped('product_uom_qty'), [5.0, 1.0])
        self.assertEqual(self.env['sale.order'].search_count([('offline_uuid', '=', vals['offline_uuid'])]), 1)

        with self.assertRaises(ValidationError, msg="The customer can't change"):
            SaleOrder.save_from_tablet(dict(vals, revision=3, partner_id=self.env['res.partner'].create({
                'name': 'Another Route Customer', 'user_id': self.salesman.id}).id))

    def test_confirm_order(self):
        vals = self._order_vals()
        SaleOrder = self.env['sale.order'].with_user(self.salesman)
        SaleOrder.save_from_tablet(vals)
        result = SaleOrder.save_from_tablet(dict(vals, revision=2, confirm=True))
        self.assertEqual(result['state'], 'sale')
        order = self.env['sale.order'].browse(result['id'])
        self.assertEqual(order.state, 'sale')

        # Sent again: nothing changes
        self.assertEqual(SaleOrder.save_from_tablet(dict(vals, revision=2, confirm=True)), result)
        # A confirmed order can't be changed from the tablet
        with self.assertRaises(ValidationError):
            SaleOrder.save_from_tablet(dict(vals, revision=3))

    def test_confirm_new_order(self):
        result = self.env['sale.order'].with_user(self.salesman).save_from_tablet(self._order_vals(confirm=True))
        self.assertEqual(result['state'], 'sale')

    def test_confirm_order_confirmed_meanwhile(self):
        vals = self._order_vals()
        SaleOrder = self.env['sale.order'].with_user(self.salesman)
        order = self.env['sale.order'].browse(SaleOrder.save_from_tablet(vals)['id'])
        order.action_confirm()
        result = SaleOrder.save_from_tablet(dict(vals, revision=2, confirm=True))
        self.assertEqual(result['state'], 'sale')
        self.assertEqual(order.offline_revision, 2)

    def _backend_quotation(self):
        return self.env['sale.order'].with_user(self.salesman).create({
            'partner_id': self.customer.id,
            'order_line': [
                Command.create({'display_type': 'line_section', 'name': 'Drinks'}),
                Command.create({'product_id': self.product_a.id, 'product_uom_qty': 1}),
                Command.create({'product_id': self.product_b.id, 'product_uom_qty': 4}),
                Command.create({'display_type': 'line_note', 'name': 'Leave it at the back door'}),
            ],
        })

    def test_change_backend_quotation(self):
        quotation = self._backend_quotation()
        line_a, line_b = quotation.order_line.filtered('product_id')
        new_product = self.product_a.copy({'name': 'product_a2'})
        vals = self._order_vals(order_id=quotation.id, lines=[
            {'product_id': self.product_a.id, 'qty': 6, 'discount': 5, 'line_id': line_a.id},
            {'product_id': new_product.id, 'qty': 2, 'discount': 0},
        ])
        result = self.env['sale.order'].with_user(self.salesman).save_from_tablet(vals)

        self.assertEqual(result['id'], quotation.id)
        self.assertEqual(quotation.offline_uuid, vals['offline_uuid'])
        self.assertEqual(quotation.offline_revision, 1)
        self.assertTrue(line_a.exists(), "The line known by the tablet is updated")
        self.assertEqual((line_a.product_uom_qty, line_a.discount), (6.0, 5.0))
        self.assertFalse(line_b.exists(), "The line removed on the tablet is removed")
        self.assertEqual(quotation.order_line.filtered('display_type').mapped('name'),
                         ['Drinks', 'Leave it at the back door'], "Sections and notes are kept")
        self.assertEqual(quotation.order_line.filtered('product_id').product_id, self.product_a | new_product)

        # Next version from the same tablet, now known by its uuid, and confirmed
        result = self.env['sale.order'].with_user(self.salesman).save_from_tablet(dict(vals, revision=2, confirm=True))
        self.assertEqual(result['state'], 'sale')

    def test_change_backend_quotation_access(self):
        quotation = self._backend_quotation()
        lines = [{'product_id': self.product_a.id, 'qty': 1}]
        with self.assertRaises(AccessError, msg="An order of another salesperson"):
            self.env['sale.order'].with_user(self.other_salesman).save_from_tablet(
                self._order_vals(order_id=quotation.id, partner_id=self.other_customer.id, lines=lines))
        quotation.offline_uuid = str(uuid.uuid4())
        with self.assertRaises(ValidationError, msg="Changed from another tablet"):
            self.env['sale.order'].with_user(self.salesman).save_from_tablet(
                self._order_vals(order_id=quotation.id, lines=lines))
        quotation.offline_uuid = False
        quotation.action_confirm()
        with self.assertRaises(ValidationError, msg="Not a quotation anymore"):
            self.env['sale.order'].with_user(self.salesman).save_from_tablet(
                self._order_vals(order_id=quotation.id, lines=lines))

    def test_line_note(self):
        self.product_a.description_sale = 'Fresh, vacuum packed'
        vals = self._order_vals(lines=[
            {'product_id': self.product_a.id, 'qty': 1, 'note': 'Cut in thin slices '},
            {'product_id': self.product_b.id, 'qty': 1, 'note': 'In a separate box'},
            {'product_id': self.product_b.id, 'qty': 2},
        ])
        SaleOrder = self.env['sale.order'].with_user(self.salesman)
        order = self.env['sale.order'].browse(SaleOrder.save_from_tablet(vals)['id'])
        line_a, line_b, line_b2 = order.order_line
        self.assertEqual(line_a.name, 'Fresh, vacuum packed\nCut in thin slices', "Under the product description")
        self.assertEqual(line_b.name, 'In a separate box', "Product without description")
        self.assertFalse(line_b2.name)

        # The route data gives the text back to the tablet
        data = self.env['res.partner'].with_user(self.salesman).get_route_data()
        order_data = next(o for o in data['customers'][0]['orders'] if o['id'] == order.id)
        self.assertEqual([line['note'] for line in order_data['lines']], ['Cut in thin slices', 'In a separate box', ''])

        # Next version: one text changed, one removed, one line without text sent
        SaleOrder.save_from_tablet(dict(vals, revision=2, lines=[
            {'product_id': self.product_a.id, 'qty': 1, 'line_id': line_a.id, 'note': 'Cut in thick slices'},
            {'product_id': self.product_b.id, 'qty': 1, 'line_id': line_b.id, 'note': ''},
            {'product_id': self.product_b.id, 'qty': 3, 'line_id': line_b2.id},
        ]))
        self.assertEqual(line_a.name, 'Fresh, vacuum packed\nCut in thick slices')
        self.assertFalse(line_b.name)
        self.assertEqual(line_b2.product_uom_qty, 3.0)

        with self.assertRaises(ValidationError):
            SaleOrder.save_from_tablet(self._order_vals(lines=[{'product_id': self.product_a.id, 'qty': 1, 'note': 'x' * 501}]))

    def test_line_note_keeps_backend_description(self):
        quotation = self._backend_quotation()
        line_a = quotation.order_line.filtered('product_id')[0]
        line_a.name = 'Written in the backend'
        self.env['sale.order'].with_user(self.salesman).save_from_tablet(self._order_vals(order_id=quotation.id, lines=[
            {'product_id': self.product_a.id, 'qty': 2, 'line_id': line_a.id},
        ]))
        self.assertEqual(line_a.name, 'Written in the backend', "No text sent: the description stays")

    def test_create_from_tablet_compatibility(self):
        vals = self._order_vals()
        del vals['revision']
        result = self.env['sale.order'].with_user(self.salesman).create_from_tablet(vals)
        self.assertEqual(result['state'], 'draft')

    def test_create_order_for_contact(self):
        result = self.env['sale.order'].with_user(self.salesman).save_from_tablet(
            self._order_vals(partner_id=self.contact.id))
        self.assertEqual(self.env['sale.order'].browse(result['id']).partner_id, self.customer)

    def test_create_order_access(self):
        SaleOrder = self.env['sale.order'].with_user(self.salesman)
        with self.assertRaises(AccessError):
            SaleOrder.save_from_tablet(self._order_vals(partner_id=self.other_customer.id))
        vals = self._order_vals(partner_id=self.other_customer.id)
        self.env['sale.order'].with_user(self.other_salesman).save_from_tablet(vals)
        with self.assertRaises(AccessError, msg="The uuid of an order of another user"):
            SaleOrder.save_from_tablet(dict(vals, partner_id=self.customer.id))
        with self.assertRaises(AccessError):
            self.env['sale.order'].with_user(self.billing_user).save_from_tablet(self._order_vals())

    def test_create_order_validation(self):
        SaleOrder = self.env['sale.order'].with_user(self.salesman)
        not_saleable = self.product_b.copy({'sale_ok': False})
        invalid_vals = [
            self._order_vals(offline_uuid='not-a-uuid'),
            self._order_vals(revision=0),
            self._order_vals(revision='2'),
            self._order_vals(confirm='yes'),
            self._order_vals(partner_id='1'),
            self._order_vals(lines=[]),
            self._order_vals(lines=[{'product_id': self.product_a.id, 'qty': 0}]),
            self._order_vals(lines=[{'product_id': self.product_a.id, 'qty': 1, 'discount': 120}]),
            self._order_vals(lines=[{'product_id': not_saleable.id, 'qty': 1}]),
            self._order_vals(lines=[{'product_id': 0, 'qty': 1}]),
            'not a dict',
        ]
        for vals in invalid_vals:
            with self.subTest(vals=vals), self.assertRaises(ValidationError):
                SaleOrder.save_from_tablet(vals)
        self.assertFalse(self.env['sale.order'].search([('partner_id', '=', self.customer.id)]))

    def test_create_order_without_discount_feature(self):
        result = self.env['sale.order'].with_user(self.other_salesman).save_from_tablet(
            self._order_vals(partner_id=self.other_customer.id))
        self.assertEqual(self.env['sale.order'].browse(result['id']).order_line.discount, 0.0,
                         "Without the discount feature, the discount of the tablet is ignored")

    # ---- account.payment.create_from_tablet ----

    def test_create_payment_idempotent(self):
        vals = self._payment_vals()
        AccountPayment = self.env['account.payment'].with_user(self.salesman)
        result = AccountPayment.create_from_tablet(vals)
        self.assertEqual(AccountPayment.create_from_tablet(vals), result)

        payment = self.env['account.payment'].search([('offline_uuid', '=', vals['offline_uuid'])])
        self.assertEqual(payment.id, result['id'])
        self.assertEqual(payment.state, 'draft')
        self.assertEqual(payment.create_uid, self.salesman)
        self.assertEqual(payment.partner_id, self.customer)
        self.assertEqual(payment.payment_type, 'inbound')
        self.assertEqual(payment.amount, 100.0)
        self.assertEqual(payment.journal_id, self.cash_journal)
        self.assertEqual(payment.invoice_ids, self.overdue_invoice)
        self.assertEqual(payment.memo, 'Cash on the route')
        self.assertFalse(payment.move_id, "A draft payment has no journal entry")
        self.assertEqual(self.overdue_invoice.payment_state, 'not_paid', "The accounting team reconciles it")

    def _post_tablet_payment(self, **kwargs):
        result = self.env['account.payment'].with_user(self.salesman).create_from_tablet(self._payment_vals(**kwargs))
        payment = self.env['account.payment'].browse(result['id'])
        # The accounting team checks the payment and confirms it
        payment.with_user(self.billing_user).action_post()
        return payment

    def test_post_payment_reconciles_invoices(self):
        payment = self._post_tablet_payment(
            amount=self.overdue_invoice.amount_residual + self.recent_invoice.amount_residual,
            invoice_ids=[self.overdue_invoice.id, self.recent_invoice.id])
        self.assertTrue(payment.move_id)
        for invoice in self.overdue_invoice | self.recent_invoice:
            self.assertIn(invoice.payment_state, ('paid', 'in_payment'))
            self.assertFalse(invoice.amount_residual)
        self.assertEqual(payment.reconciled_invoice_ids, self.overdue_invoice | self.recent_invoice)

    def test_post_payment_partial(self):
        residual = self.overdue_invoice.amount_residual
        self._post_tablet_payment(amount=residual - 30.0)
        self.assertEqual(self.overdue_invoice.payment_state, 'partial')
        self.assertAlmostEqual(self.overdue_invoice.amount_residual, 30.0)
        self.assertEqual(self.recent_invoice.payment_state, 'not_paid', "Only the chosen invoices")

    def test_post_other_payment_not_reconciled(self):
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.customer.id,
            'amount': self.overdue_invoice.amount_residual,
            'journal_id': self.cash_journal.id,
            'invoice_ids': [Command.set(self.overdue_invoice.ids)],
        })
        payment.action_post()
        self.assertEqual(self.overdue_invoice.payment_state, 'not_paid', "Only the payments of the tablet")

    def test_create_payment_access(self):
        AccountPayment = self.env['account.payment'].with_user(self.salesman)
        with self.assertRaises(AccessError):
            AccountPayment.create_from_tablet(self._payment_vals(partner_id=self.other_customer.id, invoice_ids=[]))
        with self.assertRaises(AccessError, msg="Salespeople can't read payments"):
            self.env['account.payment'].with_user(self.salesman).search([])

    def test_create_payment_validation(self):
        self.company_data['company'].route_payment_journal_ids = self.cash_journal
        AccountPayment = self.env['account.payment'].with_user(self.salesman)
        invalid_vals = [
            self._payment_vals(journal_id=self.bank_journal.id),
            self._payment_vals(journal_id=self.company_data['default_journal_sale'].id),
            self._payment_vals(amount=0),
            self._payment_vals(amount=-5),
            self._payment_vals(amount='100'),
            self._payment_vals(invoice_ids=[self.other_invoice.id]),
            self._payment_vals(invoice_ids=[999999999]),
            self._payment_vals(memo='x' * 201),
            self._payment_vals(date='2019-01-01'),
            self._payment_vals(date='not a date'),
            self._payment_vals(offline_uuid=None),
        ]
        for vals in invalid_vals:
            with self.subTest(vals=vals), self.assertRaises(ValidationError):
                AccountPayment.create_from_tablet(vals)
        self.assertFalse(self.env['account.payment'].search([('partner_id', '=', self.customer.id)]))

    # ---- get_route_sync_status ----

    def test_get_route_sync_status(self):
        order_vals, payment_vals = self._order_vals(), self._payment_vals()
        self.env['sale.order'].with_user(self.salesman).save_from_tablet(order_vals)
        self.env['account.payment'].with_user(self.salesman).create_from_tablet(payment_vals)
        other_vals = self._order_vals(partner_id=self.other_customer.id)
        self.env['sale.order'].with_user(self.other_salesman).save_from_tablet(other_vals)
        pending_uuid = str(uuid.uuid4())

        self.env['sale.order'].with_user(self.salesman).save_from_tablet(dict(order_vals, revision=3))

        status = self.env['res.partner'].with_user(self.salesman).get_route_sync_status([
            order_vals['offline_uuid'], payment_vals['offline_uuid'], other_vals['offline_uuid'], pending_uuid,
        ])
        self.assertEqual(status, {order_vals['offline_uuid']: 3, payment_vals['offline_uuid']: 1})
