from datetime import date, datetime, timedelta

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.mrp.tests.common import TestMrpCommon

from .common import create_cutting_data


@tagged('post_install', '-at_install')
class TestMeatCutting(TestMrpCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_cutting_data(cls)
        cls.Session = cls.env['meat.cutting.session']

    def _qty(self, product, lot_name):
        lot = self.env['stock.lot'].search([('product_id', '=', product.id), ('name', '=', lot_name)])
        return self.env['stock.quant']._get_available_quantity(product, self.stock_location, lot_id=lot, strict=True)

    def test_cutting_flow(self):
        self.assertEqual(self.receipt.state, 'done')
        self.assertIn(self.receipt.id, [p['id'] for p in self.Session.get_cutting_pickings()])
        products = self.Session.get_cutting_products(picking_id=self.receipt.id)
        self.assertEqual([p['id'] for p in products], [self.carcass.id])
        self.assertEqual(products[0]['lots'][0]['id'], self.lot.id)

        session = self.Session.browse(self.Session.start_cutting_session(self.carcass.id, self.lot.id, self.receipt.id))
        self.assertEqual(session.bom_id, self.bom)
        self.assertEqual(session.location_id, self.stock_location)
        # Resuming returns the same draft session
        self.assertEqual(self.Session.start_cutting_session(self.carcass.id, self.lot.id, self.receipt.id), session.id)

        loin_line, ribs_line = self.bom.bom_line_ids
        session.action_add_line(loin_line.id, 10.0)
        session.action_add_line(ribs_line.id, 7.5)
        with self.assertRaises(UserError):
            session.action_add_line(ribs_line.id, 0)
        # A cut can be weighed several times (e.g. in several crates)
        session.action_add_line(ribs_line.id, 2.5)
        data = session.get_cutting_screen_data()
        self.assertEqual(
            [(c['weighed_count'], c['weighed_qty']) for c in data['components']], [(1, 10.0), (2, 10.0)])
        self.assertAlmostEqual(data['consumed_qty'], 100)
        self.assertFalse(session.line_ids.package_id, "Cuts not sold as whole pieces are not packed")
        session.line_ids.filtered(lambda l: l.product_id == self.loin).unlink()
        self.assertEqual(
            [c['weighed_count'] for c in session.get_cutting_screen_data()['components']], [0, 2])
        session.action_add_line(loin_line.id, 10.25)
        self.assertAlmostEqual(session.total_weight, 20.25)

        line = session.line_ids.filtered(lambda l: l.product_id == self.loin)
        self.assertEqual(line._get_label_barcode_text(), '(01)08412345678905(3103)010250(10)L001')
        pdf, _fmt = self.env['ir.actions.report']._render_qweb_pdf(
            'meat_cutting.action_report_meat_cutting_label', line.ids)
        self.assertTrue(pdf)

        data = session.action_validate()
        self.assertEqual(data['state'], 'done')
        self.assertEqual(session.unbuild_id.state, 'done')
        self.assertEqual(session.unbuild_id.cutting_session_id, session)
        # The whole lot (one animal) is consumed, the rest is cutting loss
        self.assertAlmostEqual(session.consumed_qty, 100)
        self.assertAlmostEqual(self._qty(self.carcass, 'L001'), 0)
        self.assertAlmostEqual(self._qty(self.loin, 'L001'), 10.25)
        self.assertAlmostEqual(self._qty(self.ribs, 'L001'), 10.0)
        # Without crotal on the receipt lot, one is created from it and given to the cuts
        crotal = self.lot.crotal_id
        self.assertEqual(crotal.name, 'L001')
        cut_lots = session.unbuild_id.produce_line_ids.move_line_ids.lot_id.filtered(lambda lot: lot.product_id != self.carcass)
        self.assertEqual(cut_lots.product_id, self.loin | self.ribs)
        self.assertEqual(cut_lots.crotal_id, crotal)
        self.assertFalse(self.Session.get_cutting_products())
        with self.assertRaises(UserError):
            session.line_ids.unlink()

    def test_cutting_existing_crotal(self):
        crotal = self.env['stock.crotal'].create({
            'name': 'ES041234567890',
            'product_id': self.carcass.id,
            'breed': 'Duroc',
            'birth_country': 'Spain',
            'reared_country': 'Spain, Portugal',
        })
        self.lot.crotal_id = crotal
        # The screen searches the receipts and lots by product, lot and crotal
        picking_data = next(p for p in self.Session.get_cutting_pickings() if p['id'] == self.receipt.id)
        self.assertEqual(set(picking_data['search_terms']), {'Pork Carcass', 'L001', 'ES041234567890'})
        lot_data = self.Session.get_cutting_products()[0]['lots'][0]
        self.assertEqual(lot_data['crotal_name'], 'ES041234567890')
        session = self.Session.browse(self.Session.start_cutting_session(self.carcass.id, self.lot.id))
        self.assertEqual(session.get_cutting_screen_data()['crotal']['name'], 'ES041234567890')
        session.action_add_line(self.bom.bom_line_ids[0].id, 12.0)
        session.action_validate()
        cut_lot = session.unbuild_id.produce_line_ids.move_line_ids.lot_id.filtered(lambda lot: lot.product_id != self.carcass)
        self.assertEqual(cut_lot.crotal_id, crotal)
        self.assertEqual(cut_lot.name, 'L001')
        self.assertEqual(self.env['stock.crotal'].search_count([]), 1)

    def test_edit_label(self):
        crotal = self.env['stock.crotal'].create({
            'name': 'ES041234567890',
            'birth_country': 'Spain',
            'reared_country': 'Spain',
        })
        self.lot.crotal_id = crotal
        session = self.Session.browse(self.Session.start_cutting_session(self.carcass.id, self.lot.id, self.receipt.id))
        session.action_add_line(self.bom.bom_line_ids[0].id, 10.25)
        line = session.line_ids
        data = line.get_label_data()
        self.assertFalse(data['custom'])
        self.assertEqual(data['values']['product_name'], 'Pork Loin')
        self.assertEqual(data['values']['reared_country'], 'Spain')

        line.action_save_label(dict(data['values'], product_name='Iberian Loin', reared_country='', note='Keep cold'))
        values = line._get_label_values()
        self.assertEqual(values['product_name'], 'Iberian Loin')
        self.assertFalse(values['reared_country'], "An emptied text is not printed")
        self.assertEqual(values['birth_country'], 'Spain')
        # The crotal, the line and the traceability barcode are untouched
        self.assertEqual(crotal.reared_country, 'Spain')
        self.assertEqual(line.product_id, self.loin)
        self.assertEqual(line._get_label_barcode_text(), '(01)08412345678905(3103)010250(10)L001')
        html = self.env['ir.actions.report']._render_qweb_html(
            'meat_cutting.action_report_meat_cutting_label', line.ids)[0].decode()
        self.assertIn('Iberian Loin', html)
        self.assertIn('Keep cold', html)
        self.assertNotIn('Reared in', html)

        line.action_reset_label()
        self.assertEqual(line._get_label_values()['product_name'], 'Pork Loin')
        self.assertEqual(line._get_label_values()['reared_country'], 'Spain')

    def test_label_format(self):
        standard = self.env.ref('meat_cutting.action_report_meat_cutting_label')
        other = standard.sudo().copy({'name': 'Box Label'})
        session = self.Session.browse(self.Session.start_cutting_session(self.carcass.id, self.lot.id))
        self.assertEqual(session.label_report_id, standard)
        data = session.get_cutting_screen_data()
        self.assertIn(other.id, [f['id'] for f in data['label_formats']])
        session.action_set_label_report(other.id)
        self.assertEqual(session.get_cutting_screen_data()['label_report_id'], other.id)
        with self.assertRaises(UserError):
            session.action_set_label_report(self.env.ref('stock.action_report_delivery').id)
        # The next session keeps the format last used by the operator
        session.action_cancel()
        new_session = self.Session.browse(self.Session.start_cutting_session(self.carcass.id, self.lot.id))
        self.assertEqual(new_session.label_report_id, other)

    def test_cutting_method(self):
        products = self.Session.get_cutting_products(picking_id=self.receipt.id)
        self.assertEqual([bom['name'] for bom in products[0]['boms']], ['Standard', 'Chops'])
        self.assertEqual([bom['cut_count'] for bom in products[0]['boms']], [2, 1])
        session = self.Session.browse(self.Session.start_cutting_session(
            self.carcass.id, self.lot.id, self.receipt.id, self.bom_chops.id))
        self.assertEqual(session.bom_id, self.bom_chops)
        self.assertEqual(session.get_cutting_screen_data()['bom_name'], 'Chops')
        # Without weighed cuts, the method of the session can still be changed
        self.assertEqual(self.Session.start_cutting_session(
            self.carcass.id, self.lot.id, self.receipt.id, self.bom.id), session.id)
        self.assertEqual(session.bom_id, self.bom)
        session.action_add_line(self.bom.bom_line_ids[0].id, 10.0)
        with self.assertRaises(UserError):
            self.Session.start_cutting_session(self.carcass.id, self.lot.id, self.receipt.id, self.bom_chops.id)
        # Resuming without method keeps the one of the session
        self.assertEqual(self.Session.start_cutting_session(self.carcass.id, self.lot.id, self.receipt.id), session.id)
        self.assertEqual(session.bom_id, self.bom)
        other_bom = self.env['mrp.bom'].sudo().create({
            'product_tmpl_id': self.loin.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': self.ribs.id, 'product_qty': 1.0})],
        })
        with self.assertRaises(UserError):
            self.Session.start_cutting_session(self.carcass.id, self.lot.id, False, other_bom.id)

    def test_cut_expiration_date(self):
        self.loin.sudo().write({'use_expiration_date': True, 'expiration_time': 10, 'alert_time': 2})
        session = self.Session.browse(self.Session.start_cutting_session(self.carcass.id, self.lot.id))
        session.action_add_line(self.bom.bom_line_ids[0].id, 10.0)
        session.action_add_line(self.bom.bom_line_ids[1].id, 5.0)
        weighed_date = datetime(2026, 10, 1, 9, 30)
        session.line_ids.date = weighed_date
        loin_line = session.line_ids.filtered(lambda l: l.product_id == self.loin)
        ribs_line = session.line_ids.filtered(lambda l: l.product_id == self.ribs)
        # Printed when weighed, before the lot exists: same rule as the lot
        self.env.user.tz = 'Europe/Madrid'
        self.assertEqual(loin_line._get_label_dates(), {
            'production_date': date(2026, 10, 1), 'expiration_date': date(2026, 10, 11)})
        self.assertFalse(ribs_line._get_label_dates()['expiration_date'])
        session.action_validate()
        cut_lots = session.unbuild_id.produce_line_ids.move_line_ids.lot_id
        loin_lot = cut_lots.filtered(lambda lot: lot.product_id == self.loin)
        ribs_lot = cut_lots.filtered(lambda lot: lot.product_id == self.ribs)
        # The shelf life counts from the weighing of the cut
        self.assertEqual(loin_lot.expiration_date, weighed_date + timedelta(days=10))
        self.assertEqual(loin_lot.alert_date, weighed_date + timedelta(days=8))
        self.assertFalse(ribs_lot.expiration_date, "Products without expiration dates keep none")
        # Reprinted labels follow the lot, also when its date is corrected
        loin_lot.expiration_date = datetime(2026, 10, 9, 22, 30)
        self.assertEqual(loin_line._get_label_dates()['expiration_date'], date(2026, 10, 10), "In the user's timezone")
        # The GS1 barcode carries the expiration date, before the lot
        self.assertEqual(loin_line._get_label_barcode_text(), '(01)08412345678905(3103)010000(17)261010(10)L001')
        self.assertEqual(ribs_line._get_label_barcode_text(), 'L001', "No GTIN: the lot only")
        html = self.env['ir.actions.report']._render_qweb_html(
            'meat_cutting.action_report_meat_cutting_label', (loin_line | ribs_line).ids)[0].decode()
        self.assertEqual(html.count('Production date'), 2)
        self.assertEqual(html.count('Expiry date'), 1)

    def test_freeze(self):
        self.frozen_loin.sudo().write({'use_expiration_date': True, 'expiration_time': 180})
        session = self.Session.browse(self.Session.start_cutting_session(self.carcass.id, self.lot.id))
        self.assertTrue(session.get_cutting_screen_data()['can_freeze'])
        loin_bom_line, ribs_bom_line = self.bom.bom_line_ids
        # Freezing by default only applies to the cuts that have a frozen product
        session.action_set_freeze(True)
        session.action_add_line(loin_bom_line.id, 10.0)
        session.action_add_line(ribs_bom_line.id, 5.0)
        loin_line = session.line_ids.filtered(lambda l: l.product_id == self.loin)
        ribs_line = session.line_ids.filtered(lambda l: l.product_id == self.ribs)
        self.assertTrue(loin_line.freeze)
        self.assertEqual(loin_line.output_product_id, self.frozen_loin)
        self.assertFalse(ribs_line.freeze)
        self.assertEqual(ribs_line.output_product_id, self.ribs)
        with self.assertRaises(ValidationError):
            ribs_line.freeze = True
        # The label shows the frozen product, by name and barcode
        self.assertEqual(loin_line._get_label_values()['product_name'], 'Frozen Pork Loin')
        expiration = loin_line._get_label_dates()['expiration_date'].strftime('%y%m%d')
        self.assertEqual(loin_line._get_label_barcode_text(), f'(01)08412345678912(3103)010000(17){expiration}(10)L001')
        # GS1-128: FNC1 first, no separator needed after predefined length elements
        self.assertEqual(loin_line._get_label_barcode_value(), f'\xf10108412345678912310301000017{expiration}10L001')
        # An edited label keeps following the product name unless it was renamed
        loin_line.action_save_label(dict(loin_line._get_label_values(), note='Keep at -18 °C'))
        loin_line.action_set_freeze(False)
        self.assertEqual(loin_line._get_label_values()['product_name'], 'Pork Loin')
        loin_line.action_set_freeze(True)
        self.assertEqual(loin_line._get_label_values()['product_name'], 'Frozen Pork Loin')
        self.assertEqual(loin_line._get_label_values()['note'], 'Keep at -18 °C')

        session.action_validate()
        produced = session.unbuild_id.produce_line_ids.move_line_ids.filtered(lambda l: l.product_id != self.carcass)
        self.assertEqual(produced.product_id, self.frozen_loin | self.ribs)
        self.assertAlmostEqual(self._qty(self.frozen_loin, 'L001'), 10.0)
        self.assertAlmostEqual(self._qty(self.loin, 'L001'), 0.0)
        frozen_lot = produced.lot_id.filtered(lambda lot: lot.product_id == self.frozen_loin)
        self.assertEqual(frozen_lot.expiration_date, loin_line.date + timedelta(days=180))
        with self.assertRaises(UserError):
            loin_line.action_set_freeze(False)

    def test_resume_session_by_lot(self):
        # Entering without receipt resumes the session opened from the receipt, and vice versa
        session = self.Session.browse(self.Session.start_cutting_session(self.carcass.id, self.lot.id, self.receipt.id))
        session.action_add_line(self.bom.bom_line_ids[0].id, 10.0)
        self.assertEqual(self.Session.start_cutting_session(self.carcass.id, self.lot.id), session.id)
        session.action_cancel()
        session = self.Session.browse(self.Session.start_cutting_session(self.carcass.id, self.lot.id))
        self.assertFalse(session.picking_id)
        self.assertEqual(self.Session.start_cutting_session(self.carcass.id, self.lot.id, self.receipt.id), session.id)
        self.assertEqual(session.picking_id, self.receipt, "The receipt is set on the resumed session")
        # A lot can only be cut once at a time
        with self.assertRaises(ValidationError):
            self.Session.create({
                'product_id': self.carcass.id,
                'lot_id': self.lot.id,
                'bom_id': self.bom.id,
                'location_id': self.stock_location.id,
                'location_dest_id': self.stock_location.id,
            })

    def test_crotal_data_on_lots_and_stock(self):
        crotal = self.env['stock.crotal'].create({
            'name': 'ES041234567890',
            'sex': 'female',
            'halal': True,
            'breed': 'Limousin',
            'birth_country': 'France',
            'reared_country': 'Spain',
            'slaughter_date': '2026-10-01',
        })
        self.lot.crotal_id = crotal
        self.assertTrue(self.lot.crotal_halal)
        self.assertEqual(self.lot.crotal_sex, 'female')
        Quant = self.env['stock.quant']
        quant = Quant.search([('lot_id', '=', self.lot.id), ('location_id', '=', self.stock_location.id)])
        self.assertEqual(quant.crotal_id, crotal)
        self.assertTrue(quant.crotal_halal)
        self.assertEqual(quant.crotal_birth_country, 'France')
        # The cuts inherit the crotal, so their stock is filtered and grouped too
        session = self.Session.browse(self.Session.start_cutting_session(self.carcass.id, self.lot.id))
        session.action_add_line(self.bom.bom_line_ids[0].id, 10.0)
        session.action_validate()
        groups = Quant._read_group(
            [('crotal_halal', '=', True), ('location_id', '=', self.stock_location.id), ('quantity', '>', 0)],
            ['product_id', 'crotal_reared_country'], ['quantity:sum'])
        self.assertEqual([(product, country, qty) for product, country, qty in groups], [(self.loin, 'Spain', 10.0)])
        # Changing the crotal updates its lots and stock
        crotal.halal = False
        self.assertFalse(Quant.search_count([('crotal_halal', '=', True)]))
        self.assertEqual(
            self.env['stock.lot'].search([('crotal_sex', '=', 'female')]).product_id, self.carcass | self.loin)
