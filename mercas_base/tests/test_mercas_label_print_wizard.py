from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMercasLabelPrintWizard(TransactionCase):
    """Purchase 100 kg of banana (10 boxes) and 200 kg of pear (15 boxes):
    the wizard must propose 10 banana labels and 15 pear labels, without
    including the container line or service-type products."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.supplier = cls.env["res.partner"].create({"name": "Label Supplier"})
        cls.uom_kg = cls.env.ref("uom.product_uom_kgm")

        cls.box_product = cls.env["product.product"].create({
            "name": "Test Box",
            "type": "consu",
            "is_box": True,
        })
        cls.platano = cls.env["product.product"].create({
            "name": "Banana",
            "type": "consu",
            "is_storable": True,
            "uom_id": cls.uom_kg.id,
        })
        cls.pera = cls.env["product.product"].create({
            "name": "Pear",
            "type": "consu",
            "is_storable": True,
            "uom_id": cls.uom_kg.id,
        })
        cls.service_product = cls.env["product.product"].create({
            "name": "Transport",
            "type": "service",
        })

        cls.purchase = cls.env["purchase.order"].create({
            "partner_id": cls.supplier.id,
            "order_line": [
                Command.create({
                    "product_id": cls.platano.id,
                    "product_qty": 100.0,
                    "uom_id": cls.uom_kg.id,
                    "price_unit": 1.0,
                    "box_qty": 10,
                    "box_product_id": cls.box_product.id,
                }),
                Command.create({
                    "product_id": cls.pera.id,
                    "product_qty": 200.0,
                    "uom_id": cls.uom_kg.id,
                    "price_unit": 1.5,
                    "box_qty": 15,
                    "box_product_id": cls.box_product.id,
                }),
                Command.create({
                    "product_id": cls.service_product.id,
                    "product_qty": 1.0,
                    "price_unit": 20.0,
                }),
            ],
        })
        cls.purchase.button_confirm()

    def _create_wizard(self):
        Wizard = self.env["mercas.label.print.wizard"]
        return Wizard.with_context(default_purchase_id=self.purchase.id).create({})

    def test_proposes_boxes_from_purchase_lines(self):
        # The confirm flow auto-creates a box line for the "Caja test" product;
        # it must not show up as a candidate to label.
        box_line = self.purchase.order_line.filtered(
            lambda l: l.product_id == self.box_product and l.box_purchase_line_id
        )
        self.assertTrue(box_line)

        wizard = self._create_wizard()
        proposed = {line.product_id: line.quantity for line in wizard.line_ids}
        self.assertEqual(proposed, {self.platano: 10, self.pera: 15})
        self.assertNotIn(self.box_product, proposed)
        self.assertNotIn(self.service_product, proposed)

    def test_print_uses_edited_quantities(self):
        wizard = self._create_wizard()
        platano_line = wizard.line_ids.filtered(lambda l: l.product_id == self.platano)
        platano_line.quantity = 3  # only replace 3 broken labels

        action = wizard.action_print()
        self.assertEqual(action["type"], "ir.actions.report")
        self.assertEqual(action["report_name"], "mercas_base.report_mercas_box_label")
        quantity_by_product = {
            product_id: qty for product_id, _lot_id, qty in action["data"]["labels"]
        }
        self.assertEqual(quantity_by_product[self.platano.id], 3)
        self.assertEqual(quantity_by_product[self.pera.id], 15)

    def test_labels_carry_lot(self):
        lot = self.env["stock.lot"].create({
            "name": "LBL-001",
            "product_id": self.platano.id,
            "company_id": self.company.id,
        })
        self.purchase.order_line.filtered(
            lambda l: l.product_id == self.platano
        ).lot_id = lot

        wizard = self._create_wizard()
        platano_line = wizard.line_ids.filtered(lambda l: l.product_id == self.platano)
        self.assertEqual(platano_line.lot_id, lot)

        action = wizard.action_print()
        self.assertIn([self.platano.id, lot.id, 10], action["data"]["labels"])

        values = self.env["report.mercas_base.report_mercas_box_label"]._get_report_values(
            None, action["data"]
        )
        # 10 banana + 15 pear boxes, one label each; default format is 2x7
        # (14 per page) -> 2 pages.
        self.assertEqual(len(values["labels"]), 25)
        self.assertEqual(len(values["pages"]), 2)
        banana_labels = [l for l in values["labels"] if l["lot"] == lot]
        self.assertEqual(len(banana_labels), 10)
        self.assertEqual(banana_labels[0]["barcode"], "LBL-001")

    def test_dymo_uses_dymo_report(self):
        wizard = self._create_wizard()
        wizard.print_format = "dymo"
        action = wizard.action_print()
        self.assertEqual(action["report_name"], "mercas_base.report_mercas_box_label_dymo")

    def test_print_requires_positive_quantity(self):
        wizard = self._create_wizard()
        wizard.line_ids.quantity = 0
        with self.assertRaises(UserError):
            wizard.action_print()

    def test_proposes_boxes_from_sale_lines(self):
        customer = self.env["res.partner"].create({"name": "Label Customer"})
        sale = self.env["sale.order"].create({
            "partner_id": customer.id,
            "order_line": [
                Command.create({
                    "product_id": self.platano.id,
                    "product_uom_qty": 50.0,
                    "product_uom_id": self.uom_kg.id,
                    "price_unit": 2.0,
                    "box_qty": 5,
                    "box_product_id": self.box_product.id,
                }),
            ],
        })
        sale.action_confirm()

        wizard = self.env["mercas.label.print.wizard"].with_context(
            default_sale_id=sale.id
        ).create({})
        proposed = {line.product_id: line.quantity for line in wizard.line_ids}
        self.assertEqual(proposed, {self.platano: 5})

    def test_reprint_from_lots(self):
        """Reprinting from the lots: as many labels as boxes were bought of
        each lot, or one when no purchase tells."""
        lot = self.env["stock.lot"].create({
            "name": "LBL-REPRINT",
            "product_id": self.platano.id,
            "company_id": self.company.id,
        })
        self.purchase.order_line.filtered(
            lambda l: l.product_id == self.platano
        ).lot_id = lot
        loose = self.env["stock.lot"].create({
            "name": "LBL-LOOSE",
            "product_id": self.pera.id,
            "company_id": self.company.id,
        })
        action = (lot | loose).action_print_mercas_labels()
        self.assertEqual(action["res_model"], "mercas.label.print.wizard")
        wizard = self.env["mercas.label.print.wizard"].with_context(action["context"]).create({})
        proposed = {line.lot_id: line.quantity for line in wizard.line_ids}
        self.assertEqual(proposed, {lot: 10, loose: 1})
        self.assertIn([self.platano.id, lot.id, 10], wizard.action_print()["data"]["labels"])
