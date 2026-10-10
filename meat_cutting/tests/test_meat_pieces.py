from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.mrp.tests.common import TestMrpCommon

from ..tools import gs1_barcode_value, gs1_check_digit, gs1_sscc
from .common import create_cutting_data


@tagged('post_install', '-at_install')
class TestMeatPieces(TestMrpCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_cutting_data(cls)
        cls.Session = cls.env['meat.cutting.session']
        cls.loin.sudo().meat_piece = True
        cls.frozen_loin.sudo().write({'meat_piece': True, 'use_expiration_date': True, 'expiration_time': 180})
        # Whole loins are ordered by number, about 4.5 kg each
        cls.uom_loin = cls.env['uom.uom'].sudo().create({
            'name': 'Whole loin', 'relative_factor': 4.5, 'relative_uom_id': cls.uom_kg.id})
        cls.loin.sudo().uom_ids = cls.uom_loin
        cls.customer = cls.env['res.partner'].create({'name': 'Butcher'})

    def _cut(self, loin_weights, ribs_weight=7.5):
        session = self.Session.browse(self.Session.start_cutting_session(self.carcass.id, self.lot.id))
        loin_bom_line, ribs_bom_line = self.bom.bom_line_ids
        for weight in loin_weights:
            session.action_add_line(loin_bom_line.id, weight)
        session.action_add_line(ribs_bom_line.id, ribs_weight)
        return session

    def _loin_quants(self, product=None):
        return self.env['stock.quant'].search([
            ('product_id', '=', (product or self.loin).id),
            ('location_id', '=', self.stock_location.id),
            ('quantity', '>', 0),
        ])

    def test_gs1_tools(self):
        self.assertEqual(gs1_check_digit('841234567890'), '5')
        self.assertEqual(gs1_sscc('8437000', 12), '084370000000000129')
        self.assertFalse(gs1_sscc('84370001234', 1234567), "Serial longer than its room")
        # FNC1 after a variable length element followed by another one only
        self.assertEqual(
            gs1_barcode_value([('01', '08412345678905'), ('10', 'L1'), ('21', 'S1')]),
            '\xf10108412345678905' + '10L1\xf1' + '21S1')

    def test_cut_whole_pieces(self):
        session = self._cut([4.6, 4.4])
        loin_lines = session.line_ids.filtered(lambda l: l.product_id == self.loin)
        ribs_line = session.line_ids - loin_lines
        # Each weighed loin is one piece, packed (and labelled) when weighed
        self.assertEqual(len(loin_lines.package_id), 2)
        self.assertTrue(all(loin_lines.package_id.mapped('meat_piece')))
        self.assertFalse(ribs_line.package_id)
        loin_component = session.get_cutting_screen_data()['components'][0]
        self.assertEqual((loin_component['piece'], loin_component['weighed_count']), (True, 2))
        html = self.env['ir.actions.report']._render_qweb_html(
            'meat_cutting.action_report_meat_cutting_label', loin_lines[:1].ids)[0].decode()
        self.assertIn(loin_lines[:1].package_id.name, html)
        # Deleting a piece deletes its empty package
        session.action_add_line(self.bom.bom_line_ids[0].id, 1.0)
        extra_line = session.line_ids.filtered(lambda l: l.weight == 1.0)
        extra_package = extra_line.package_id
        extra_line.unlink()
        self.assertFalse(extra_package.exists())

        session.action_validate()
        quants = self._loin_quants()
        self.assertEqual(sorted(quants.mapped('quantity')), [4.4, 4.6], "One quant per piece")
        self.assertEqual(quants.package_id, loin_lines.package_id)
        self.assertEqual(quants.lot_id.name, 'L001', "The pieces keep the lot of the animal")

    def test_freeze_stock(self):
        self.loin.sudo().write({'use_expiration_date': True, 'expiration_time': 30})
        session = self._cut([4.6, 4.4])
        session.action_validate()
        fresh_quants = self._loin_quants()
        piece = fresh_quants.filtered(lambda q: q.quantity == 4.6)
        with self.assertRaises(UserError):
            self.env['stock.quant'].search([('product_id', '=', self.ribs.id)]).action_meat_freeze()

        action = piece.action_meat_freeze()
        self.assertEqual(self._loin_quants(), fresh_quants - piece)
        frozen_quant = self._loin_quants(self.frozen_loin)
        # The frozen piece is relabelled: product, freezing date, shelf life
        self.assertEqual(action['report_name'], 'meat_cutting.report_meat_piece_label')
        self.assertEqual(action['context']['active_ids'], frozen_quant.ids)
        expiration = frozen_quant.lot_id.expiration_date
        self.assertEqual(
            frozen_quant._get_meat_label_barcode_text(),
            f'(01)08412345678912(3103)004600(17){expiration:%y%m%d}(10)L001')
        html = self.env['ir.actions.report']._render_qweb_html(
            'meat_cutting.action_report_meat_piece_label', frozen_quant.ids)[0].decode()
        for text in ('Frozen Pork Loin', 'Freezing date', piece.package_id.name, 'Expiry date'):
            self.assertIn(text, html)
        self.assertNotIn('Production date', html)
        self.assertAlmostEqual(frozen_quant.quantity, 4.6)
        self.assertEqual(frozen_quant.package_id, piece.package_id, "The frozen piece stays in its package")
        frozen_lot = frozen_quant.lot_id
        self.assertEqual(frozen_lot.name, 'L001')
        self.assertEqual(frozen_lot.crotal_id, self.lot.crotal_id)
        self.assertAlmostEqual(
            frozen_lot.expiration_date, fields.Datetime.now() + timedelta(days=180), delta=timedelta(minutes=5))
        # Traceability: the frozen lot is produced from the fresh one
        consume_line = self.env['stock.move.line'].search([
            ('product_id', '=', self.loin.id), ('location_dest_id.usage', '=', 'production')])
        self.assertEqual(consume_line.produce_line_ids.lot_id, frozen_lot)

        # Freezing the rest of the lot another time: a new dated lot
        fresh_lot = (fresh_quants - piece).lot_id
        self.assertTrue(fresh_lot.can_meat_freeze)
        fresh_lot.action_meat_freeze()
        self.assertFalse(self._loin_quants())
        self.assertEqual(
            self._loin_quants(self.frozen_loin).lot_id.mapped('name'),
            ['L001', f'L001-{fields.Date.context_today(fresh_lot):%y%m%d}'])

    def _deliver_pieces(self, pieces, packaging_qty):
        """ Delivery of `packaging_qty` whole loins, picking the given pieces. """
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        delivery = self.env['stock.picking'].create({
            'picking_type_id': warehouse.out_type_id.id,
            'partner_id': self.customer.id,
            'origin': 'S00042',
            'location_id': self.stock_location.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'move_ids': [Command.create({
                'product_id': self.loin.id,
                'product_uom_qty': packaging_qty * 4.5,
                'uom_id': self.uom_kg.id,
                'location_id': self.stock_location.id,
                'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            })],
        })
        delivery.action_confirm()
        move = delivery.move_ids
        # As set by a sale order line in the packaging unit
        move.packaging_uom_id = self.uom_loin
        move.move_line_ids.unlink()
        self.env['stock.move.line'].create([{
            'move_id': move.id,
            'picking_id': delivery.id,
            'product_id': self.loin.id,
            'uom_id': self.uom_kg.id,
            'quantity': piece.quantity,
            'lot_id': piece.lot_id.id,
            'package_id': piece.package_id.id,
            'result_package_id': piece.package_id.id,
            'location_id': self.stock_location.id,
            'location_dest_id': move.location_dest_id.id,
        } for piece in pieces])
        move.picked = True
        return delivery

    def test_deliver_pieces_in_boxes(self):
        self.loin.sudo().write({'use_expiration_date': True, 'expiration_time': 30})
        self.lot.crotal_id = self.env['stock.crotal'].create({'name': 'ES0123', 'halal': True})
        self._cut([4.6, 4.3]).action_validate()
        pieces = self._loin_quants().sorted('quantity')
        box_type = self.env['stock.package.type'].sudo().create({'name': 'Box', 'meat_sscc_prefix': '8437000'})

        # Two loins ordered (9 kg), the two pieces weigh 8.9 kg: it is complete
        delivery = self._deliver_pieces(pieces, 2)
        delivery.move_line_ids.with_context(force_move_lines=True).action_put_in_pack(package_type_id=box_type.id)
        box = delivery._get_meat_boxes()
        self.assertEqual(len(box), 1)
        self.assertTrue(box.valid_sscc, "Boxes of this type are named with a SSCC")
        self.assertTrue(box.name.startswith('08437000'))

        values = box._get_meat_box_label_values()
        self.assertEqual(values['partner'], self.customer)
        self.assertEqual(values['origin'], 'S00042')
        self.assertEqual(len(values['lines']), 1)
        self.assertEqual(values['lines'][0]['pieces'], 2)
        self.assertAlmostEqual(values['net_weight'], 8.9)
        self.assertTrue(values['halal'])
        self.assertTrue(values['expiration_date'])
        pack_date = box.pack_date.strftime('%y%m%d')
        self.assertEqual(box._get_meat_box_barcode_text(), f'(00){box.name}(13){pack_date}')
        self.assertEqual(box._get_meat_box_barcode_value(), f'\xf100{box.name}13{pack_date}')

        self.assertIs(delivery.button_validate(), True, "No backorder wizard for the missing 0.1 kg")
        self.assertEqual(delivery.state, 'done')
        self.assertFalse(delivery.backorder_ids)
        self.assertAlmostEqual(delivery.move_ids.product_uom_qty, 8.9)
        # Once delivered, the box label still lists its contents
        self.assertEqual(delivery._get_meat_boxes(), box)
        self.assertAlmostEqual(box._get_meat_box_label_values()['net_weight'], 8.9)
        for report, record in (
            ('meat_cutting.action_report_meat_box_label', box),
            ('meat_cutting.action_report_picking_meat_box_label', delivery),
        ):
            html = self.env['ir.actions.report']._render_qweb_html(report, record.ids)[0].decode()
            self.assertIn(box.name, html)
            self.assertIn('HALAL', html)

    def test_deliver_missing_piece(self):
        self._cut([4.6, 4.3]).action_validate()
        pieces = self._loin_quants().sorted('quantity')
        # Two loins ordered, a single one picked: the second is backordered
        delivery = self._deliver_pieces(pieces[:1], 2)
        self.assertIsInstance(delivery.button_validate(), dict, "Backorder wizard")
        self.assertAlmostEqual(delivery.move_ids.product_uom_qty, 9.0)

    def _reserve(self, quantity, uom):
        """ Delivery of `quantity` loins in `uom` (by number or in kg), reserved. """
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        customers = self.env.ref('stock.stock_location_customers')
        delivery = self.env['stock.picking'].create({
            'picking_type_id': warehouse.out_type_id.id,
            'partner_id': self.customer.id,
            'location_id': self.stock_location.id,
            'location_dest_id': customers.id,
            'move_ids': [Command.create({
                'product_id': self.loin.id,
                'product_uom_qty': uom._compute_quantity(quantity, self.uom_kg),
                'uom_id': self.uom_kg.id,
                'location_id': self.stock_location.id,
                'location_dest_id': customers.id,
            })],
        })
        # As set by a sale order line
        delivery.move_ids.packaging_uom_id = uom
        delivery.action_confirm()
        delivery.action_assign()
        return delivery.move_ids

    def test_reserve_whole_pieces(self):
        self._cut([4.6, 4.3]).action_validate()
        pieces = self._loin_quants()
        # Two loins ordered (9 kg): both pieces whole, 8.9 kg, and ready
        move = self._reserve(2, self.uom_loin)
        self.assertEqual(move.move_line_ids.package_id, pieces.package_id)
        self.assertAlmostEqual(move.quantity, 8.9)
        self.assertEqual(move.state, 'assigned', "Ready with the pieces ordered, though lighter")
        # Validated as reserved, without picking: no backorder for the 0.1 kg
        self.assertIs(move.picking_id.button_validate(), True)
        self.assertEqual(move.state, 'done')
        self.assertAlmostEqual(move.product_uom_qty, 8.9)

    def test_reserve_whole_piece_not_split(self):
        self._cut([4.6, 4.3]).action_validate()
        # One loin ordered (4.5 kg): a whole piece, not 4.5 kg of the heavier one
        move = self._reserve(1, self.uom_loin)
        self.assertEqual(len(move.move_line_ids.package_id), 1)
        self.assertIn(move.quantity, (4.6, 4.3))
        self.assertEqual(move.state, 'assigned')
        piece_left = self._loin_quants().filtered(lambda q: q.package_id != move.move_line_ids.package_id)
        # Sold by weight: reserved by weight, as usual, part of the other piece
        move_kg = self._reserve(2, self.uom_kg)
        self.assertEqual(move_kg.move_line_ids.package_id, piece_left.package_id)
        self.assertAlmostEqual(move_kg.quantity, 2)
        # The rest of that piece is not a whole loin: nothing to reserve
        move_left = self._reserve(1, self.uom_loin)
        self.assertFalse(move_left.move_line_ids)
        self.assertEqual(move_left.state, 'confirmed')
