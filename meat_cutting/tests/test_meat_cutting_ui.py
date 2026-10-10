from odoo.tests import HttpCase, tagged

from .common import create_cutting_data


@tagged('post_install', '-at_install')
class TestMeatCuttingUi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_cutting_data(cls)
        cls.loin.meat_piece = True

    def test_cutting_screen_tour(self):
        self.start_tour('/odoo/action-meat_cutting.meat_cutting_screen_action', 'meat_cutting_screen_tour', login='admin')
        session = self.env['meat.cutting.session'].search([('product_id', '=', self.carcass.id)])
        self.assertEqual(session.state, 'done')
        self.assertEqual(session.picking_id, self.receipt)
        self.assertEqual(session.bom_id, self.bom)
        self.assertAlmostEqual(session.line_ids.weight, 2.5)
        self.assertEqual(session.line_ids.label_product_name, 'Iberian Loin')
        self.assertEqual(session.line_ids.output_product_id, self.frozen_loin)
        self.assertEqual(session.unbuild_id.produce_line_ids.product_id - self.carcass, self.frozen_loin)
        self.assertEqual(session.label_report_id, self.env.ref('meat_cutting.action_report_meat_cutting_label'))
        self.assertEqual(session.unbuild_id.state, 'done')
        self.assertAlmostEqual(session.consumed_qty, 100)
        self.assertTrue(self.lot.crotal_id)
        # The frozen piece is in its package
        piece = session.line_ids.package_id
        self.assertTrue(piece.meat_piece)
        self.assertEqual(session.unbuild_id.produce_line_ids.move_line_ids.result_package_id, piece)
