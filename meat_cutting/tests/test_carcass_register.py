from datetime import date, timedelta

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCarcassRegister(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.uom_kg = cls.env.ref('uom.product_uom_kgm')
        # Carcasses are ordered by number, about 90 kg each
        cls.uom_carcass = cls.env['uom.uom'].create({
            'name': 'Pork carcass', 'relative_factor': 90, 'relative_uom_id': cls.uom_kg.id})
        cls.carcass = cls.env['product.product'].create({
            'name': 'Pork Carcass',
            'type': 'consu',
            'is_storable': True,
            'tracking': 'lot',
            'meat_piece': True,
            'use_expiration_date': True,
            'expiration_time': 30,
            'uom_id': cls.uom_kg.id,
            'uom_ids': [Command.set(cls.uom_carcass.ids)],
        })
        cls.slaughterhouse = cls.env['res.partner'].create({'name': 'Slaughterhouse', 'city': 'Murcia'})
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)

    def _receipt(self, carcasses):
        """ Receipt of `carcasses` carcasses, ordered in the packaging unit. """
        supplier_location = self.env.ref('stock.stock_location_suppliers')
        receipt = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.in_type_id.id,
            'partner_id': self.slaughterhouse.id,
            'location_id': supplier_location.id,
            'location_dest_id': self.warehouse.lot_stock_id.id,
            'move_ids': [Command.create({
                'product_id': self.carcass.id,
                'product_uom_qty': carcasses * 90,
                'uom_id': self.uom_kg.id,
                'location_id': supplier_location.id,
                'location_dest_id': self.warehouse.lot_stock_id.id,
            })],
        })
        receipt.action_confirm()
        # As set by a purchase order line in the packaging unit
        receipt.move_ids.packaging_uom_id = self.uom_carcass
        return receipt

    def _register(self, receipt, carcasses, **header):
        """ Register the carcasses, given as (crotal, weight, line values). """
        action = receipt.action_register_carcasses()
        register_form = Form(self.env[action['res_model']].with_context(action['context']))
        for field_name, value in header.items():
            setattr(register_form, field_name, value)
        for name, weight, values in carcasses:
            with register_form.line_ids.new() as line:
                line.name = name
                line.weight = weight
                for field_name, value in values.items():
                    setattr(line, field_name, value)
        register = register_form.save()
        register.action_confirm()
        return register

    def test_register_carcasses(self):
        self.env['stock.crotal'].create({
            'name': 'ES000', 'partner_id': self.slaughterhouse.id, 'supplier_health_code': 'ES 10.04512/MU CE'})
        receipt = self._receipt(3)
        slaughter_date = date.today() - timedelta(days=3)
        register = self._register(receipt, [
            ('ES001', 94.6, {'sex': 'male', 'breed': 'Duroc', 'quality': 'E'}),
            ('ES002', 89.3, {'sex': 'female', 'reared_country': 'Francia'}),
            ('ES003', 81.8, {'halal': False}),
        ], slaughter_date=slaughter_date, slaughter_order='SAC-1', birth_country='España',
            reared_country='España', halal=True, halal_certifier='Certifier', halal_certificate='HAL-1')
        self.assertEqual(register.partner_id, self.slaughterhouse)
        self.assertEqual(register.supplier_health_code, 'ES 10.04512/MU CE', "As in the last crotal of the supplier")

        move_lines = receipt.move_line_ids
        self.assertEqual(move_lines.mapped('quantity'), [94.6, 89.3, 81.8])
        self.assertTrue(receipt.move_ids.picked)
        lots = move_lines.lot_id
        self.assertEqual(lots.mapped('name'), ['ES001', 'ES002', 'ES003'], "Lots named after their crotal")
        crotals = lots.crotal_id
        self.assertEqual(crotals.mapped('name'), lots.mapped('name'))
        crotal = crotals[0]
        self.assertRecordValues(crotal, [{
            'product_id': self.carcass.id,
            'partner_id': self.slaughterhouse.id,
            'supplier_health_code': 'ES 10.04512/MU CE',
            'supplier_city': 'Murcia',
            'slaughter_date': slaughter_date,
            'slaughter_order': 'SAC-1',
            'sex': 'male',
            'breed': 'Duroc',
            'quality': 'E',
            'birth_country': 'España',
            'reared_country': 'España',
            'halal': True,
            'halal_certifier': 'Certifier',
            'halal_certificate': 'HAL-1',
        }])
        # Defaults of the header, changed on a carcass
        self.assertEqual(crotals[1].reared_country, 'Francia')
        self.assertFalse(crotals[2].halal)
        self.assertFalse(crotals[2].halal_certificate)
        # The carcass expires counting from the slaughter
        self.assertEqual(lots[0].expiration_date.date(), slaughter_date + timedelta(days=30))

        # Three carcasses ordered, 265.7 kg received: it is complete
        self.assertIs(receipt.button_validate(), True)
        self.assertEqual(receipt.state, 'done')
        self.assertFalse(receipt.backorder_ids)
        self.assertAlmostEqual(receipt.move_ids.product_uom_qty, 265.7)
        self.assertAlmostEqual(lots[0].product_qty, 94.6)

    def test_register_missing_carcass(self):
        receipt = self._receipt(3)
        self._register(receipt, [('ES001', 94.6, {}), ('ES002', 89.3, {})])
        self.assertIsInstance(receipt.button_validate(), dict, "Backorder wizard for the missing carcass")

    def test_register_known_crotal(self):
        # A lot received without crotal, and a crotal registered in advance
        lot = self.env['stock.lot'].create({'name': 'ES001', 'product_id': self.carcass.id})
        crotal = self.env['stock.crotal'].create({'name': 'ES002', 'breed': 'Duroc'})
        receipt = self._receipt(2)
        self._register(receipt, [('ES001', 94.6, {}), ('ES002', 89.3, {'sex': 'female'})])
        self.assertEqual(receipt.move_line_ids.lot_id[0], lot)
        self.assertEqual(lot.crotal_id.name, 'ES001')
        self.assertEqual(receipt.move_line_ids.lot_id[1].crotal_id, crotal)
        self.assertEqual(crotal.sex, 'female')

        # Once received, the crotal is not received again
        with self.assertRaisesRegex(UserError, 'already been received'):
            self._register(self._receipt(1), [('ES002', 90, {})])
        with self.assertRaisesRegex(UserError, 'repeated'):
            self._register(self._receipt(2), [('ES003', 90, {}), ('ES003', 91, {})])
        with self.assertRaisesRegex(UserError, 'weight'):
            self._register(self._receipt(1), [('ES004', 0, {})])
        self.assertFalse(self.env['stock.crotal'].search([('name', 'in', ['ES003', 'ES004'])]))
