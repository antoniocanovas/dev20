from odoo import Command
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestScrapBase(TransactionCase):

    def test_lots_enabled(self):
        """ Lots & Serial Numbers is enabled for internal users, also when it was disabled. """
        lots = self.env.ref('stock.group_production_lot')
        group_user = self.env.ref('base.group_user')
        self.assertIn(lots, group_user.all_implied_ids)
        self.assertTrue(new_test_user(self.env, login='scrap_base_user').has_group('stock.group_production_lot'))

        group_user._remove_group(lots)
        self.assertNotIn(lots, group_user.all_implied_ids)
        self.env['res.groups']._scrap_base_enable_lots()
        self.assertIn(lots, group_user.all_implied_ids)


@tagged('post_install', '-at_install')
class TestScrapChassis(TransactionCase):

    def test_without_variants(self):
        """ Set on the template, kept by its only variant, and the other way round. """
        template = self.env['product.template'].create({'name': 'Chassis Car', 'chassis': 'VF1AAA'})
        self.assertEqual(template.product_variant_id.chassis, 'VF1AAA')
        template.chassis = 'VF1BBB'
        self.assertEqual(template.product_variant_id.chassis, 'VF1BBB')
        template.product_variant_id.chassis = 'VF1CCC'
        self.assertEqual(template.chassis, 'VF1CCC')
        self.assertFalse(template.copy().chassis, "Not copied")

    def test_with_variants(self):
        """ Each variant has its own; the template has none. """
        attribute = self.env['product.attribute'].create({
            'name': 'Chassis Color', 'value_ids': [Command.create({'name': 'Red'}), Command.create({'name': 'Blue'})],
        })
        template = self.env['product.template'].create({
            'name': 'Chassis Van',
            'attribute_line_ids': [Command.create({'attribute_id': attribute.id, 'value_ids': [Command.set(attribute.value_ids.ids)]})],
        })
        red, blue = template.product_variant_ids
        red.chassis = 'VF1RED'
        blue.chassis = 'VF1BLUE'
        self.assertFalse(template.chassis)
        template.chassis = 'VF1ALL'
        self.assertEqual((red | blue).mapped('chassis'), ['VF1RED', 'VF1BLUE'], "The variants keep theirs")
        self.assertEqual(self.env['product.product'].search([('chassis', '=', 'VF1BLUE')]), blue)


