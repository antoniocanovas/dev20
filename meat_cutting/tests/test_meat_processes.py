from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.mrp.tests.common import TestMrpCommon

from .common import create_cutting_data


@tagged('post_install', '-at_install')
class TestMeatProcesses(TestMrpCommon):
    """ Second cut, preparation, production and packing on the factory screen. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_cutting_data(cls)
        cls.Session = cls.env['meat.cutting.session']
        cls.category = cls.env['product.category'].create({'name': 'Pork Pieces'})
        cls.chops = cls.env['product.product'].create({
            'name': 'Pork Chops', 'is_storable': True, 'tracking': 'lot', 'uom_id': cls.uom_kg.id,
            'use_expiration_date': True, 'expiration_time': 10,
        })
        cls.loin.sudo().write({
            'meat_piece': True, 'categ_id': cls.category.id, 'use_expiration_date': True, 'expiration_time': 30,
        })
        # The loin is cut again into chops
        cls.bom_loin = cls.env['mrp.bom'].create({
            'product_tmpl_id': cls.loin.product_tmpl_id.id,
            'product_qty': 1.0,
            'uom_id': cls.uom_kg.id,
            'bom_line_ids': [Command.create({'product_id': cls.chops.id, 'product_qty': 0.9})],
        })
        # Presentations, as attribute values that create no variant
        attribute = cls.env['product.attribute'].create({
            'name': 'Presentation',
            'create_variant': 'no_variant',
            'value_ids': [Command.create({'name': 'Whole'}), Command.create({'name': 'Sliced'})],
        })
        cls.whole, cls.sliced = attribute.value_ids
        cls.loin.product_tmpl_id.attribute_line_ids = [Command.create({
            'attribute_id': attribute.id, 'value_ids': [Command.set(attribute.value_ids.ids)]})]
        cls.customer = cls.env['res.partner'].create({'name': 'Butcher'})

    def _cut_loins(self, weights):
        session = self.Session.browse(self.Session.start_cutting_session(self.carcass.id, self.lot.id))
        for weight in weights:
            session.action_add_line(self.bom.bom_line_ids[0].id, weight)
        session.action_validate()
        return self.env['stock.quant'].search([
            ('product_id', '=', self.loin.id), ('location_id', '=', self.stock_location.id), ('quantity', '>', 0),
        ]).sorted('quantity')

    def test_cutting_package(self):
        pieces = self._cut_loins([4.6, 4.3])
        # Packages are cut again on the cutting mode, not as received lots
        self.assertNotIn(self.loin.id, [p['id'] for p in self.Session.get_cutting_products()])
        families = self.Session.get_cutting_families('cutting')
        self.assertEqual([f['id'] for f in families], [self.category.id])
        packages = self.Session.get_cutting_packages('cutting', self.category.id)
        self.assertEqual(len(packages), 2)
        self.assertEqual(packages[0]['boms'][0]['id'], self.bom_loin.id)

        piece = pieces[-1]
        session = self.Session.browse(self.Session.start_package_session(
            'cutting', piece.package_id.id, self.loin.id))
        self.assertEqual(session.lot_id, piece.lot_id)
        self.assertEqual(self.Session.start_package_session('cutting', piece.package_id.id, self.loin.id), session.id,
                         "The session of the package is resumed")
        session.action_add_line(self.bom_loin.bom_line_ids.id, 2.0)
        session.action_add_line(self.bom_loin.bom_line_ids.id, 2.2)
        session.action_validate()
        self.assertAlmostEqual(session.consumed_qty, 4.6, msg="The whole piece is consumed")
        self.assertFalse(piece.package_id.quant_ids.filtered(lambda q: q.quantity > 0))
        chops = self.env['stock.quant'].search([('product_id', '=', self.chops.id), ('quantity', '>', 0)])
        self.assertAlmostEqual(sum(chops.mapped('quantity')), 4.2)
        self.assertEqual(chops.lot_id.name, piece.lot_id.name, "The chops keep the lot of the animal")
        self.assertEqual(chops.lot_id.crotal_id, piece.lot_id.crotal_id)
        # The chops do not last longer than the loin they come from
        self.assertLessEqual(chops.lot_id.expiration_date, piece.lot_id.expiration_date)

    def test_preparation(self):
        piece = self._cut_loins([4.6])
        self.assertEqual([f['id'] for f in self.Session.get_cutting_families('preparation')], [self.category.id])
        session = self.Session.browse(self.Session.start_package_session(
            'preparation', piece.package_id.id, self.loin.id))
        data = session.get_cutting_screen_data()
        self.assertEqual([p['id'] for p in data['presentations']], [self.whole.id, self.sliced.id])
        self.assertFalse(data['components'])
        session.action_add_line(False, 1.5, self.whole.id)
        line = self.env['meat.cutting.line'].browse(session.action_add_line(False, 1.0, self.whole.id))
        line.action_set_presentation(self.sliced.id)
        self.assertEqual(line.package_id.meat_presentation_id, self.sliced)
        self.assertEqual(line._get_label_values()['product_name'], 'Pork Loin (Sliced)')
        with self.assertRaises(UserError):
            session.action_add_line(False, 1.0, self.chops.id)

        session.action_validate()
        self.assertAlmostEqual(session.consumed_qty, 2.5)
        # What is left stays in the original package
        self.assertAlmostEqual(sum(piece.package_id.quant_ids.mapped('quantity')), 2.1)
        prepared = session.line_ids.package_id.quant_ids
        self.assertEqual(sorted(prepared.mapped('quantity')), [1.0, 1.5])
        self.assertEqual(prepared.lot_id, piece.lot_id, "Same product, same lot")
        self.assertEqual(
            {q.quantity: q.package_id.meat_presentation_id for q in prepared}, {1.0: self.sliced, 1.5: self.whole})

    def test_preparation_freeze(self):
        """ A prepared package kept as stock can be frozen. """
        piece = self._cut_loins([4.6])
        session = self.Session.browse(self.Session.start_package_session(
            'preparation', piece.package_id.id, self.loin.id))
        self.assertTrue(session.get_cutting_screen_data()['can_freeze'])
        session.action_add_line(False, 1.5)
        frozen_line = self.env['meat.cutting.line'].browse(session.action_add_line(False, 1.0))
        frozen_line.action_set_freeze(True)
        session.action_validate()
        self.assertAlmostEqual(sum(piece.package_id.quant_ids.mapped('quantity')), 2.1)
        frozen = frozen_line.package_id.quant_ids
        self.assertEqual(frozen.product_id, self.frozen_loin)
        self.assertAlmostEqual(frozen.quantity, 1.0)

    def test_preparation_too_heavy(self):
        piece = self._cut_loins([4.6])
        session = self.Session.browse(self.Session.start_package_session(
            'preparation', piece.package_id.id, self.loin.id))
        session.action_add_line(False, 5.0)
        with self.assertRaises(UserError):
            session.action_validate()

    def test_production(self):
        pieces = self._cut_loins([4.6, 4.3])
        ribs_lot = self.env['stock.lot'].sudo().create({
            'name': 'RIBS1', 'product_id': self.ribs.id,
            'expiration_date': fields.Datetime.now() + timedelta(days=5),
        })
        self.env['stock.quant']._update_available_quantity(self.ribs, self.stock_location, 3.0, lot_id=ribs_lot)
        sausage = self.env['product.product'].sudo().create({
            'name': 'Sausage', 'is_storable': True, 'tracking': 'lot', 'uom_id': self.uom_kg.id,
            'categ_id': self.category.id, 'use_expiration_date': True, 'expiration_time': 20,
        })
        bom_sausage = self.env['mrp.bom'].sudo().create({
            'product_tmpl_id': sausage.product_tmpl_id.id,
            'meat_use': 'production',
            'product_qty': 1.0,
            'uom_id': self.uom_kg.id,
            'bom_line_ids': [
                Command.create({'product_id': self.loin.id, 'product_qty': 0.7}),
                Command.create({'product_id': self.ribs.id, 'product_qty': 0.3}),
            ],
        })
        # Only the BoMs to make products are proposed, not the cutting ones
        products = self.Session.get_production_products(self.category.id)
        self.assertEqual([p['id'] for p in products], [sausage.id])
        self.assertNotIn(self.bom_loin.id, [b['id'] for b in self.Session._get_cutting_boms(self.loin, 'production')])

        session = self.Session.browse(self.Session.start_production_session(sausage.id))
        self.assertEqual(session.bom_id, bom_sausage)
        loin_stock = session.get_ingredient_packages(self.loin.id)
        self.assertEqual(len(loin_stock), 2)
        piece = pieces[0]
        session.action_add_consumption(
            self.loin.id, 3.0, package_id=piece.package_id.id, lot_id=piece.lot_id.id,
            location_id=piece.location_id.id)
        with self.assertRaises(UserError):
            session.action_add_consumption(
                self.loin.id, 2.0, package_id=piece.package_id.id, lot_id=piece.lot_id.id,
                location_id=piece.location_id.id)
        # Without weight, what is left of the lot is used
        session.action_add_consumption(self.ribs.id, 0, lot_id=ribs_lot.id, location_id=self.stock_location.id)
        self.assertAlmostEqual(session.get_cutting_screen_data()['consumed_weight'], 6.0)
        remaining = {v['package_id']: v['qty'] for v in session.get_ingredient_packages(self.loin.id)}
        self.assertAlmostEqual(remaining[piece.package_id.id], 1.3)
        with self.assertRaises(UserError):
            session.action_add_consumption(self.chops.id, 1.0)

        session.action_add_line(False, 2.9)
        session.action_add_line(False, 2.8)
        self.assertEqual(len(session.line_ids.package_id), 2, "Each weighing is a new package")
        session.action_validate()

        production = session.production_id
        self.assertEqual(production.state, 'done')
        self.assertAlmostEqual(sum(piece.package_id.quant_ids.mapped('quantity')), 1.3)
        self.assertFalse(ribs_lot.quant_ids.filtered(lambda q: q.location_id == self.stock_location and q.quantity))
        made = self.env['stock.quant'].search([('product_id', '=', sausage.id), ('quantity', '>', 0)])
        self.assertEqual(sorted(made.mapped('quantity')), [2.8, 2.9])
        self.assertEqual(made.package_id, session.line_ids.package_id)
        self.assertEqual(made.lot_id.name, session.name, "A new lot")
        # It expires with the ingredient closest to expiry (the ribs)
        self.assertEqual(made.lot_id.expiration_date, ribs_lot.expiration_date)

    def _sausage(self):
        sausage, frozen_sausage = self.env['product.product'].sudo().create([{
            'name': name, 'is_storable': True, 'tracking': 'lot', 'uom_id': self.uom_kg.id,
            'categ_id': self.category.id, 'use_expiration_date': True, 'expiration_time': days,
        } for name, days in (('Sausage', 20), ('Frozen Sausage', 180))])
        sausage.frozen_product_id = frozen_sausage
        sausage.product_tmpl_id.attribute_line_ids = [Command.create({
            'attribute_id': self.whole.attribute_id.id, 'value_ids': [Command.set([self.whole.id, self.sliced.id])]})]
        self.env['mrp.bom'].sudo().create({
            'product_tmpl_id': sausage.product_tmpl_id.id,
            'meat_use': 'production',
            'product_qty': 1.0,
            'uom_id': self.uom_kg.id,
            'bom_line_ids': [
                Command.create({'product_id': self.loin.id, 'product_qty': 0.7}),
                Command.create({'product_id': self.ribs.id, 'product_qty': 0.3}),
            ],
        })
        return sausage, frozen_sausage

    def _use_ribs(self, session):
        ribs_lot = self.env['stock.lot'].sudo().create({'name': 'RIBS2', 'product_id': self.ribs.id})
        self.env['stock.quant']._update_available_quantity(self.ribs, self.stock_location, 1.0, lot_id=ribs_lot)
        session.action_add_consumption(self.ribs.id, 0, lot_id=ribs_lot.id, location_id=self.stock_location.id)

    def test_production_unused_ingredient(self):
        """ Every ingredient of the recipe must be used, in any quantity. """
        pieces = self._cut_loins([4.6])
        sausage, _frozen_sausage = self._sausage()
        session = self.Session.browse(self.Session.start_production_session(sausage.id))
        session.action_add_consumption(
            self.loin.id, 0, package_id=pieces.package_id.id, lot_id=pieces.lot_id.id,
            location_id=pieces.location_id.id)
        session.action_add_line(False, 4.4)
        with self.assertRaisesRegex(UserError, 'Pork Ribs'):
            session.action_validate()
        self._use_ribs(session)
        session.action_validate()
        self.assertEqual(session.production_id.state, 'done')

    def test_production_recommended(self):
        """ The quantity to make proposes the quantity of each ingredient. """
        sausage, _frozen_sausage = self._sausage()
        session = self.Session.browse(self.Session.start_production_session(sausage.id))
        data = session.get_cutting_screen_data()
        self.assertEqual([c['recommended_qty'] for c in data['components']], [0, 0])
        with self.assertRaises(UserError):
            session.action_set_production_qty(0)
        session.action_set_production_qty(12.0)
        data = session.get_cutting_screen_data()
        self.assertEqual(data['production_qty'], 12.0)
        self.assertEqual({c['name']: c['recommended_qty'] for c in data['components']},
                         {'Pork Loin': 8.4, 'Pork Ribs': 3.6})

    def test_production_find_package(self):
        """ A package of any ingredient is found by its name, its lot or a
        scanned label carrying the lot. """
        pieces = self._cut_loins([4.6, 4.3])
        sausage, _frozen_sausage = self._sausage()
        session = self.Session.browse(self.Session.start_production_session(sausage.id))
        piece = pieces[0]
        found = session.find_ingredient_packages(piece.package_id.name)
        self.assertEqual([(f['product_id'], f['package_id']) for f in found], [(self.loin.id, piece.package_id.id)])
        found = session.find_ingredient_packages(f'0112345678901231{piece.lot_id.name}')
        self.assertEqual({f['package_id'] for f in found}, set(pieces.package_id.ids))
        self.assertFalse(session.find_ingredient_packages('nothing-like-this'))
        self.assertFalse(session.find_ingredient_packages(' '))

    def test_production_freeze(self):
        """ The packages made can be frozen and presented. """
        pieces = self._cut_loins([4.6, 4.3])
        sausage, frozen_sausage = self._sausage()
        session = self.Session.browse(self.Session.start_production_session(sausage.id))
        data = session.get_cutting_screen_data()
        self.assertTrue(data['can_freeze'])
        self.assertEqual([p['id'] for p in data['presentations']], [self.whole.id, self.sliced.id])
        for piece in pieces:
            session.action_add_consumption(
                self.loin.id, 0, package_id=piece.package_id.id, lot_id=piece.lot_id.id,
                location_id=piece.location_id.id)
        self._use_ribs(session)
        fresh_line = self.env['meat.cutting.line'].browse(session.action_add_line(False, 4.0, self.sliced.id))
        session.action_set_freeze(True)
        frozen_line = self.env['meat.cutting.line'].browse(session.action_add_line(False, 4.5, self.whole.id))
        self.assertTrue(frozen_line.freeze)
        self.assertEqual(frozen_line.output_product_id, frozen_sausage)
        self.assertEqual(frozen_line._get_label_values()['product_name'], 'Frozen Sausage (Whole)')
        session.action_validate()

        self.assertEqual(session.production_id.state, 'done')
        fresh = fresh_line.package_id.quant_ids
        self.assertEqual((fresh.product_id, fresh.quantity), (sausage, 4.0))
        self.assertEqual(fresh.package_id.meat_presentation_id, self.sliced)
        frozen = frozen_line.package_id.quant_ids.filtered(lambda q: q.quantity > 0)
        self.assertEqual((frozen.product_id, frozen.quantity), (frozen_sausage, 4.5))
        self.assertEqual(frozen.lot_id.name, session.name)
        # The shelf life of the frozen product starts when made
        self.assertGreater(frozen.lot_id.expiration_date, fresh.lot_id.expiration_date)
        self.assertFalse(self.env['stock.quant'].search([
            ('product_id', '=', sausage.id), ('package_id', '=', frozen_line.package_id.id), ('quantity', '>', 0)]))

    def test_production_all_frozen(self):
        pieces = self._cut_loins([4.6])
        sausage, frozen_sausage = self._sausage()
        session = self.Session.browse(self.Session.start_production_session(sausage.id))
        session.action_add_consumption(
            self.loin.id, 0, package_id=pieces.package_id.id, lot_id=pieces.lot_id.id,
            location_id=pieces.location_id.id)
        self._use_ribs(session)
        session.action_set_freeze(True)
        session.action_add_line(False, 4.4)
        session.action_validate()
        made = self.env['stock.quant'].search([
            ('product_id', 'in', (sausage | frozen_sausage).ids), ('quantity', '>', 0)])
        self.assertEqual((made.product_id, made.quantity), (frozen_sausage, 4.4))

    def _delivery(self, pieces):
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        customers = self.env.ref('stock.stock_location_customers')
        uom_loin = self.env['uom.uom'].sudo().create({
            'name': 'Whole loin', 'relative_factor': 4.5, 'relative_uom_id': self.uom_kg.id})
        delivery = self.env['stock.picking'].create({
            'picking_type_id': warehouse.out_type_id.id,
            'partner_id': self.customer.id,
            'location_id': self.stock_location.id,
            'location_dest_id': customers.id,
            'move_ids': [Command.create({
                'product_id': self.loin.id,
                'product_uom_qty': pieces * 4.5,
                'uom_id': self.uom_kg.id,
                'location_id': self.stock_location.id,
                'location_dest_id': customers.id,
            })],
        })
        delivery.move_ids.packaging_uom_id = uom_loin
        delivery.action_confirm()
        delivery.action_assign()
        return delivery

    def test_packing(self):
        pieces = self._cut_loins([4.6, 4.3, 4.4])
        delivery = self._delivery(2)
        self.assertIn(delivery.id, [p['id'] for p in self.env['stock.picking'].get_meat_packing_pickings()])
        data = delivery.get_meat_packing_data()
        self.assertEqual(len(data['lines']), 2)
        self.assertEqual(data['moves'][0]['pieces_ordered'], 2)
        self.assertFalse(data['boxes'])

        box = delivery.action_meat_new_box()
        line = data['lines'][0]
        delivery.action_meat_toggle_box(line['id'], box['id'])
        data = delivery.get_meat_packing_data()
        self.assertEqual([b['count'] for b in data['boxes']], [1])
        self.assertEqual(data['lines'][0]['box_id'], box['id'])
        # Pressed again, it is taken out of the box
        delivery.action_meat_toggle_box(line['id'], box['id'])
        self.assertFalse(delivery.get_meat_packing_data()['boxes'])

        # A piece not reserved replaces an unpacked one of the same product
        free_piece = pieces.filtered(lambda q: q.package_id not in delivery.move_line_ids.package_id)
        delivery.action_meat_scan_package(free_piece.package_id.name, box['id'])
        self.assertIn(free_piece.package_id, delivery.move_line_ids.package_id)
        self.assertEqual(len(delivery.move_line_ids), 2)
        other = delivery.move_line_ids.filtered(lambda ml: ml.package_id != free_piece.package_id)
        delivery.action_meat_scan_package(other.package_id.name, box['id'])
        with self.assertRaises(UserError):
            delivery.action_meat_scan_package(
                (pieces.package_id - delivery.move_line_ids.package_id).name, box['id'])

        box_package = self.env['stock.package'].browse(box['id'])
        values = box_package._get_meat_box_label_values()
        self.assertEqual(values['pieces'], 2)
        self.assertIs(delivery.button_validate(), True)
        self.assertEqual(delivery.state, 'done')
        self.assertEqual(delivery._get_meat_boxes(), box_package)

    def test_relabel_piece(self):
        """ The label of a piece is printed again as weighed, or from its
        stock, with its texts edited. """
        pieces = self._cut_loins([4.6, 4.3])
        piece = pieces[1]
        Package = self.env['stock.package']
        found = Package.meat_relabel_search(piece.package_id.name)
        self.assertEqual([(f['id'], f['is_box']) for f in found], [(piece.package_id.id, False)])
        # A scanned GS1 label finds its piece among those of the lot by its weight
        line = self.env['meat.cutting.line'].search([('package_id', '=', piece.package_id.id)])
        scanned = line._get_label_barcode_value().replace('\xf1', '\x1d')
        self.assertEqual([f['id'] for f in Package.meat_relabel_search(scanned)], [piece.package_id.id])
        self.assertEqual(len(Package.meat_relabel_search(self.lot.name)), 2)
        self.assertFalse(Package.meat_relabel_search(' '))

        data = piece.package_id.get_meat_relabel_data()
        kinds = [f['kind'] for f in data['formats']]
        self.assertEqual(kinds[0], 'line')
        self.assertEqual(kinds[-1], 'stock')
        self.assertEqual(data['formats'][0]['res_ids'], line.ids)
        stock_format = data['formats'][-1]
        self.assertEqual(stock_format['res_ids'], piece.ids)

        piece.package_id.action_save_label(dict(
            piece.package_id.get_label_data()['values'], product_name='Iberian Loin', note='Keep cold'))
        values = piece._get_meat_label_values()
        self.assertEqual((values['product_name'], values['note']), ('Iberian Loin', 'Keep cold'))
        self.assertEqual(line._get_label_values()['product_name'], 'Pork Loin', "The cut label is not changed")
        piece.package_id.action_reset_label()
        self.assertEqual(piece._get_meat_label_values()['product_name'], 'Pork Loin')

        # Once frozen, the stock is no longer the one weighed: only its own label
        piece._meat_freeze()
        self.assertEqual([f['kind'] for f in piece.package_id.get_meat_relabel_data()['formats']], ['stock'])

    def test_relabel_box(self):
        pieces = self._cut_loins([4.6, 4.3])
        delivery = self._delivery(2)
        box = delivery.action_meat_new_box()
        for line in delivery.get_meat_packing_data()['lines']:
            delivery.action_meat_toggle_box(line['id'], box['id'])
        box_package = self.env['stock.package'].browse(box['id'])
        found = self.env['stock.package'].meat_relabel_search(box_package.name)
        self.assertEqual([(f['id'], f['is_box'], f['pieces']) for f in found], [(box_package.id, True, 2)])
        formats = box_package.get_meat_relabel_data()['formats']
        self.assertEqual([(f['kind'], f['res_ids'], f['edit_model'], f['edit_kind']) for f in formats],
                         [('box', box_package.ids, 'stock.package', 'box')])
        # Customer and note of the box label can be edited
        box_label = box_package.with_context(meat_label_kind='box')
        data = box_label.get_label_data()
        self.assertEqual(data['values'], {'partner_name': 'Butcher', 'note': ''})
        box_label.action_save_label({'partner_name': 'Butcher Shop', 'note': 'Fragile'})
        values = box_package._get_meat_box_label_values()
        self.assertEqual((values['partner_name'], values['note']), ('Butcher Shop', 'Fragile'))
        self.assertFalse(box_package.meat_label_custom, "The piece label of the package is not changed")
        box_label.action_reset_label()
        self.assertEqual(box_package._get_meat_box_label_values()['partner_name'], 'Butcher')
        # A piece in the box offers the label of its box too
        piece_formats = pieces[0].package_id.get_meat_relabel_data()['formats']
        self.assertEqual(piece_formats[-1]['kind'], 'box')
        self.assertEqual(piece_formats[-1]['res_ids'], box_package.ids)
