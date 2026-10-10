from odoo import Command
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMeatCuttingPurchase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['res.config.settings'].create({'group_uom': True}).execute()
        cls.uom_kg = cls.env.ref('uom.product_uom_kgm')
        cls.slaughterhouse = cls.env['res.partner'].create({'name': 'Slaughterhouse'})
        # Carcasses are ordered by number, about 90 kg each, at 2.10 €/kg
        cls.uom_carcass = cls.env['uom.uom'].create({
            'name': 'Pork carcass', 'relative_factor': 90, 'relative_uom_id': cls.uom_kg.id})
        cls.carcass = cls.env['product.product'].create({
            'name': 'Pork Carcass',
            'type': 'consu',
            'is_storable': True,
            'tracking': 'lot',
            'meat_piece': True,
            'uom_id': cls.uom_kg.id,
            'uom_ids': [Command.set(cls.uom_carcass.ids)],
            'purchase_method': 'receive',
            'supplier_taxes_id': [Command.clear()],
            'seller_ids': [Command.create({'partner_id': cls.slaughterhouse.id, 'price': 2.10})],
        })

    def _purchase(self, carcasses):
        # As in the interface: the price of the vendor (per kg) is converted
        # when the unit changes
        order_form = Form(self.env['purchase.order'])
        order_form.partner_id = self.slaughterhouse
        with order_form.order_line.new() as line:
            line.product_id = self.carcass
            line.uom_id = self.uom_carcass
            line.product_qty = carcasses
        order = order_form.save()
        order.button_confirm()
        return order

    def _receive(self, order, weights):
        """ Register the carcasses of these weights and validate the receipt. """
        receipt = order.picking_ids
        action = receipt.action_register_carcasses()
        self.env[action['res_model']].with_context(action['context']).create({
            'line_ids': [Command.create({
                'product_id': self.carcass.id, 'name': f'ES{index:03}', 'weight': weight,
            }) for index, weight in enumerate(weights)],
        }).action_confirm()
        self.assertIs(receipt.button_validate(), True)
        return receipt

    def _bill(self, order):
        order.action_create_invoice()
        return order.invoice_ids.sorted('id')[-1]

    def test_bill_real_weight(self):
        order = self._purchase(3)
        line = order.order_line
        self.assertAlmostEqual(line.price_unit, 189.0, msg="The price of the estimated weight")
        self.assertEqual(order.picking_ids.move_ids.packaging_uom_id, self.uom_carcass)

        # Three carcasses ordered, 275.7 kg received: no backorder
        receipt = self._receive(order, [94.6, 89.3, 91.8])
        self.assertFalse(receipt.backorder_ids)
        self.assertAlmostEqual(line.qty_received, 3.06, msg="Rounded in the packaging unit")
        bill = self._bill(order)
        # Billed in kg: the real weight at the price per kg, without rounding
        self.assertEqual(bill.invoice_line_ids.product_uom_id, self.uom_kg)
        self.assertAlmostEqual(bill.invoice_line_ids.quantity, 275.7)
        self.assertAlmostEqual(bill.invoice_line_ids.price_unit, 2.10)
        self.assertAlmostEqual(bill.amount_untaxed, 578.97)
        self.assertEqual(line.qty_to_invoice, 0)
        self.assertEqual(order.invoice_status, 'invoiced')

    def test_lighter_carcasses(self):
        order = self._purchase(2)
        self._receive(order, [85.0, 88.0])
        self.assertAlmostEqual(self._bill(order).amount_untaxed, 363.3)
        self.assertEqual(order.invoice_status, 'invoiced')

    def test_ordered_in_kg(self):
        """ Lines ordered in the unit of the product keep the standard behaviour. """
        order = self.env['purchase.order'].create({
            'partner_id': self.slaughterhouse.id,
            'order_line': [Command.create({'product_id': self.carcass.id, 'product_qty': 180})],
        })
        order.button_confirm()
        self._receive(order, [94.6, 89.3])
        bill = self._bill(order)
        self.assertAlmostEqual(bill.invoice_line_ids.quantity, 183.9)
        self.assertAlmostEqual(bill.amount_untaxed, 386.19)

    def test_bill_after_return(self):
        order = self._purchase(2)
        receipt = self._receive(order, [94.6, 89.3])
        self._bill(order).write({'invoice_date': '2026-10-01'})
        order.invoice_ids.action_post()
        # The heavier carcass goes back to the slaughterhouse: refunded by its weight
        return_picking = receipt._create_return()
        return_picking.move_ids.product_uom_qty = 94.6
        return_picking.action_confirm()
        return_move = return_picking.move_ids
        return_move.move_line_ids.unlink()
        self.env['stock.move.line'].create({
            'move_id': return_move.id,
            'picking_id': return_picking.id,
            'product_id': self.carcass.id,
            'uom_id': self.uom_kg.id,
            'quantity': 94.6,
            'lot_id': receipt.move_line_ids.lot_id.filtered(lambda lot: lot.name == 'ES000').id,
            'location_id': return_move.location_id.id,
            'location_dest_id': return_move.location_dest_id.id,
        })
        return_move.picked = True
        return_picking.button_validate()
        self.assertEqual(return_picking.state, 'done')
        line = order.order_line
        self.assertAlmostEqual(line._get_qty_to_invoice_in_product_uom(), -94.6)
        refund = self._bill(order)
        self.assertEqual(refund.move_type, 'in_refund')
        self.assertAlmostEqual(refund.invoice_line_ids.quantity, 94.6)
        self.assertAlmostEqual(refund.amount_untaxed, 198.66)
