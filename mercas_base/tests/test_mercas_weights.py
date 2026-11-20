from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMercasWeights(TransactionCase):
    """Goods weighed with their boxes: the quantity of the line is the net
    weight, the tare is the weight of its boxes (weight of the box product)
    and the gross weight the one of the scale. The invoice and the delivery
    note print them, with the packaging in a table of its own."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids += cls.env.ref("stock.group_tracking_lot")
        cls.customer = cls.env["res.partner"].create({"name": "Weights Customer"})
        cls.supplier = cls.env["res.partner"].create({"name": "Weights Supplier"})
        kg = cls.env.ref("uom.product_uom_kgm")
        cls.box = cls.env["product.product"].create({
            "name": "Weights Box", "is_storable": True, "is_box": True, "weight": 0.5, "list_price": 1.0,
        })
        cls.tomato = cls.env["product.product"].create({
            "name": "Weights Tomato", "is_storable": True, "uom_id": kg.id, "box_product_id": cls.box.id,
        })
        cls.euro_type = cls.env["stock.package.type"].create({
            "name": "Weights Europallet", "base_weight": 25.0, "mercas_is_pallet": True,
        })
        stock = cls.env.ref("stock.warehouse0").lot_stock_id
        cls.env["stock.quant"]._update_available_quantity(cls.tomato, stock, 1000.0)
        cls.env["stock.quant"]._update_available_quantity(cls.box, stock, 1000.0)

    def _sale(self, qty=100.0, boxes=10):
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [Command.create({
                "product_id": self.tomato.id, "product_uom_qty": qty, "box_qty": boxes, "price_unit": 2.0,
            })],
        })
        return order, order.order_line

    def test_tare_and_gross_weight(self):
        _order, line = self._sale()
        self.assertTrue(line.mercas_weighed)
        self.assertAlmostEqual(line.mercas_tare, 5.0)
        self.assertAlmostEqual(line.mercas_gross_weight, 105.0)
        # The scale: the gross weight sets the net one
        line.mercas_gross_weight = 111.0
        self.assertAlmostEqual(line.product_uom_qty, 106.0)
        # More boxes, more tare
        line.box_qty = 12
        self.assertAlmostEqual(line.mercas_tare, 6.0)
        # The tare weighed stays when the weight of the box changes afterwards
        self.box.weight = 0.7
        self.assertAlmostEqual(line.mercas_tare, 6.0)

    def test_gross_weight_on_purchase(self):
        order = self.env["purchase.order"].create({
            "partner_id": self.supplier.id,
            "order_line": [Command.create({
                "product_id": self.tomato.id, "product_qty": 50.0, "box_qty": 4, "price_unit": 1.0,
            })],
        })
        line = order.order_line
        self.assertAlmostEqual(line.mercas_tare, 2.0)
        line.mercas_gross_weight = 62.0
        self.assertAlmostEqual(line.product_qty, 60.0)

    def test_invoice_weights_and_packaging(self):
        order, line = self._sale()
        order.button_sold_and_sent()
        invoice = order.invoice_ids or order._create_invoices()
        goods = invoice.invoice_line_ids.filtered(lambda l: l.product_id == self.tomato)
        self.assertEqual(goods.box_qty, 10)
        self.assertAlmostEqual(goods.mercas_tare, 5.0)
        weights = invoice._mercas_invoice_weights()
        self.assertEqual(weights[goods.id], {"boxes": 10, "net": 100.0, "tare": 5.0, "gross": 105.0})
        # The packaging out of the lines of the goods, in its own table
        packaging = invoice._mercas_packaging_lines()
        self.assertIn(self.box, packaging.product_id)
        self.assertFalse(invoice._get_move_lines_to_report() & packaging)
        html = self.env["ir.actions.report"]._render_qweb_html("account.account_invoices", invoice.ids)[0].decode()
        self.assertIn("mercas_packaging_table", html)
        self.assertIn("105.00", html)

    def test_order_reports_weights(self):
        """ The sale order, the purchase order and the request for quotation print the same
        columns as the invoice. """
        order, line = self._sale()
        self.assertEqual(order._mercas_order_weights(), {
            line.id: {"boxes": 10, "net": 100.0, "tare": 5.0, "gross": 105.0},
        })
        Report = self.env["ir.actions.report"]
        html = Report._render_qweb_html("sale.action_report_saleorder", order.ids)[0].decode()
        self.assertIn("td_mercas_gross", html)
        self.assertIn("105.00", html)
        purchase = self.env["purchase.order"].create({
            "partner_id": self.supplier.id,
            "order_line": [Command.create({
                "product_id": self.tomato.id, "product_qty": 50.0, "box_qty": 4, "price_unit": 1.0,
            })],
        })
        for report in ("purchase.report_purchase_quotation", "purchase.action_report_purchase_order"):
            html = Report._render_qweb_html(report, purchase.ids)[0].decode()
            self.assertIn("td_mercas_gross", html, report)
            self.assertIn("52.00", html, report)
        # Without boxes nor tare, the standard columns
        line.box_qty = 0
        self.assertFalse(order._mercas_order_weights())
        html = Report._render_qweb_html("sale.action_report_saleorder", order.ids)[0].decode()
        self.assertNotIn("td_mercas_gross", html)

    def test_invoice_of_only_packaging(self):
        """ A return or a delivery of boxes only: they are the lines of the invoice. """
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.customer.id,
            "invoice_line_ids": [Command.create({"product_id": self.box.id, "quantity": 5, "price_unit": 1.0})],
        })
        self.assertFalse(invoice._mercas_packaging_lines())
        self.assertFalse(invoice._mercas_invoice_weights())

    def test_partial_invoice_in_proportion(self):
        _order, line = self._sale()
        vals = line._mercas_invoice_weight_vals(40.0)
        self.assertEqual(vals["box_qty"], 4)
        self.assertAlmostEqual(vals["mercas_tare"], 2.0)

    def test_delivery_weights_with_pallets(self):
        order, line = self._sale()
        order._mercas_set_pallets([
            {"package_type_id": self.euro_type.id, "lines": [{"sale_line_id": line.id, "box_qty": 7}]},
        ])
        order.button_sold_and_sent()
        picking = order.picking_ids
        self.assertEqual(picking.state, "done")
        weights = picking._mercas_delivery_weights()
        totals = weights["totals"]
        self.assertEqual((totals["boxes"], totals["pallets"]), (10, 1))
        self.assertAlmostEqual(totals["net"], 100.0)
        self.assertAlmostEqual(totals["box_tare"], 5.0)
        self.assertAlmostEqual(totals["pallet_tare"], 25.0)
        self.assertAlmostEqual(totals["gross"], 130.0)
        # The same gross weight as the packing list
        self.assertAlmostEqual(order._mercas_packing_list()["totals"]["gross"], totals["gross"])
        # The boxes of the line shared out among its move lines (on the pallet and loose)
        goods = picking.move_line_ids.filtered(lambda ml: ml.product_id == self.tomato)
        self.assertEqual(sorted(weights["lines"][ml.id]["boxes"] for ml in goods), [3, 7])
        self.assertEqual(weights["packaging"].product_id, self.box)
        # A pallet weighed counts with its weight
        order.mercas_pallet_ids.package_id.shipping_weight = 100.0
        self.assertAlmostEqual(picking._mercas_delivery_weights()["totals"]["gross"], 100.0 + 30.0 * 105.0 / 100.0)
        html = self.env["ir.actions.report"]._render_qweb_html("stock.action_report_delivery", picking.ids)[0].decode()
        self.assertIn("mercas_weights_table", html)
        self.assertIn("mercas_packaging_table", html)

    def test_share_out(self):
        share_out = self.env["stock.picking"]._mercas_share_out
        self.assertEqual(share_out(10, [60.0, 40.0]), [6, 4])
        self.assertEqual(sum(share_out(7, [1.0, 1.0, 1.0])), 7)
        self.assertEqual(share_out(0, [1.0, 2.0]), [0, 0])
