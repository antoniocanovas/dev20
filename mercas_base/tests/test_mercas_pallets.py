from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMercasPallets(TransactionCase):
    """The boxes of a sale are spread over pallets: each pallet is a package
    of the delivery, with the kg of each line in proportion to its boxes, and
    the packing list shows them with their net, tare and gross weight."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids += cls.env.ref("stock.group_tracking_lot")
        cls.customer = cls.env["res.partner"].create({"name": "Pallet Customer"})
        kg = cls.env.ref("uom.product_uom_kgm")
        # The weight of the box product is the tare of each box
        cls.box = cls.env["product.product"].create({"name": "Green Box", "type": "consu", "is_box": True, "weight": 0.5})
        cls.europallet = cls.env["product.product"].create({"name": "Europallet", "type": "consu", "is_box": True})
        PackageType = cls.env["stock.package.type"]
        cls.euro_type = PackageType.create({
            "name": "Europallet", "base_weight": 25.0, "mercas_is_pallet": True,
            "mercas_box_product_id": cls.europallet.id,
            "packaging_length": 1200.0, "width": 800.0, "height": 1500.0,
        })
        cls.single_type = PackageType.create({"name": "Single-use Pallet", "base_weight": 15.0, "mercas_is_pallet": True})
        products = cls.env["product.product"].create([
            {"name": "Tomato", "is_storable": True, "uom_id": kg.id, "box_product_id": cls.box.id},
            {"name": "Pepper", "is_storable": True, "uom_id": kg.id, "box_product_id": cls.box.id},
        ])
        cls.tomato, cls.pepper = products
        stock = cls.env.ref("stock.warehouse0").lot_stock_id
        cls.stock_location = stock
        for product in products:
            cls.env["stock.quant"]._update_available_quantity(product, stock, 1000.0)

    def test_packages_enabled(self):
        """ The install (post_init_hook) enables Inventory > Packages: the pallets are
        packages of the deliveries. """
        self.assertIn(self.env.ref("stock.group_tracking_lot"), self.env.ref("base.group_user").all_implied_ids)

    def test_expiration_dates_enabled(self):
        """ The install enables Inventory > Expiration Dates (product_expiry). """
        self.assertEqual(self.env['ir.module.module']._get('product_expiry').state, 'installed')
        self.assertIn('expiration_date', self.env['stock.lot']._fields)

    def _sale(self):
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [
                Command.create({"product_id": self.tomato.id, "product_uom_qty": 100.0, "box_qty": 10, "price_unit": 1.0}),
                Command.create({"product_id": self.pepper.id, "product_uom_qty": 30.0, "box_qty": 6, "price_unit": 2.0}),
            ],
        })
        self.tomato_line, self.pepper_line = order.order_line
        return order

    def _pallets(self, *pallets):
        """[(package type, [(line, boxes)])] as the screen sends them."""
        return [
            {
                "package_type_id": package_type.id,
                "lines": [{"sale_line_id": line.id, "box_qty": boxes} for line, boxes in lines],
            }
            for package_type, lines in pallets
        ]

    def _packed(self, line):
        """{package name or '': kg} of the delivered move lines of `line`."""
        result = {}
        for ml in line.move_ids.move_line_ids:
            if ml.quantity:
                key = ml.result_package_id.name or ""
                result[key] = result.get(key, 0.0) + ml.quantity
        return result

    def _corrections(self, order):
        return order.picking_ids.message_ids.filtered(
            lambda m: "The done move line has been corrected" in (m.body or "")
        )

    def _sell_on_two_pallets(self):
        order = self._sale()
        order._mercas_set_pallets(self._pallets(
            (self.euro_type, [(self.tomato_line, 6), (self.pepper_line, 6)]),
            (self.single_type, [(self.tomato_line, 4)]),
        ))
        order.button_sold_and_sent()
        self.assertEqual(order.picking_ids.state, "done")
        return order

    def test_delivery_goes_on_the_pallets(self):
        order = self._sell_on_two_pallets()
        first, second = order.mercas_pallet_ids
        self.assertEqual(first.package_id.package_type_id, self.euro_type)
        self.assertEqual(second.package_id.package_type_id, self.single_type)
        self.assertEqual(self._packed(self.tomato_line), {first.package_id.name: 60.0, second.package_id.name: 40.0})
        self.assertEqual(self._packed(self.pepper_line), {first.package_id.name: 30.0})
        customer_location = order.picking_ids.location_dest_id
        quants = self.env["stock.quant"].search([("package_id", "=", first.package_id.id)])
        self.assertEqual(quants.location_id, customer_location)
        self.assertAlmostEqual(sum(quants.mapped("quantity")), 90.0)
        # One returnable pallet: a line of envases, as the boxes
        pallet_line = order.order_line.filtered("mercas_pallet_box_line")
        self.assertEqual(pallet_line.product_id, self.europallet)
        self.assertEqual(pallet_line.product_uom_qty, 1.0)
        self.assertEqual(pallet_line.qty_delivered, 1.0)
        # Not a correction: the delivery has no log of changed lines
        self.assertFalse(self._corrections(order))

    def test_correction_after_the_delivery(self):
        order = self._sell_on_two_pallets()
        first = order.mercas_pallet_ids[0]
        stock_before = self.tomato.with_context(location=self.stock_location.id).qty_available
        mismatch = order._mercas_set_pallets([{
            "id": first.id,
            "package_type_id": self.single_type.id,
            "lines": [
                {"sale_line_id": self.tomato_line.id, "box_qty": 10},
                {"sale_line_id": self.pepper_line.id, "box_qty": 6},
            ],
        }])
        self.assertEqual(len(order.mercas_pallet_ids), 1)
        self.assertEqual(order.mercas_pallet_ids.package_id, first.package_id, "the pallet keeps its package")
        self.assertEqual(first.package_id.package_type_id, self.single_type)
        self.assertEqual(self._packed(self.tomato_line), {first.package_id.name: 100.0})
        self.assertEqual(self._packed(self.pepper_line), {first.package_id.name: 30.0})
        self.assertEqual(self.tomato.with_context(location=self.stock_location.id).qty_available, stock_before)
        quants = self.env["stock.quant"].search([
            ("product_id", "=", self.tomato.id), ("location_id", "=", order.picking_ids.location_dest_id.id),
            ("quantity", "!=", 0),
        ])
        self.assertEqual(quants.package_id, first.package_id)
        self.assertAlmostEqual(sum(quants.mapped("quantity")), 100.0)
        self.assertTrue(self._corrections(order), "a correction is logged on the delivery")
        # The europallet given is no longer on the sale: regularized as a box movement
        self.assertEqual(mismatch, [(self.europallet, 0, 1)])

    def test_loose_boxes_stay_without_package(self):
        order = self._sale()
        order._mercas_set_pallets(self._pallets((self.single_type, [(self.tomato_line, 7)])))
        order.button_sold_and_sent()
        package = order.mercas_pallet_ids.package_id
        self.assertEqual(self._packed(self.tomato_line), {package.name: 70.0, "": 30.0})
        self.assertEqual(self._packed(self.pepper_line), {"": 30.0})
        self.assertFalse(order.order_line.filtered("mercas_pallet_box_line"))

    def test_boxes_taken_off_the_last_pallets(self):
        order = self._sale()
        order._mercas_set_pallets(self._pallets(
            (self.euro_type, [(self.tomato_line, 6)]),
            (self.single_type, [(self.tomato_line, 4)]),
        ))
        self.tomato_line.box_qty = 5
        first, second = order.mercas_pallet_ids
        self.assertEqual(first.box_qty, 5)
        self.assertFalse(second.line_ids)

    def test_no_more_boxes_than_the_line(self):
        order = self._sale()
        with self.assertRaises(ValidationError):
            order._mercas_set_pallets(self._pallets(
                (self.euro_type, [(self.pepper_line, 4)]),
                (self.single_type, [(self.pepper_line, 3)]),
            ))

    def test_packing_list(self):
        order = self._sell_on_two_pallets()
        data = order._mercas_packing_list()
        first, second = data["pallets"]
        self.assertEqual(first["boxes"], 12)
        self.assertAlmostEqual(first["net"], 90.0)
        self.assertAlmostEqual(first["tare"], 25.0 + 12 * 0.5)
        self.assertAlmostEqual(first["gross"], 121.0)
        self.assertAlmostEqual(first["volume"], 1.2 * 0.8 * 1.5)
        self.assertAlmostEqual(second["gross"], 40.0 + 15.0 + 2.0)
        totals = data["totals"]
        self.assertEqual((totals["pallets"], totals["boxes"], totals["packages"]), (2, 16, 2))
        self.assertAlmostEqual(totals["net"], 130.0)
        self.assertAlmostEqual(totals["gross"], 130.0 + 40.0 + 8.0)
        self.assertEqual(data["returnable"], {self.europallet: 1})
        # A pallet weighed shows its weight
        second["pallet"].package_id.shipping_weight = 60.0
        self.assertAlmostEqual(order._mercas_packing_list()["pallets"][1]["gross"], 60.0)

        Report = self.env["ir.actions.report"]
        html = Report._render_qweb_html("mercas_base.action_report_mercas_packing_list", order.ids)[0]
        self.assertIn(first["name"], html.decode())
        html = Report._render_qweb_html("mercas_base.action_report_mercas_packing_list_picking", order.picking_ids.ids)[0]
        self.assertIn(order.name, html.decode())
        # Printed from the browser the report is looked up by its name (/report/pdf/<name>/<ids>):
        # the one of the delivery note must take the ids as pickings, not as sale orders
        picking_report = self.env.ref("mercas_base.action_report_mercas_packing_list_picking")
        self.assertEqual(Report._get_report(picking_report.report_name), picking_report)
        html = Report._render_qweb_html(picking_report.report_name, order.picking_ids.ids)[0]
        self.assertIn(order.name, html.decode())
