import io
from datetime import date, datetime

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestScrapGaiaReport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.tz = 'Europe/Madrid'
        cls.Report = cls.env['scrap.gaia.report']
        # Without the reports of other tests or data
        cls.Report.search([]).write({'state': 'draft'})
        cls.Report.search([]).unlink()
        cls.ferrous = cls.env.ref('scrap_gaia.material_ferrous')
        cls.plastic = cls.env.ref('scrap_gaia.material_plastic')
        cls.part = cls.env['product.product'].create({
            'name': 'Puerta GAIA', 'is_storable': True, 'scrap_unbuild_type': 'subproduct', 'weight': 20,
            'scrap_material_line_ids': [
                Command.create({'scrap_material_id': cls.ferrous.id, 'percent': 80}),
                Command.create({'scrap_material_id': cls.plastic.id, 'percent': 10}),
            ],
        })
        cls.oil = cls.env['product.product'].create({
            'name': 'Lata de aceite nueva', 'is_storable': True, 'weight': 5,
            'scrap_material_line_ids': [Command.create({'scrap_material_id': cls.plastic.id, 'percent': 10})],
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Chatarras Sur'})
        cls.stock = cls.env.ref('stock.stock_location_stock')
        for product in cls.part | cls.oil:
            cls.env['stock.quant']._update_available_quantity(product, cls.stock, 100)

    def _deliver(self, done, products):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'partner_id': self.partner.id,
            'location_id': self.stock.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'move_ids': [Command.create({'product_id': product.id, 'product_uom_qty': qty}) for product, qty in products],
        })
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.picked = True
        picking.button_validate()
        picking.date_done = done
        return picking

    def test_periods(self):
        """ Monthly by default, after the last one; the periods can't overlap. """
        october = self.Report.create({'date_from': date(2026, 10, 1), 'date_to': date(2026, 10, 31)})
        self.assertEqual(october.name, 'GAIA 2026-10')
        november = self.Report.create({})
        self.assertEqual((november.date_from, november.date_to), (date(2026, 11, 1), date(2026, 11, 30)))
        self.assertEqual(november.name, 'GAIA 2026-11')
        with self.assertRaises(ValidationError):
            self.Report.create({'date_from': date(2026, 10, 31), 'date_to': date(2026, 11, 5)})
        with self.assertRaises(ValidationError):
            self.Report.create({'date_from': date(2026, 12, 10), 'date_to': date(2026, 12, 1)})
        # Another company, the same period
        company = self.env['res.company'].create({'name': 'Otro CAT'})
        self.Report.create({'date_from': date(2026, 10, 1), 'date_to': date(2026, 10, 31), 'company_id': company.id})
        quarter = self.Report.create({'date_from': date(2026, 12, 1), 'date_to': date(2027, 2, 28)})
        self.assertEqual(quarter.name, 'GAIA 2026-12-01 / 2027-02-28')

    def test_report(self):
        """ The deliveries of the period, in the time zone of the user, with the weights written
        in them; frozen once presented; in PDF and Excel. """
        # 31/10 at 23:30 in Madrid is still October; 1/11 at 00:30 in Madrid, November
        first = self._deliver(datetime(2026, 10, 1, 8, 0), [(self.part, 2), (self.oil, 4)])
        last = self._deliver(datetime(2026, 10, 31, 22, 30), [(self.part, 1)])
        november = self._deliver(datetime(2026, 10, 31, 23, 30), [(self.part, 5)])
        only_oil = self._deliver(datetime(2026, 10, 15, 10, 0), [(self.oil, 10)])
        # Written by hand in the delivery: the report takes it as it is
        last.scrap_material_line_ids.filtered(lambda line: line.scrap_material_id == self.ferrous).weight = 15

        report = self.Report.create({'date_from': date(2026, 10, 1), 'date_to': date(2026, 10, 31)})
        report.action_compute()
        self.assertEqual(report.picking_ids, first | last)
        self.assertNotIn(november, report.picking_ids)
        self.assertNotIn(only_oil, report.picking_ids, "Without products of the vehicle recycling")
        totals = {line.scrap_material_id: line.weight for line in report.total_ids}
        self.assertEqual(totals, {self.ferrous: 32 + 15, self.plastic: 4 + 2})
        self.assertAlmostEqual(report.weight_total, 53)
        self.assertEqual(len(report.line_ids), 4)
        self.assertEqual(report._get_move_rows().product_id, self.part, "Not the oil")

        # PDF and Excel
        html = self.env['ir.actions.report']._render_qweb_html('scrap_gaia.action_report_scrap_gaia', report.ids)[0].decode()
        self.assertIn('gaia_totals', html)
        self.assertIn(first.name, html)
        self.assertNotIn('Lata de aceite', html)
        action = report.action_download_xlsx()
        self.assertIn('/xlsx_file/GAIA 2026-10.xlsx', action['url'])
        from openpyxl import load_workbook  # noqa: PLC0415
        book = load_workbook(io.BytesIO(bytes(report.xlsx_file)))
        self.assertEqual(len(book.worksheets), 3)
        deliveries = book.worksheets[1]
        self.assertEqual([deliveries.cell(row, 2).value for row in (2, 3)], [first.name, last.name])
        self.assertEqual(book.worksheets[2].max_row, 3, "A header and a move by delivery")

        # Presented: it can't be changed, computed again nor deleted
        report.action_present()
        self.assertEqual(report.state, 'presented')
        self.assertTrue(report.presented_date)
        with self.assertRaises(UserError):
            report.action_compute()
        with self.assertRaises(UserError):
            report.date_to = date(2026, 11, 2)
        with self.assertRaises(UserError):
            report.unlink()
        report.note = "Presentado en la sede electrónica"
        # The weights of the delivery changed later: the report keeps the ones it had
        last.scrap_material_line_ids.filtered(lambda line: line.scrap_material_id == self.ferrous).weight = 16
        self.assertEqual(sum(report.total_ids.mapped('weight')), 53)
        # Back to draft: it can be computed again
        report.action_draft()
        report.action_compute()
        self.assertAlmostEqual(report.weight_total, 54)

    def test_present_needs_compute(self):
        report = self.Report.create({'date_from': date(2026, 9, 1), 'date_to': date(2026, 9, 30)})
        with self.assertRaises(UserError):
            report.action_present()