@tagged('post_install', '-at_install')
class TestScrapCatSearch(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.part = cls.env['product.product'].create({
            'name': 'Search Alternator', 'chassis': 'WVWZZZ1JZ3W386752', 'plate': 'PL-778',
            'ref_oem': '06B903016', 'ref_market': 'BOSCH 0124', 'references': 'AL1234 / CA1556',
        })
        cls.other = cls.env['product.product'].create({'name': 'Search Starter'})

    def test_name_search(self):
        """ Found by its CAT data in the product fields, as a variant and as a template. """
        for value in ('1JZ3W386', 'pl-778', '06B903', 'BOSCH', 'CA1556'):
            products = [product_id for product_id, _name in self.env['product.product'].name_search(value)]
            self.assertEqual(products, [self.part.id], value)
            templates = [template_id for template_id, _name in self.env['product.template'].name_search(value)]
            self.assertEqual(templates, [self.part.product_tmpl_id.id], value)
        self.assertEqual(self.env['product.product'].search([('display_name', 'ilike', '06B903')]), self.part)
        self.assertNotIn(self.part, self.env['product.product'].search([('display_name', 'not ilike', '06B903')]))
        self.assertIn(self.other, self.env['product.product'].search([('display_name', 'not ilike', '06B903')]))

    def test_chassis_warning(self):
        """ A warning, not an error, when another product has the chassis. """
        with Form(self.env['product.template']) as form:
            form.name = 'Search Car'
            # The CAT tab is shown with its scrap type
            form.scrap_unbuild_type = 'main'
            with self.assertLogs('odoo.tests.form', level='WARNING') as logs:
                form.chassis = 'WVWZZZ1JZ3W386752'
            self.assertIn('Search Alternator', logs.output[0])
        self.assertEqual(form.record.chassis, 'WVWZZZ1JZ3W386752')


@tagged('post_install', '-at_install')
class TestScrapVehicles(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.supplier = cls.env['res.partner'].create({'name': 'CAT Supplier'})
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'CAT Brand'})
        cls.model = cls.env['fleet.vehicle.model'].create({'name': 'CAT Model', 'brand_id': brand.id})
        cls.template = cls.env['product.product'].create({
            'name': 'CAT Vehicle', 'type': 'consu', 'is_storable': True, 'tracking': 'serial',
            'is_template': True, 'default_code': 'VEH', 'supplier_taxes_id': [Command.clear()],
            'vehicle_model_id': cls.model.id, 'ref_oem': 'OEM-1',
        })
        cls.other = cls.env['product.product'].create({
            'name': 'CAT Not a template', 'type': 'consu', 'is_storable': True, 'tracking': 'serial',
        })
        Sequence = cls.env['ir.sequence']
        cls.main_sequence = Sequence.create({'name': 'To dismantle', 'prefix': 'DES', 'padding': 4, 'implementation': 'no_gap'})
        cls.refurbish_sequence = Sequence.create({'name': 'To sell', 'prefix': 'CV', 'padding': 4, 'implementation': 'no_gap'})
        cls.company.write({
            'scrap_main_sequence_id': cls.main_sequence.id,
            'scrap_refurbish_sequence_id': cls.refurbish_sequence.id,
        })

    def _buy(self, unbuild_type, plates, product=None, price=1000.0):
        """ A purchase of vehicles, one per line with its plate, confirmed. """
        order = self.env['purchase.order'].create({
            'partner_id': self.supplier.id,
            'unbuild_type': unbuild_type,
            'order_line': [Command.create({
                'product_id': (product or self.template).id, 'product_qty': 1, 'price_unit': price,
                'scrap_lot_name': plate,
            }) for plate in plates],
        })
        order.button_confirm()
        return order

    def _receive(self, order):
        picking = order.picking_ids.filtered(lambda picking: picking.state != 'cancel')
        picking.move_ids.picked = True
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        return picking.move_line_ids.lot_id.sorted('id')

    def test_defaults(self):
        """ Analytic accounting is enabled, and the company has the plans and the locations of
        the module. """
        implied = self.env.ref('base.group_user').all_implied_ids
        self.assertIn(self.env.ref('analytic.group_analytic_accounting'), implied)
        self.assertIn(self.env.ref('stock.group_stock_multi_locations'), implied)
        self.assertEqual(self.company.scrap_main_analytic_plan_id, self.env.ref('scrap_base.analytic_plan_scrap_main'))
        self.assertEqual(self.company.scrap_refurbish_analytic_plan_id, self.env.ref('scrap_base.analytic_plan_scrap_refurbish'))
        stock = self.env['stock.warehouse'].search([('company_id', '=', self.company.id)], limit=1).lot_stock_id
        self.assertEqual(self.company.scrap_main_location_id.name, 'Para desguazar')
        self.assertEqual(self.company.scrap_refurbish_location_id.name, 'Compra / Venta')
        self.assertEqual((self.company.scrap_main_location_id | self.company.scrap_refurbish_location_id).location_id, stock)
        self.assertEqual(self.company.scrap_waste_location_id.name, 'Zona de desecho')
        self.assertEqual(self.company.scrap_waste_location_id.location_id, stock)

    def test_new_company(self):
        company = self.env['res.company'].create({'name': 'CAT New Company'})
        self.assertTrue(company.scrap_main_analytic_plan_id)
        self.assertEqual(company.scrap_main_location_id.company_id, company)
        self.assertEqual(company.scrap_refurbish_location_id.company_id, company)
        self.assertEqual(company.scrap_waste_location_id.company_id, company)

    def test_vehicle_to_dismantle(self):
        order = self._buy('main', ['1111 cat', '2222CAT'], price=1500.0)
        lines = order.order_line
        vehicles = lines.product_id
        self.assertEqual(len(vehicles), 2)
        self.assertNotIn(self.template, vehicles)
        first, second = lines
        vehicle = first.product_id
        self.assertEqual(vehicle.name, 'CAT Vehicle 1111CAT')
        self.assertEqual(vehicle.scrap_lot_name, '1111CAT')
        self.assertFalse(vehicle.plate, "Not the license plate")
        self.assertEqual(vehicle.vehicle_model_id, self.model)
        self.assertEqual(vehicle.ref_oem, 'OEM-1')
        self.assertFalse(vehicle.is_template)
        self.assertFalse(vehicle.default_code)
        self.assertEqual(vehicle.scrap_template_id, self.template.product_tmpl_id)
        self.assertEqual(vehicle.tracking, 'serial')
        self.assertEqual(vehicle.standard_price, 1500.0)
        self.assertEqual(first.price_unit, 1500.0)
        account = vehicle.scrap_analytic_account_id
        self.assertEqual(account.name, '1111CAT')
        self.assertEqual(account.plan_id, self.company.scrap_main_analytic_plan_id)
        self.assertEqual(first.analytic_distribution, {str(account.id): 100})
        location = vehicle.scrap_location_id
        self.assertEqual(location.name, '1111CAT')
        self.assertEqual(location.location_id, self.company.scrap_main_location_id)
        self.assertEqual(second.product_id.scrap_location_id.name, '2222CAT')
        # The receipt takes each vehicle to its location, with its plate as serial number
        self.assertEqual(len(order.picking_ids), 1)
        move_line = order.picking_ids.move_line_ids.filtered(lambda move_line: move_line.product_id == vehicle)
        self.assertEqual(move_line.location_dest_id, location)
        self.assertEqual(move_line.lot_name, '1111CAT')
        lots = self._receive(order)
        self.assertEqual(lots.mapped('name'), ['1111CAT', '2222CAT'])
        self.assertEqual(lots.product_id, vehicles)
        self.assertEqual(lots.mapped('ref'), ['DES0001', 'DES0002'])
        self.assertEqual(vehicle.default_code, 'DES0001')
        self.assertEqual(self.env['stock.quant']._get_available_quantity(vehicle, location), 1)
        # The bill goes to the analytic account of each vehicle
        order.action_create_invoice()
        bill_line = order.invoice_ids.invoice_line_ids.filtered(lambda line: line.product_id == vehicle)
        self.assertEqual(bill_line.analytic_distribution, {str(account.id): 100})
        # And so does any other invoice of the vehicle
        self.assertEqual(
            self.env['account.analytic.distribution.model']._get_distribution({
                'product_id': vehicle.id, 'company_id': self.company.id}),
            {str(account.id): 100})

    def test_vehicle_to_sell(self):
        order = self._buy('refurbish', ['3333CAT'])
        vehicle = order.order_line.product_id
        self.assertEqual(vehicle.scrap_analytic_account_id.plan_id, self.company.scrap_refurbish_analytic_plan_id)
        self.assertEqual(vehicle.scrap_location_id.location_id, self.company.scrap_refurbish_location_id)
        self.assertEqual(self._receive(order).ref, 'CV0001')

    def test_not_vehicles(self):
        """ Without a kind of entry of vehicles, or for a product that isn't a scrap template,
        the product isn't copied and no reference is given. """
        for unbuild_type in (False, 'subproduct', 'other'):
            order = self._buy(unbuild_type, [f'{unbuild_type}CAT'])
            self.assertEqual(order.order_line.product_id, self.template)
        order = self._buy('main', ['4444CAT'], product=self.other)
        self.assertEqual(order.order_line.product_id, self.other)
        self.assertFalse(self._receive(order).ref)
        self.assertEqual(self.main_sequence.number_next_actual, 1, "No number used")

    def test_no_sequence(self):
        self.company.scrap_main_sequence_id = False
        order = self._buy('main', ['5555CAT'])
        self.assertFalse(self._receive(order).ref)
        self.assertFalse(order.order_line.product_id.default_code)

    def test_checks(self):
        with self.assertRaisesRegex(UserError, 'license plate'):
            self._buy('main', [False])
        with self.assertRaisesRegex(UserError, 'more than one line'):
            self._buy('main', ['6666CAT', '6666-cat'])
        order = self.env['purchase.order'].create({
            'partner_id': self.supplier.id, 'unbuild_type': 'main',
            'order_line': [Command.create({'product_id': self.template.id, 'product_qty': 2, 'scrap_lot_name': '7777CAT'})],
        })
        with self.assertRaisesRegex(UserError, 'line of its own'):
            order.button_confirm()
        self._buy('main', ['8888CAT'])
        with self.assertRaisesRegex(UserError, 'already a vehicle'):
            self._buy('refurbish', ['8888CAT'])
        self.company.scrap_main_location_id = False
        with self.assertRaisesRegex(UserError, 'CAT tab'):
            self._buy('main', ['9999CAT'])

    def test_cancel(self):
        """ A cancelled purchase gives the plates back, and can be bought again. """
        order = self._buy('main', ['1212CAT'])
        vehicle = order.order_line.product_id
        order.button_cancel()
        self.assertEqual(order.order_line.product_id, self.template)
        self.assertEqual(order.order_line.scrap_lot_name, '1212CAT')
        self.assertFalse(vehicle.active)
        self.assertFalse(vehicle.scrap_location_id.active)
        self.assertFalse(vehicle.scrap_analytic_account_id.active)
        order.button_draft()
        order.button_confirm()
        self.assertNotEqual(order.order_line.product_id, self.template)
        self.assertEqual(self._receive(order).name, '1212CAT')

    def test_deadlines(self):
        """ A vehicle to dismantle is discharged when received; its legal limits follow the
        days of the company, and the warehouse users mark it as done. """
        self.company.write({'decontamination_days': 10, 'scrap_days': 30})
        order = self._buy('main', ['1313CAT', '1414CAT'])
        first, second = order.order_line.product_id.product_tmpl_id
        self.assertEqual(first.scrap_unbuild_type, 'main')
        self.assertFalse(first.discharge_date, "Not received yet")
        self._receive(order)
        today = fields.Date.context_today(first)
        self.assertEqual(first.discharge_date, today)
        self.assertEqual(first.decontamination_limit_date, today + timedelta(days=10))
        self.assertEqual(first.scrap_limit_date, today + timedelta(days=30))
        self.assertEqual(first.decontamination_days_left, 10)
        self.company.decontamination_days = 5
        self.assertEqual(first.decontamination_limit_date, today + timedelta(days=5))

        worker = new_test_user(self.env, login='cat_worker', groups='stock.group_stock_user')
        self.assertFalse(first.with_user(worker).has_access('write'), "The warehouse users can't change products")
        with self.assertRaisesRegex(ValidationError, 'decontaminated before'):
            first.with_user(worker).action_scrap_dismantled()
        first.with_user(worker).action_scrap_decontaminated()
        self.assertEqual(first.decontamination_date, today)
        first.with_user(worker).action_scrap_dismantled()
        self.assertEqual(first.scrap_date, today)

        # On another date
        second.with_user(worker)._scrap_write_cat_dates({'decontamination_date': today + timedelta(days=1)})
        self.assertEqual(second.decontamination_date, today + timedelta(days=1))
        with self.assertRaisesRegex(ValidationError, 'before its discharge'):
            second.decontamination_date = today - timedelta(days=1)

        outsider = new_test_user(self.env, login='cat_outsider', groups='base.group_user')
        with self.assertRaises(AccessError):
            second.with_user(outsider).action_scrap_dismantled()

    def test_no_deadlines(self):
        """ Only the vehicles to dismantle, with the days set in the company. """
        self.company.write({'decontamination_days': 0, 'scrap_days': 0})
        order = self._buy('refurbish', ['1515CAT'])
        self._receive(order)
        self.assertFalse(order.order_line.product_id.discharge_date)
        order = self._buy('main', ['1616CAT'])
        self._receive(order)
        vehicle = order.order_line.product_id
        self.assertTrue(vehicle.discharge_date)
        self.assertFalse(vehicle.decontamination_limit_date, "No days in the company")

    def test_complete_vehicle(self):
        """ A vehicle created by hand, with its template, scrap type and license plate, gets its
        analytic account, its location and its distribution with the button, and is received
        and discharged as a bought one. """
        template = self.env['product.template'].create({
            'name': 'CAT Hand Vehicle', 'type': 'consu', 'is_storable': True, 'tracking': 'serial',
            'scrap_template_id': self.template.product_tmpl_id.id, 'scrap_lot_name': '17 17-cat',
        })
        self.assertEqual(template.scrap_lot_name, '1717CAT')
        with self.assertRaisesRegex(UserError, 'scrap type'):
            template.action_scrap_complete_vehicle()
        template.scrap_unbuild_type = 'main'
        template.product_variant_id.action_scrap_complete_vehicle()
        self.assertEqual(template.company_id, self.company)
        account = template.scrap_analytic_account_id
        self.assertEqual(account.name, '1717CAT')
        self.assertEqual(account.plan_id, self.company.scrap_main_analytic_plan_id)
        self.assertEqual(template.scrap_location_id.location_id, self.company.scrap_main_location_id)
        Distribution = self.env['account.analytic.distribution.model']
        self.assertEqual(
            Distribution._get_distribution({'product_id': template.product_variant_id.id, 'company_id': self.company.id}),
            {str(account.id): 100})
        # Again, nothing more
        template.action_scrap_complete_vehicle()
        self.assertEqual(Distribution.search_count([('product_id', '=', template.product_variant_id.id)]), 1)
        self.assertEqual(template.scrap_analytic_account_id, account)

        # Bought without scrap type, it goes to its location with its plate and is discharged
        order = self._buy(False, [False], product=template.product_variant_id)
        self.assertEqual(order.order_line.product_id, template.product_variant_id)
        self.assertEqual(order.picking_ids.move_line_ids.location_dest_id, template.scrap_location_id)
        self.assertEqual(self._receive(order).name, '1717CAT')
        self.assertEqual(template.discharge_date, fields.Date.context_today(template))

        # Its plate can't be bought again, nor given to another vehicle
        with self.assertRaisesRegex(UserError, 'already a vehicle'):
            self._buy('main', ['1717CAT'])
        other = template.copy({'scrap_template_id': self.template.product_tmpl_id.id, 'scrap_unbuild_type': 'main', 'scrap_lot_name': '1717CAT'})
        with self.assertRaisesRegex(UserError, 'already a vehicle'):
            other.action_scrap_complete_vehicle()

    def test_boms(self):
        """ The bills of materials of the scrap template, with their operations, are copied for
        each vehicle, also for one completed by hand. """
        Product = self.env['product.product']
        wheel = Product.create({'name': 'CAT Wheel', 'type': 'consu', 'is_storable': True})
        engine = Product.create({'name': 'CAT Engine', 'type': 'consu', 'is_storable': True})
        workcenter = self.env['mrp.workcenter'].create({'name': 'CAT Dismantling'})
        bom = self.env['mrp.bom'].create({
            'product_tmpl_id': self.template.product_tmpl_id.id,
            'code': 'Dismantle',
            'operation_ids': [Command.create({'name': 'Take to pieces', 'workcenter_id': workcenter.id})],
            'bom_line_ids': [
                Command.create({'product_id': wheel.id, 'product_qty': 4}),
                Command.create({'product_id': engine.id, 'product_qty': 1}),
            ],
        })
        bom.bom_line_ids[1].operation_id = bom.operation_ids
        self.assertTrue(self.env.user.has_group('mrp.group_mrp_routings'))

        vehicle = self._buy('main', ['1818CAT']).order_line.product_id.product_tmpl_id
        copy = vehicle.bom_ids
        self.assertEqual(len(copy), 1)
        self.assertNotEqual(copy, bom)
        self.assertEqual(copy.code, 'Dismantle')
        self.assertEqual(copy.bom_line_ids.mapped('product_qty'), [4, 1])
        self.assertEqual(copy.bom_line_ids.product_id, wheel | engine)
        self.assertEqual(copy.operation_ids.name, 'Take to pieces')
        self.assertEqual(copy.bom_line_ids[1].operation_id, copy.operation_ids)
        self.assertEqual(bom.product_tmpl_id, self.template.product_tmpl_id, "The template keeps its own")

        by_hand = self.env['product.template'].create({
            'name': 'CAT Hand BoM', 'type': 'consu', 'is_storable': True, 'tracking': 'serial',
            'scrap_template_id': self.template.product_tmpl_id.id, 'scrap_unbuild_type': 'main',
            'scrap_lot_name': '1919CAT',
        })
        by_hand.action_scrap_complete_vehicle()
        self.assertEqual(by_hand.bom_ids.bom_line_ids.product_id, wheel | engine)
        by_hand.action_scrap_complete_vehicle()
        self.assertEqual(len(by_hand.bom_ids), 1, "Not copied again")

    def _vehicle_to_dismantle(self, plate):
        """ A vehicle received and decontaminated, with a bill of materials of 4 wheels, an
        engine and a battery tracked by lot. """
        Product = self.env['product.product']
        self.wheel = Product.create({'name': 'CAT Wheel', 'type': 'consu', 'is_storable': True})
        self.engine = Product.create({'name': 'CAT Engine', 'type': 'consu', 'is_storable': True})
        self.battery = Product.create({'name': 'CAT Battery', 'type': 'consu', 'is_storable': True, 'tracking': 'lot'})
        self.env['mrp.bom'].create({
            'product_tmpl_id': self.template.product_tmpl_id.id,
            'bom_line_ids': [
                Command.create({'product_id': self.wheel.id, 'product_qty': 4}),
                Command.create({'product_id': self.engine.id, 'product_qty': 1}),
                Command.create({'product_id': self.battery.id, 'product_qty': 1}),
            ],
        })
        order = self._buy('main', [plate])
        self._receive(order)
        vehicle = order.order_line.product_id.product_tmpl_id
        vehicle.decontamination_date = vehicle.discharge_date
        return vehicle

    def test_dismantle(self):
        vehicle = self._vehicle_to_dismantle('2020CAT')
        wheels, engine, battery = vehicle.bom_ids.bom_line_ids
        worker = new_test_user(self.env, login='cat_dismantler', groups='stock.group_stock_user')
        vehicle = vehicle.with_user(worker)
        self.assertEqual(vehicle._scrap_dismantle_pending_lines(), wheels | engine | battery)

        # A wheel in good condition, into the location of the vehicle, by a warehouse user
        part = vehicle._scrap_dismantle(wheels, 1, 'dismantled', 'good')
        self.assertEqual(part.location_dest_id, vehicle.scrap_location_id)
        self.assertEqual(part.move_id.state, 'done')
        self.assertEqual(part.move_id.location_id.usage, 'production')
        self.assertEqual(self.wheel.with_context(location=vehicle.scrap_location_id.id).qty_available, 1)
        self.assertEqual(wheels.product_qty, 3, "Decreased: 3 left to dismantle")
        self.assertEqual(part.user_id, worker)

        # Into another location; the battery gets a lot after the reference of the vehicle
        stock = self.env['stock.warehouse'].search([('company_id', '=', self.company.id)], limit=1).lot_stock_id
        part = vehicle._scrap_dismantle(battery, 1, 'dismantled', 'excellent', stock)
        self.assertEqual(part.move_id.location_dest_id, stock)
        self.assertTrue(part.move_id.move_line_ids.lot_id.name.startswith(vehicle.default_code))
        self.assertEqual(battery.product_qty, 0)
        self.assertNotIn(battery, vehicle._scrap_dismantle_pending_lines())

        # Discarded: to the scrap location, without condition
        part = vehicle._scrap_dismantle(engine, 1, 'discarded', 'good')
        self.assertFalse(part.condition)
        self.assertEqual(part.move_id.location_dest_id, self.company.scrap_location_id)
        self.assertEqual(self.engine.qty_available, 0)

        with self.assertRaises(UserError):
            vehicle._scrap_dismantle(wheels, 4, 'missing')
        with self.assertRaises(UserError):
            vehicle._scrap_dismantle(wheels, 1, 'dismantled')
        with self.assertRaises(ValidationError):
            vehicle._scrap_dismantle(wheels, 1, 'lost')
        self.assertFalse(vehicle.scrap_date)

        # The rest are missing: no move, and nothing left, so it is dismantled today
        part = vehicle._scrap_dismantle(wheels, 3, 'missing')
        self.assertFalse(part.move_id)
        self.assertEqual(vehicle.scrap_date, fields.Date.context_today(vehicle))
        self.assertEqual(len(vehicle.scrap_dismantle_line_ids), 4)
        with self.assertRaises(UserError):
            vehicle._scrap_dismantle(wheels, 1, 'missing')

    def test_dismantle_checks(self):
        vehicle = self._vehicle_to_dismantle('2121CAT')
        wheels = vehicle.bom_ids.bom_line_ids[0]
        vehicle.decontamination_date = False
        with self.assertRaises(UserError):
            vehicle._scrap_dismantle(wheels, 1, 'missing')
        vehicle.decontamination_date = vehicle.discharge_date
        other = self._vehicle_to_dismantle('2222CAT')
        with self.assertRaises(ValidationError):
            vehicle._scrap_dismantle(other.bom_ids.bom_line_ids[0], 1, 'missing')
        customers = self.env.ref('stock.stock_location_customers')
        with self.assertRaises(UserError):
            vehicle._scrap_dismantle(wheels, 1, 'dismantled', 'good', customers)
        outsider = new_test_user(self.env, login='cat_no_stock', groups='base.group_user')
        with self.assertRaises(AccessError):
            vehicle.with_user(outsider)._scrap_dismantle(wheels, 1, 'missing')

    def test_dismantle_template(self):
        """ A component that is a scrap template becomes, by unit, a product of its own. """
        Product = self.env['product.product']
        head = Product.create({'name': 'CAT Head', 'type': 'consu', 'is_storable': True})
        engine = Product.create({
            'name': 'CAT Used Engine', 'type': 'consu', 'is_storable': True, 'tracking': 'serial',
            'is_template': True, 'scrap_unbuild_type': 'subproduct', 'purchase_ok': False, 'sale_ok': False,
        })
        self.env['mrp.bom'].create({
            'product_tmpl_id': engine.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': head.id, 'product_qty': 1})],
        })
        self.env['mrp.bom'].create({
            'product_tmpl_id': self.template.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': engine.id, 'product_qty': 2})],
        })
        order = self._buy('main', ['2323CAT'])
        self._receive(order)
        vehicle = order.order_line.product_id.product_tmpl_id
        vehicle.decontamination_date = vehicle.discharge_date
        line = vehicle.bom_ids.bom_line_ids
        with self.assertRaises(UserError):
            vehicle._scrap_dismantle(line, 1.5, 'dismantled', 'good')

        parts = vehicle._scrap_dismantle(line, 2, 'dismantled', 'functional')
        self.assertEqual(len(parts), 2)
        products = parts.product_id
        self.assertEqual(len(products), 2, "One product per engine")
        self.assertNotIn(engine, products)
        for product in products:
            self.assertEqual(product.name, f"CAT Used Engine {vehicle.default_code}")
            self.assertFalse(product.is_template)
            self.assertTrue(product.sale_ok, "Saleable, although the template isn't")
            self.assertEqual(product.scrap_template_id, engine.product_tmpl_id)
            self.assertEqual(product.scrap_unbuild_type, 'subproduct')
            self.assertEqual(product.vehicle_model_id, self.model)
            self.assertEqual(product.bom_ids.bom_line_ids.product_id, head, "Its bill of materials, to dismantle it later")
            self.assertEqual(product.with_context(location=vehicle.scrap_location_id.id).qty_available, 1)
        self.assertEqual(parts.mapped('quantity'), [1, 1])
        self.assertEqual(len(parts.move_id.move_line_ids.lot_id), 2)
        self.assertEqual(engine.qty_available, 0, "The template has no stock")
        self.assertEqual(vehicle.scrap_date, fields.Date.context_today(vehicle))

    def test_undo_dismantle(self):
        """ A part marked by mistake is undone: its stock goes back and it is again to dismantle. """
        vehicle = self._vehicle_to_dismantle('2424CAT')
        wheels, engine, battery = vehicle.bom_ids.bom_line_ids
        worker = new_test_user(self.env, login='cat_undoer', groups='stock.group_stock_user')
        vehicle = vehicle.with_user(worker)
        location = vehicle.scrap_location_id

        part = vehicle._scrap_dismantle(wheels, 2, 'dismantled', 'good')
        vehicle._scrap_undo_dismantle(part)
        self.assertFalse(part.exists())
        self.assertEqual(wheels.product_qty, 4)
        self.assertEqual(self.wheel.with_context(location=location.id).qty_available, 0)

        # A discarded one, back from the scrap location; a lot, back with it
        vehicle._scrap_undo_dismantle(vehicle._scrap_dismantle(engine, 1, 'discarded'))
        part = vehicle._scrap_dismantle(battery, 1, 'dismantled', 'excellent')
        lot = part.move_id.move_line_ids.lot_id
        vehicle._scrap_undo_dismantle(part)
        self.assertEqual(self.env['stock.quant']._get_available_quantity(self.battery, location, lot_id=lot, strict=True), 0)
        self.assertEqual((engine.product_qty, battery.product_qty), (1, 1))

        # Not anymore where it entered: it can't be undone
        part = vehicle._scrap_dismantle(wheels, 1, 'dismantled', 'good')
        self.env['stock.quant']._update_available_quantity(self.wheel, location, -1)
        with self.assertRaises(UserError):
            vehicle._scrap_undo_dismantle(part)
        self.assertTrue(part.exists())

        # The last one undone: the vehicle isn't dismantled anymore
        vehicle._scrap_dismantle(wheels, 3, 'missing')
        vehicle._scrap_dismantle(engine, 1, 'missing')
        last = vehicle._scrap_dismantle(battery, 1, 'missing')
        self.assertTrue(vehicle.scrap_date)
        vehicle._scrap_undo_dismantle(last)
        self.assertFalse(vehicle.scrap_date)
        self.assertEqual(battery.product_qty, 1)

        other = self._vehicle_to_dismantle('2525CAT')
        with self.assertRaises(ValidationError):
            other._scrap_undo_dismantle(part)

    def test_undo_dismantle_template(self):
        """ The product made of a scrap template is archived. """
        engine = self.env['product.product'].create({
            'name': 'CAT Undo Engine', 'type': 'consu', 'is_storable': True, 'is_template': True,
            'scrap_unbuild_type': 'subproduct',
        })
        self.env['mrp.bom'].create({
            'product_tmpl_id': self.template.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': engine.id, 'product_qty': 1})],
        })
        order = self._buy('main', ['2626CAT'])
        self._receive(order)
        vehicle = order.order_line.product_id.product_tmpl_id
        vehicle.decontamination_date = vehicle.discharge_date
        part = vehicle._scrap_dismantle(vehicle.bom_ids.bom_line_ids, 1, 'dismantled', 'good')
        copy = part.product_id
        self.assertNotEqual(copy, engine)
        vehicle._scrap_undo_dismantle(part)
        self.assertFalse(copy.active)
        self.assertEqual(copy.qty_available, 0)
        self.assertTrue(engine.active)
        self.assertEqual(vehicle.bom_ids.bom_line_ids.product_id, engine)
        self.assertFalse(vehicle.scrap_date)

    def test_dismantle_subproduct(self):
        """ A subproduct (an engine) is dismantled later, without decontaminating it; its
        parts, also the ones of a subproduct of it (a cylinder head), keep the vehicle as their
        origin. """
        Product = self.env['product.product']
        valve = Product.create({'name': 'CAT Valve', 'type': 'consu', 'is_storable': True})
        head = Product.create({
            'name': 'CAT Cylinder Head', 'type': 'consu', 'is_storable': True,
            'is_template': True, 'scrap_unbuild_type': 'subproduct',
        })
        engine = Product.create({
            'name': 'CAT Sub Engine', 'type': 'consu', 'is_storable': True,
            'is_template': True, 'scrap_unbuild_type': 'subproduct',
        })
        self.env['mrp.bom'].create({
            'product_tmpl_id': head.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': valve.id, 'product_qty': 8})],
        })
        self.env['mrp.bom'].create({
            'product_tmpl_id': engine.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': head.id, 'product_qty': 1})],
        })
        self.env['mrp.bom'].create({
            'product_tmpl_id': self.template.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': engine.id, 'product_qty': 1})],
        })
        order = self._buy('main', ['2929CAT'])
        self._receive(order)
        vehicle = order.order_line.product_id.product_tmpl_id
        vehicle.decontamination_date = vehicle.discharge_date
        worker = new_test_user(self.env, login='cat_sub_dismantler', groups='stock.group_stock_user')

        first = vehicle.with_user(worker)._scrap_dismantle(vehicle.bom_ids.bom_line_ids, 1, 'dismantled', 'good')
        sub_engine = first.product_id.product_tmpl_id
        self.assertEqual(sub_engine.scrap_origin_id, vehicle)
        self.assertEqual(sub_engine.scrap_location_id, vehicle.scrap_location_id)
        self.assertEqual(sub_engine.scrap_analytic_account_id, vehicle.scrap_analytic_account_id)
        self.assertTrue(self.env['account.analytic.distribution.model'].search_count([
            ('product_id', '=', sub_engine.product_variant_id.id)]), "Its sales go to the vehicle")
        self.assertTrue(sub_engine._scrap_is_subproduct())
        self.assertFalse(vehicle.scrap_origin_id)
        self.assertEqual(first.origin_id, vehicle)

        # The engine, dismantled: its cylinder head is a subproduct of the vehicle too
        sub_engine = sub_engine.with_user(worker)
        second = sub_engine._scrap_dismantle(sub_engine.bom_ids.bom_line_ids, 1, 'dismantled', 'functional')
        sub_head = second.product_id.product_tmpl_id
        self.assertEqual(sub_head.scrap_origin_id, vehicle, "The vehicle, not the engine")
        self.assertEqual(sub_head.name, f"CAT Cylinder Head {vehicle.default_code}")
        self.assertEqual(sub_engine.scrap_date, fields.Date.context_today(sub_engine), "Nothing left: dismantled")
        self.assertFalse(sub_engine.decontamination_date)

        # Its valves too, into the location of the vehicle
        sub_head = sub_head.with_user(worker)
        third = sub_head._scrap_dismantle(sub_head.bom_ids.bom_line_ids, 5, 'dismantled', 'good')
        self.assertEqual(third.location_dest_id, vehicle.scrap_location_id)
        self.assertEqual((third.vehicle_id, third.origin_id), (sub_head, vehicle))
        self.assertEqual(vehicle.scrap_origin_line_ids, first | second | third)
        self.assertEqual(vehicle.scrap_dismantle_line_ids, first)

        # The engine can't be undone while its parts are marked
        with self.assertRaises(UserError):
            sub_engine._scrap_undo_dismantle(second)
        with self.assertRaises(UserError):
            vehicle.with_user(worker)._scrap_undo_dismantle(first)
        sub_head._scrap_undo_dismantle(third)
        sub_engine._scrap_undo_dismantle(second)
        self.assertFalse(sub_head.active)
        self.assertFalse(sub_engine.scrap_date)
        vehicle.with_user(worker)._scrap_undo_dismantle(first)
        self.assertFalse(sub_engine.active)
        self.assertFalse(self.env['account.analytic.distribution.model'].search_count([
            ('product_id', '=', sub_engine.product_variant_id.id)]))

        # Not a subproduct to dismantle: a template, or archived
        with self.assertRaises(UserError):
            engine.product_tmpl_id._scrap_dismantle(engine.bom_ids.bom_line_ids, 1, 'missing')
        with self.assertRaises(UserError):
            sub_engine._scrap_dismantle(sub_engine.bom_ids.bom_line_ids, 1, 'missing')

    def test_dismantle_bought_subproduct(self):
        """ An engine bought to dismantle is still a subproduct, without origin: it is
        dismantled once received, without decontaminating it, and it is the origin of its own
        subproducts. """
        Product = self.env['product.product']
        valve = Product.create({'name': 'CAT Bought Valve', 'type': 'consu', 'is_storable': True})
        head = Product.create({
            'name': 'CAT Bought Head', 'type': 'consu', 'is_storable': True,
            'is_template': True, 'scrap_unbuild_type': 'subproduct',
        })
        engine = Product.create({
            'name': 'CAT Bought Engine', 'type': 'consu', 'is_storable': True, 'tracking': 'serial',
            'is_template': True, 'scrap_unbuild_type': 'subproduct', 'supplier_taxes_id': [Command.clear()],
        })
        self.env['mrp.bom'].create({
            'product_tmpl_id': head.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': valve.id, 'product_qty': 8})],
        })
        self.env['mrp.bom'].create({
            'product_tmpl_id': engine.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': head.id, 'product_qty': 1})],
        })
        order = self._buy('main', ['MOTOR01'], product=engine)
        bought = order.order_line.product_id.product_tmpl_id
        self.assertNotEqual(bought, engine.product_tmpl_id)
        self.assertEqual(bought.scrap_unbuild_type, 'subproduct')
        self.assertFalse(bought.scrap_origin_id)
        self.assertTrue(bought._scrap_is_subproduct())
        with self.assertRaises(UserError):
            bought._scrap_dismantle(bought.bom_ids.bom_line_ids, 1, 'missing')

        self._receive(order)
        self.assertTrue(bought.discharge_date)
        self.assertFalse(bought.decontamination_limit_date or bought.scrap_limit_date, "Without legal deadlines")
        first = bought._scrap_dismantle(bought.bom_ids.bom_line_ids, 1, 'dismantled', 'good')
        sub_head = first.product_id.product_tmpl_id
        self.assertEqual(sub_head.scrap_origin_id, bought, "The engine bought is the origin")
        self.assertEqual(sub_head.name, f"CAT Bought Head {bought.default_code or 'MOTOR01'}")
        self.assertEqual(sub_head.scrap_location_id, bought.scrap_location_id)
        self.assertEqual(bought.scrap_date, fields.Date.context_today(bought))
        second = sub_head._scrap_dismantle(sub_head.bom_ids.bom_line_ids, 8, 'dismantled', 'functional')
        self.assertEqual(second.origin_id, bought)
        self.assertEqual(bought.scrap_origin_line_ids, first | second)

    def test_decontaminate(self):
        """ The waste taken out while decontaminating, as many times as needed. """
        oil = self.env['product.product'].create({
            'name': 'CAT Oil', 'type': 'consu', 'is_storable': True,
            'uom_id': self.env.ref('uom.product_uom_litre').id,
        })
        other = self.env['product.product'].create({'name': 'CAT Not Waste', 'type': 'consu', 'is_storable': True})
        self.company.scrap_waste_product_ids = oil
        waste_zone = self.company.scrap_waste_location_id
        order = self._buy('main', ['2727CAT'])
        self._receive(order)
        worker = new_test_user(self.env, login='cat_decontaminator', groups='stock.group_stock_user')
        vehicle = order.order_line.product_id.product_tmpl_id.with_user(worker)

        part = vehicle._scrap_decontaminate(oil, 3.5, 'discarded')
        self.assertEqual((part.stage, part.uom_id, part.location_dest_id), ('decontamination', oil.uom_id, waste_zone))
        self.assertEqual(part.move_id.state, 'done')
        vehicle._scrap_decontaminate(oil, 2, 'discarded')
        self.assertEqual(oil.with_context(location=waste_zone.id).qty_available, 5.5, "As many times as needed")
        # Another location than the waste zone (not its parent, which counts it too)
        stock = self.env['stock.location'].create({
            'name': 'CAT Shelf', 'location_id': waste_zone.location_id.id, 'company_id': self.company.id})
        self.assertEqual(vehicle._scrap_decontaminate(oil, 1, 'discarded', stock).move_id.location_dest_id, stock)
        missing = vehicle._scrap_decontaminate(oil, 1, 'missing')
        self.assertFalse(missing.move_id)
        self.assertFalse(vehicle.bom_ids, "Without a bill of materials")

        with self.assertRaises(ValidationError):
            vehicle._scrap_decontaminate(other, 1, 'discarded')
        with self.assertRaises(ValidationError):
            vehicle._scrap_decontaminate(oil, 1, 'dismantled')
        with self.assertRaises(UserError):
            vehicle._scrap_decontaminate(oil, 0, 'discarded')
        with self.assertRaises(UserError):
            vehicle._scrap_decontaminate(oil, 1, 'discarded', self.env.ref('stock.stock_location_customers'))

        # Corrected: its stock goes back and enters again
        vehicle._scrap_update_waste(part, 4, 'discarded', stock)
        self.assertEqual((part.quantity, part.location_dest_id), (4, stock))
        self.assertEqual(oil.with_context(location=waste_zone.id).qty_available, 2)
        self.assertEqual(oil.with_context(location=stock.id).qty_available, 5)
        vehicle._scrap_update_waste(part, 1, 'missing')
        self.assertFalse(part.move_id)
        self.assertEqual(oil.with_context(location=stock.id).qty_available, 1)
        vehicle._scrap_update_waste(part, 3, 'discarded')
        self.assertEqual(part.location_dest_id, waste_zone, "Into the waste zone by default")
        with self.assertRaises(ValidationError):
            vehicle._scrap_update_waste(part, 1, 'dismantled')
        other_vehicle = self._buy('main', ['2828CAT']).order_line.product_id.product_tmpl_id
        with self.assertRaises(ValidationError):
            other_vehicle._scrap_update_waste(part, 1, 'missing')

        # Removed
        vehicle._scrap_undo_dismantle(missing)
        self.assertFalse(missing.exists())

        # Decontaminated: nothing more, neither corrected nor removed
        vehicle._scrap_write_cat_dates({'decontamination_date': vehicle.discharge_date})
        with self.assertRaises(UserError):
            vehicle._scrap_decontaminate(oil, 1, 'discarded')
        with self.assertRaises(UserError):
            vehicle._scrap_update_waste(part, 1, 'discarded')
        with self.assertRaises(UserError):
            vehicle._scrap_undo_dismantle(part)
        self.assertEqual(len(vehicle.scrap_dismantle_line_ids), 3)

    def test_kanban_template_ribbon(self):
        """ The scrap templates, with a ribbon on their card of the kanban view. """
        for model in ('product.template', 'product.product'):
            arch = self.env[model].get_views([(False, 'kanban')])['views']['kanban']['arch']
            self.assertIn('web_ribbon', arch, model)
            self.assertIn('is_template', arch, model)
