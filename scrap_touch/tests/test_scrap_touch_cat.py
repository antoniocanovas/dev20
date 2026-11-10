import uuid
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestScrapTouchCat(TransactionCase):
    """ Decontamination, dismantling and vehicles on the touch screen. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.write({'decontamination_days': 10, 'scrap_days': 30})
        cls.supplier = cls.env['res.partner'].create({'name': 'CAT Touch Supplier'})
        cls.template = cls.env['product.product'].create({
            'name': 'CAT Touch Car', 'type': 'consu', 'is_storable': True, 'tracking': 'serial',
            'is_template': True, 'supplier_taxes_id': [Command.clear()],
        })
        cls.buyer = new_test_user(
            cls.env, login='cat_touch_buyer',
            groups='purchase.group_purchase_user,stock.group_stock_user,stock.group_production_lot')
        cls.worker = new_test_user(cls.env, login='cat_touch_worker', groups='stock.group_stock_user')
        cls.touch = cls.env['scrap.touch'].with_user(cls.worker)
        cls.today = fields.Date.context_today(cls.touch)

        def buy(plates, unbuild_type='main', receive=True):
            result = cls.env['scrap.touch'].with_user(cls.buyer).purchase_entry({
                'uuid': str(uuid.uuid4()), 'partner_id': cls.supplier.id, 'unbuild_type': unbuild_type,
                'lines': [{'product_id': cls.template.id, 'lot_name': plate, 'price_unit': 100.0} for plate in plates],
            }, receive)
            return cls.env['purchase.order'].browse(result['id']).order_line.product_id.product_tmpl_id

        cls.late, cls.soon, cls.decontaminated = buy(['CAT0001', 'CAT0002', 'CAT0003'])
        cls.late.discharge_date = cls.today - timedelta(days=12)
        cls.soon.discharge_date = cls.today - timedelta(days=8)
        cls.decontaminated.write({
            'discharge_date': cls.today - timedelta(days=20),
            'decontamination_date': cls.today - timedelta(days=15),
        })
        cls.to_receive = buy(['CAT0004'], receive=False)
        cls.resale = buy(['CAT0005'], unbuild_type='refurbish')

    def _ids(self, stage, state_filter, query=''):
        mine = (self.late | self.soon | self.decontaminated | self.to_receive | self.resale).ids
        return [vehicle['id'] for vehicle in self.touch.get_vehicles(query, state_filter, stage) if vehicle['id'] in mine]

    def test_screen_data(self):
        data = self.touch.get_screen_data()
        self.assertTrue(data['can_cat'])
        self.assertFalse(data['can_purchase'], "The purchase entries are for the purchase users")
        self.assertGreaterEqual(data['cat_counts']['decontamination']['late'], 1)

    def test_decontamination_list(self):
        """ The vehicles received, the nearest limit first. """
        self.assertEqual(self._ids('decontamination', 'pending'), [self.late.id, self.soon.id])
        self.assertEqual(self._ids('decontamination', 'late'), [self.late.id])
        self.assertEqual(self._ids('decontamination', 'done'), [self.decontaminated.id])
        self.assertEqual(self._ids('decontamination', 'all', 'cat 0002'), [self.soon.id], "By license plate")
        vehicle = self.touch.get_vehicles('CAT0001', 'pending', 'decontamination')[0]
        self.assertEqual(vehicle['decontamination_days_left'], -2)
        self.assertEqual(vehicle['plate'], 'CAT0001')
        with self.assertRaises(ValidationError):
            self.touch.get_vehicles('', 'in_stock', 'decontamination')

    def test_dismantling_list(self):
        self.assertEqual(self._ids('scrap', 'pending'), [self.decontaminated.id])
        self.assertEqual(self._ids('scrap', 'late'), [])

    def test_vehicles_list(self):
        self.assertEqual(set(self._ids('vehicles', 'all')), {
            self.late.id, self.soon.id, self.decontaminated.id, self.to_receive.id, self.resale.id})
        self.assertNotIn(self.to_receive.id, self._ids('vehicles', 'in_stock'))
        self.assertEqual(self._ids('vehicles', 'refurbish'), [self.resale.id])
        self.assertEqual(self._ids('vehicles', 'on_sale'), [self.resale.id], "To sell, in stock")
        summary = self.touch.get_vehicle(self.resale.id)
        self.assertEqual(summary['plate'], 'CAT0005')
        self.assertEqual(summary['partner'], 'CAT Touch Supplier')
        self.assertTrue(summary['location'].endswith('CAT0005'))

    def test_mark(self):
        summary = self.touch.mark_vehicle(self.late.id, 'decontamination')
        self.assertEqual(summary['decontamination_date'], fields.Date.to_string(self.today))
        self.assertEqual(self.late.decontamination_date, self.today)
        with self.assertRaisesRegex(UserError, 'already done'):
            self.touch.mark_vehicle(self.late.id, 'decontamination')
        with self.assertRaisesRegex(UserError, 'decontaminated before'):
            self.touch.mark_vehicle(self.soon.id, 'scrap')
        with self.assertRaisesRegex(UserError, 'later than today'):
            self.touch.mark_vehicle(self.soon.id, 'decontamination', fields.Date.to_string(self.today + timedelta(days=1)))
        yesterday = self.today - timedelta(days=1)
        self.touch.mark_vehicle(self.soon.id, 'decontamination', fields.Date.to_string(yesterday))
        self.assertEqual(self.soon.decontamination_date, yesterday)
        with self.assertRaisesRegex(UserError, 'to dismantle received'):
            self.touch.mark_vehicle(self.resale.id, 'decontamination')
        with self.assertRaisesRegex(UserError, 'to dismantle received'):
            self.touch.mark_vehicle(self.to_receive.id, 'decontamination')

        self.touch.mark_vehicle(self.late.id, 'scrap')
        self.assertEqual(self.late.scrap_date, self.today)
        with self.assertRaisesRegex(UserError, 'undo the dismantling first'):
            self.touch.unmark_vehicle(self.late.id, 'decontamination')
        self.touch.unmark_vehicle(self.late.id, 'scrap')
        self.touch.unmark_vehicle(self.late.id, 'decontamination')
        self.assertFalse(self.late.decontamination_date)

    def test_access(self):
        outsider = new_test_user(self.env, login='cat_touch_outsider', groups='base.group_user')
        with self.assertRaises(Exception):
            self.env['scrap.touch'].with_user(outsider).mark_vehicle(self.late.id, 'decontamination')
        self.assertFalse(self.late.decontamination_date)
        with self.assertRaises(ValidationError):
            self.touch.get_vehicle(self.template.product_tmpl_id.id)

    def test_dismantle(self):
        """ The operator marks the components of the vehicle on the screen. """
        Product = self.env['product.product']
        wheel = Product.create({'name': 'CAT Touch Wheel', 'type': 'consu', 'is_storable': True})
        battery = Product.create({'name': 'CAT Touch Battery', 'type': 'consu', 'is_storable': True})
        vehicle = self.decontaminated
        self.env['mrp.bom'].create({
            'product_tmpl_id': vehicle.id,
            'bom_line_ids': [
                Command.create({'product_id': wheel.id, 'product_qty': 4}),
                Command.create({'product_id': battery.id, 'product_qty': 1}),
            ],
        })
        wheels, battery_line = vehicle.bom_ids.bom_line_ids
        summary = self.touch.get_vehicle(vehicle.id)
        self.assertEqual((summary['pending_parts'], summary['dismantled_parts']), (2, 0))
        data = self.touch.get_dismantle(vehicle.id)
        self.assertEqual([line['id'] for line in data['pending']], [wheels.id, battery_line.id])
        self.assertEqual(data['location_id'], vehicle.scrap_location_id.id)
        locations = self.touch.get_dismantle_locations(vehicle.id)
        self.assertEqual(locations[0]['id'], vehicle.scrap_location_id.id, "Its own location first")
        self.assertTrue(all(self.env['stock.location'].browse(location['id']).usage == 'internal' for location in locations))

        stock = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1).lot_stock_id
        data = self.touch.dismantle_part(vehicle.id, wheels.id, 3, 'dismantled', 'half_life', stock.id)
        self.assertEqual(data['pending'][0]['quantity'], 1)
        self.assertEqual(data['parts'][0]['result'], 'dismantled')
        self.assertEqual(data['parts'][0]['location'], stock.complete_name)
        self.assertEqual(wheel.with_context(location=stock.id).qty_available, 3)
        data = self.touch.dismantle_part(vehicle.id, battery_line.id, 1, 'discarded')
        self.assertEqual(len(data['pending']), 1)
        self.assertFalse(data['scrap_date'])
        for args in ((wheels.id, '1', 'missing'), (wheels.id, True, 'missing'), ('x', 1, 'missing')):
            with self.assertRaises(ValidationError):
                self.touch.dismantle_part(vehicle.id, *args)
        data = self.touch.dismantle_part(vehicle.id, wheels.id, 1, 'missing')
        self.assertFalse(data['pending'])
        self.assertEqual(data['scrap_date'], fields.Date.to_string(self.today), "Nothing left: dismantled")
        with self.assertRaises(UserError):
            self.touch.dismantle_part(vehicle.id, wheels.id, 1, 'missing')

        # Undone by mistake: again to dismantle, and the vehicle isn't dismantled anymore
        part = data['parts'][0]
        self.assertTrue(part['can_undo'])
        data = self.touch.undo_dismantle_part(vehicle.id, part['id'])
        self.assertEqual([line['id'] for line in data['pending']], [wheels.id])
        self.assertFalse(data['scrap_date'])
        with self.assertRaises(UserError):
            self.touch.undo_dismantle_part(vehicle.id, part['id'])

    def test_dismantle_subproduct(self):
        """ The subproducts, in their own list of the dismantling, are dismantled as the
        vehicles; the vehicle shows their parts too. """
        Product = self.env['product.product']
        valve = Product.create({'name': 'CAT Touch Valve', 'type': 'consu', 'is_storable': True})
        engine = Product.create({
            'name': 'CAT Touch Engine', 'type': 'consu', 'is_storable': True,
            'is_template': True, 'scrap_unbuild_type': 'subproduct',
        })
        self.env['mrp.bom'].create({
            'product_tmpl_id': engine.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': valve.id, 'product_qty': 2})],
        })
        vehicle = self.decontaminated
        self.env['mrp.bom'].create({
            'product_tmpl_id': vehicle.id,
            'bom_line_ids': [Command.create({'product_id': engine.id, 'product_qty': 1})],
        })
        data = self.touch.dismantle_part(vehicle.id, vehicle.bom_ids.bom_line_ids.id, 1, 'dismantled', 'good')
        sub_engine = self.env['product.template'].search([('scrap_origin_id', '=', vehicle.id)])
        self.assertEqual(len(sub_engine), 1)

        subproducts = self.touch.get_vehicles('', 'subproduct', 'scrap')
        self.assertIn(sub_engine.id, [item['id'] for item in subproducts])
        self.assertNotIn(vehicle.id, [item['id'] for item in subproducts])
        found = self.touch.get_vehicles('CAT0003', 'subproduct', 'scrap')
        self.assertEqual([item['id'] for item in found], [sub_engine.id], "By the license plate of its vehicle")
        self.assertTrue(found[0]['is_subproduct'])
        self.assertEqual(found[0]['origin_plate'], 'CAT0003')
        self.assertNotIn(sub_engine.id, [item['id'] for item in self.touch.get_vehicles('', 'all', 'scrap')])

        summary = self.touch.get_vehicle(sub_engine.id)
        self.assertEqual(summary['origin'], vehicle.display_name)
        data = self.touch.get_dismantle(sub_engine.id)
        self.assertEqual(data['location_id'], vehicle.scrap_location_id.id)
        line = sub_engine.bom_ids.bom_line_ids
        data = self.touch.dismantle_part(sub_engine.id, line.id, 1, 'dismantled', 'functional')
        self.assertEqual(data['parts'][0]['source'], '', "Its own part")
        self.assertTrue(data['parts'][0]['can_undo'])

        # The vehicle shows the parts of its subproduct, undone from there
        parts = self.touch.get_dismantle(vehicle.id)['parts']
        self.assertEqual(len(parts), 2)
        valve_part = next(part for part in parts if part['product_id'] == valve.id)
        self.assertEqual(valve_part['source'], sub_engine.display_name)
        self.assertFalse(valve_part['can_undo'])
        with self.assertRaises(ValidationError):
            self.touch.undo_dismantle_part(vehicle.id, valve_part['id'])

        # Finished although a valve is left; only dismantled
        with self.assertRaises(UserError):
            self.touch.mark_vehicle(sub_engine.id, 'decontamination')
        summary = self.touch.mark_vehicle(sub_engine.id, 'scrap')
        self.assertEqual(summary['scrap_date'], fields.Date.to_string(self.today))
        summary = self.touch.unmark_vehicle(sub_engine.id, 'scrap')
        self.assertFalse(summary['scrap_date'])

    def test_dismantle_rules(self):
        """ The rules of the dismantling, together: a component that isn't a template only
        increases its stock; a template becomes, by unit, a copy of its own with the origin,
        and leaves the bill of materials, the template without stock; the copy of a template of
        subproducts is a subproduct, in the list of the subproducts to dismantle if it has
        something to dismantle. """
        Product = self.env['product.product']
        wheel = Product.create({'name': 'CAT Rules Wheel', 'type': 'consu', 'is_storable': True})
        valve = Product.create({'name': 'CAT Rules Valve', 'type': 'consu', 'is_storable': True})
        engine = Product.create({
            'name': 'CAT Rules Engine', 'type': 'consu', 'is_storable': True,
            'is_template': True, 'scrap_unbuild_type': 'subproduct',
        })
        door = Product.create({
            'name': 'CAT Rules Door', 'type': 'consu', 'is_storable': True,
            'is_template': True, 'scrap_unbuild_type': 'subproduct',
        })
        self.env['mrp.bom'].create({
            'product_tmpl_id': engine.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': valve.id, 'product_qty': 4})],
        })
        vehicle = self.decontaminated
        self.env['mrp.bom'].create({
            'product_tmpl_id': vehicle.id,
            'bom_line_ids': [
                Command.create({'product_id': wheel.id, 'product_qty': 4}),
                Command.create({'product_id': engine.id, 'product_qty': 2}),
                Command.create({'product_id': door.id, 'product_qty': 1}),
            ],
        })
        wheels, engines, doors = vehicle.bom_ids.bom_line_ids
        location = vehicle.scrap_location_id
        Template = self.env['product.template'].with_context(active_test=False)
        products_before = Template.search_count([])

        # Not a template: its own stock increases, no product is made
        data = self.touch.dismantle_part(vehicle.id, wheels.id, 4, 'dismantled', 'good')
        self.assertEqual(wheel.with_context(location=location.id).qty_available, 4)
        self.assertEqual(Template.search_count([]), products_before, "No copy")
        self.assertEqual(wheels.product_qty, 0)
        self.assertNotIn(wheels.id, [line['id'] for line in data['pending']])

        # A template: a copy by unit, with the origin, one unit of stock each, and the template
        # leaves what is to dismantle, without stock
        data = self.touch.dismantle_part(vehicle.id, engines.id, 2, 'dismantled', 'functional')
        copies = Template.search([('scrap_template_id', '=', engine.product_tmpl_id.id)])
        self.assertEqual(len(copies), 2)
        for copy in copies:
            self.assertEqual(copy.scrap_origin_id, vehicle)
            self.assertEqual(copy.scrap_unbuild_type, 'subproduct', "As its template")
            self.assertFalse(copy.is_template)
            self.assertEqual(copy.product_variant_id.with_context(location=location.id).qty_available, 1)
            self.assertEqual(copy.bom_ids.bom_line_ids.product_id, valve, "Its own bill of materials")
        self.assertEqual(engine.qty_available, 0, "The template has no stock")
        self.assertEqual(engines.product_qty, 0)
        self.assertEqual([line['id'] for line in data['pending']], [doors.id])
        data = self.touch.dismantle_part(vehicle.id, doors.id, 1, 'dismantled', 'good')
        door_copy = Template.search([('scrap_template_id', '=', door.product_tmpl_id.id)])
        self.assertEqual(door_copy.scrap_unbuild_type, 'subproduct')
        self.assertFalse(data['pending'])
        self.assertTrue(data['scrap_date'], "Nothing left: dismantled")

        # The subproducts with something to dismantle are in their list
        listed = [item['id'] for item in self.touch.get_vehicles('', 'subproduct', 'scrap')]
        self.assertTrue(set(copies.ids) <= set(listed))
        self.assertNotIn(door_copy.id, listed, "Without bill of materials, nothing to dismantle")

    def test_bought_subproduct(self):
        """ An engine bought in the entry to dismantle is in the list of the subproducts once
        received, without origin; its subproducts have it as their origin. """
        Product = self.env['product.product']
        valve = Product.create({'name': 'CAT Touch Bought Valve', 'type': 'consu', 'is_storable': True})
        engine = Product.create({
            'name': 'CAT Touch Bought Engine', 'type': 'consu', 'is_storable': True, 'tracking': 'serial',
            'is_template': True, 'scrap_unbuild_type': 'subproduct', 'supplier_taxes_id': [Command.clear()],
        })
        self.env['mrp.bom'].create({
            'product_tmpl_id': engine.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': valve.id, 'product_qty': 2})],
        })

        def buy(plate, receive):
            result = self.env['scrap.touch'].with_user(self.buyer).purchase_entry({
                'uuid': str(uuid.uuid4()), 'partner_id': self.supplier.id, 'unbuild_type': 'main',
                'lines': [{'product_id': engine.id, 'lot_name': plate, 'price_unit': 50.0}],
            }, receive)
            return self.env['purchase.order'].browse(result['id']).order_line.product_id.product_tmpl_id

        waiting = buy('MOTOR02', False)
        bought = buy('MOTOR01', True)
        ids = [item['id'] for item in self.touch.get_vehicles('', 'subproduct', 'scrap')]
        self.assertIn(bought.id, ids)
        self.assertNotIn(waiting.id, ids, "Not received yet")
        self.assertNotIn(bought.id, [item['id'] for item in self.touch.get_vehicles('', 'all', 'decontamination')])
        with self.assertRaises(UserError):
            self.touch.mark_vehicle(waiting.id, 'scrap')

        summary = self.touch.get_vehicle(bought.id)
        self.assertTrue(summary['is_subproduct'])
        self.assertEqual((summary['origin'], summary['plate']), ('', 'MOTOR01'))
        data = self.touch.dismantle_part(bought.id, bought.bom_ids.bom_line_ids.id, 2, 'dismantled', 'good')
        self.assertEqual(data['scrap_date'], fields.Date.to_string(self.today))
        self.assertEqual(bought.scrap_origin_line_ids.product_id, valve)

    def test_decontaminate(self):
        """ The operator takes the waste out of the vehicle on the screen. """
        oil = self.env['product.product'].create({
            'name': 'CAT Touch Oil', 'type': 'consu', 'is_storable': True,
            'uom_id': self.env.ref('uom.product_uom_litre').id,
        })
        self.env.company.scrap_waste_product_ids = oil
        vehicle = self.late
        data = self.touch.get_decontamination(vehicle.id)
        self.assertEqual(data['stage'], 'decontamination')
        self.assertEqual([line['product_id'] for line in data['pending']], [oil.id])
        self.assertEqual(data['location_id'], self.env.company.scrap_waste_location_id.id)
        data = self.touch.decontaminate_part(vehicle.id, oil.id, 2.5, 'discarded')
        data = self.touch.decontaminate_part(vehicle.id, oil.id, 1, 'discarded')
        self.assertEqual([part['quantity'] for part in data['parts']], [1, 2.5])
        self.assertEqual(len(data['pending']), 1, "Still offered, as many times as needed")
        self.assertEqual(self.touch.get_vehicle(vehicle.id)['waste_parts'], 2)
        self.assertEqual(self.touch.get_dismantle(vehicle.id)['parts'], [], "Not with the dismantled parts")
        for args in ((oil.id, '1', 'discarded'), ('x', 1, 'discarded')):
            with self.assertRaises(ValidationError):
                self.touch.decontaminate_part(vehicle.id, *args)
        waste_zone = self.env.company.scrap_waste_location_id
        last, first = data['parts']
        self.assertEqual((first['product_id'], first['location_id'], first['can_undo']), (oil.id, waste_zone.id, True))

        # Corrected and removed until it is decontaminated
        data = self.touch.update_decontamination_part(vehicle.id, first['id'], 3, 'discarded')
        self.assertEqual(sorted(part['quantity'] for part in data['parts']), [1, 3])
        data = self.touch.undo_dismantle_part(vehicle.id, last['id'])
        self.assertEqual(data['stage'], 'decontamination')
        self.assertEqual(oil.with_context(location=waste_zone.id).qty_available, 3)
        with self.assertRaises(UserError):
            self.touch.update_decontamination_part(vehicle.id, last['id'], 1, 'missing')

        self.touch.mark_vehicle(vehicle.id, 'decontamination')
        data = self.touch.get_decontamination(vehicle.id)
        self.assertFalse(data['parts'][0]['can_undo'])
        with self.assertRaises(UserError):
            self.touch.decontaminate_part(vehicle.id, oil.id, 1, 'discarded')
        with self.assertRaises(UserError):
            self.touch.update_decontamination_part(vehicle.id, first['id'], 1, 'discarded')
        with self.assertRaises(UserError):
            self.touch.undo_dismantle_part(vehicle.id, first['id'])
