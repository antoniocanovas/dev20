from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMeatCuttingSale(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['res.config.settings'].create({'group_uom': True}).execute()
        cls.uom_kg = cls.env.ref('uom.product_uom_kgm')
        # Whole loins are ordered by number, about 4.5 kg each, at 7.90 €/kg
        cls.uom_loin = cls.env['uom.uom'].create({
            'name': 'Whole loin', 'relative_factor': 4.5, 'relative_uom_id': cls.uom_kg.id})
        cls.loin = cls.env['product.product'].create({
            'name': 'Pork Loin',
            'type': 'consu',
            'is_storable': True,
            'tracking': 'lot',
            'meat_piece': True,
            'uom_id': cls.uom_kg.id,
            'uom_ids': [Command.set(cls.uom_loin.ids)],
            'list_price': 7.90,
            'invoice_policy': 'delivery',
            'taxes_id': [Command.clear()],
        })
        cls.chops = cls.env['product.product'].create({
            'name': 'Pork Chops',
            'type': 'consu',
            'is_storable': True,
            'uom_id': cls.uom_kg.id,
            'list_price': 6.40,
            'invoice_policy': 'delivery',
            'taxes_id': [Command.clear()],
        })
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        lot = cls.env['stock.lot'].create({'name': 'L001', 'product_id': cls.loin.id})
        Quant = cls.env['stock.quant']
        for weight in (4.63, 4.40, 4.30):
            package = cls.env['stock.package'].create({'meat_piece': True})
            Quant._update_available_quantity(cls.loin, cls.warehouse.lot_stock_id, weight, lot_id=lot, package_id=package)
        Quant._update_available_quantity(cls.chops, cls.warehouse.lot_stock_id, 10)
        cls.customer = cls.env['res.partner'].create({'name': 'Butcher'})

    def _sell(self, lines):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [Command.create({
                'product_id': product.id,
                'product_uom_id': uom.id,
                'product_uom_qty': qty,
            }) for product, uom, qty in lines],
        })
        order.action_confirm()
        return order

    def _deliver(self, order, weights):
        """ Deliver the pieces of these weights, and the chops as reserved. """
        delivery = order.picking_ids
        loin_move = delivery.move_ids.filtered(lambda m: m.product_id == self.loin)
        loin_move.move_line_ids.unlink()
        quants = self.env['stock.quant'].search([
            ('product_id', '=', self.loin.id), ('location_id', '=', self.warehouse.lot_stock_id.id)])
        self.env['stock.move.line'].create([{
            'move_id': loin_move.id,
            'picking_id': delivery.id,
            'product_id': self.loin.id,
            'uom_id': self.uom_kg.id,
            'quantity': quant.quantity,
            'lot_id': quant.lot_id.id,
            'package_id': quant.package_id.id,
            'result_package_id': quant.package_id.id,
            'location_id': quant.location_id.id,
            'location_dest_id': loin_move.location_dest_id.id,
        } for quant in quants.filtered(lambda q: q.quantity in weights)])
        delivery.move_ids.picked = True
        self.assertIs(delivery.with_context(skip_sms=True).button_validate(), True)
        return delivery

    def test_invoice_real_weight(self):
        order = self._sell([(self.loin, self.uom_loin, 1), (self.chops, self.uom_kg, 3)])
        loin_line, chops_line = order.order_line
        self.assertAlmostEqual(loin_line.price_unit, 35.55, msg="The price of the estimated weight")
        self.assertEqual(order.picking_ids.move_ids[0].packaging_uom_id, self.uom_loin)

        self._deliver(order, [4.63])
        self.assertAlmostEqual(loin_line.qty_delivered, 1.03, msg="Rounded in the packaging unit")
        invoice = order._create_invoices()
        loin_invoice_line = invoice.invoice_line_ids.filtered(lambda l: l.product_id == self.loin)
        chops_invoice_line = invoice.invoice_line_ids - loin_invoice_line
        # Invoiced in kg: the real weight at the price per kg, without rounding
        self.assertEqual(loin_invoice_line.product_uom_id, self.uom_kg)
        self.assertAlmostEqual(loin_invoice_line.quantity, 4.63)
        self.assertAlmostEqual(loin_invoice_line.price_unit, 7.90)
        self.assertAlmostEqual(loin_invoice_line.price_subtotal, 36.58)
        # Lines ordered in the unit of the product keep the standard behaviour
        self.assertEqual(chops_invoice_line.product_uom_id, self.uom_kg)
        self.assertAlmostEqual(chops_invoice_line.quantity, 3)
        self.assertAlmostEqual(chops_invoice_line.price_unit, 6.40)

        self.assertAlmostEqual(loin_line.qty_invoiced, 1.03)
        self.assertEqual(loin_line.qty_to_invoice, 0)
        self.assertEqual(order.invoice_status, 'invoiced')

    def test_lighter_pieces(self):
        order = self._sell([(self.loin, self.uom_loin, 2)])
        self._deliver(order, [4.40, 4.30])
        # The two pieces ordered weigh 0.3 kg less than estimated
        invoice = order._create_invoices()
        self.assertAlmostEqual(invoice.invoice_line_ids.quantity, 8.70)
        self.assertAlmostEqual(invoice.amount_untaxed, 68.73)
        self.assertEqual(order.invoice_status, 'invoiced')

    def test_invoice_after_return(self):
        order = self._sell([(self.loin, self.uom_loin, 1)])
        delivery = self._deliver(order, [4.63])
        order._create_invoices().action_post()
        # The customer returns the piece: the credit note is the real weight
        return_picking = delivery._create_return()
        return_picking.action_return_all()
        return_picking.action_confirm()
        return_move = return_picking.move_ids
        return_move.move_line_ids.unlink()
        self.env['stock.move.line'].create({
            'move_id': return_move.id,
            'picking_id': return_picking.id,
            'product_id': self.loin.id,
            'uom_id': self.uom_kg.id,
            'quantity': 4.63,
            'lot_id': delivery.move_line_ids.lot_id.id,
            'location_id': return_move.location_id.id,
            'location_dest_id': return_move.location_dest_id.id,
        })
        return_move.picked = True
        return_picking.button_validate()
        self.assertEqual(return_picking.state, 'done')
        line = order.order_line
        self.assertAlmostEqual(line._get_qty_to_invoice_in_product_uom(), -4.63)
        credit_note = order._create_invoices(final=True)
        self.assertEqual(credit_note.move_type, 'out_refund')
        self.assertAlmostEqual(credit_note.invoice_line_ids.quantity, 4.63)
        self.assertAlmostEqual(credit_note.amount_untaxed, 36.58)
