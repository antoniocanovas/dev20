from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMercasClassification(TransactionCase):
    """Quality and size of what is sold:

    - Goods bought in bulk: one product, with attributes that never create
      variants; the quality and the size are chosen on each sale line.
    - Goods bought already classified: a product whose variants are the
      quality.

    The sales report adds up both kinds by the name of the value.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.uom_kg = cls.env.ref("uom.product_uom_kgm")
        cls.supplier = cls.env["res.partner"].create({"name": "Bulk Supplier"})
        cls.customer = cls.env["res.partner"].create({"name": "Bulk Customer"})
        Attribute = cls.env["product.attribute"]
        cls.bulk_quality = Attribute.create({
            "name": "Bulk Quality",
            "create_variant": "no_variant",
            "mercas_role": "quality",
            "value_ids": [Command.create({"name": "Extra"}), Command.create({"name": "First"})],
        })
        cls.bulk_size = Attribute.create({
            "name": "Bulk Size",
            "create_variant": "no_variant",
            "mercas_role": "size",
            "value_ids": [Command.create({"name": "03"}), Command.create({"name": "04"})],
        })
        cls.variant_quality = Attribute.create({
            "name": "Classified Quality",
            "create_variant": "always",
            "mercas_role": "quality",
            "value_ids": [Command.create({"name": "Extra"}), Command.create({"name": "Second"})],
        })
        cls.bulk = cls.env["product.template"].create({
            "name": "Bulk Apple",
            "type": "consu",
            "is_storable": True,
            "tracking": "lot",
            "uom_id": cls.uom_kg.id,
            "taxes_id": [Command.clear()],
            "supplier_taxes_id": [Command.clear()],
            "attribute_line_ids": [
                Command.create({"attribute_id": cls.bulk_quality.id, "value_ids": [Command.set(cls.bulk_quality.value_ids.ids)]}),
                Command.create({"attribute_id": cls.bulk_size.id, "value_ids": [Command.set(cls.bulk_size.value_ids.ids)]}),
            ],
        })
        cls.classified = cls.env["product.template"].create({
            "name": "Classified Apple",
            "type": "consu",
            "uom_id": cls.uom_kg.id,
            "taxes_id": [Command.clear()],
            "attribute_line_ids": [
                Command.create({"attribute_id": cls.variant_quality.id, "value_ids": [Command.set(cls.variant_quality.value_ids.ids)]}),
            ],
        })
        cls.lot = cls.env["stock.lot"].create({
            "name": "LOTE-GRANEL",
            "product_id": cls.bulk.product_variant_id.id,
            "partner_id": cls.supplier.id,
        })
        purchase = cls.env["purchase.order"].create({
            "partner_id": cls.supplier.id,
            "order_line": [Command.create({
                "product_id": cls.bulk.product_variant_id.id,
                "product_qty": 100.0,
                "price_unit": 1.0,
                "lot_id": cls.lot.id,
            })],
        })
        purchase.button_purchase_and_receive()

    @classmethod
    def _ptav(cls, template, name, attribute):
        return template.attribute_line_ids.filtered(
            lambda line: line.attribute_id == attribute
        ).product_template_value_ids.filtered(lambda ptav: ptav.name == name)

    def _sell(self, product, qty, price, values=None, lot=None):
        sale = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [Command.create({
                "product_id": product.id,
                "product_uom_qty": qty,
                "price_unit": price,
                "lot_id": lot and lot.id,
                "product_no_variant_attribute_value_ids": [Command.set(values.ids if values else [])],
            })],
        })
        sale.button_sold_and_sent()
        return sale.order_line

    def _sell_bulk(self, qty, price, quality, size):
        values = self._ptav(self.bulk, quality, self.bulk_quality) | self._ptav(self.bulk, size, self.bulk_size)
        return self._sell(self.bulk.product_variant_id, qty, price, values, self.lot)

    def test_line_classification(self):
        line = self._sell_bulk(30.0, 2.0, "Extra", "03")
        self.assertEqual(line.mercas_quality, "Extra")
        self.assertEqual(line.mercas_size, "03")
        self.assertEqual(line._mercas_classification_text(), "Extra · 03")
        variant = self.classified.product_variant_ids.filtered(
            lambda product: product.product_template_attribute_value_ids.name == "Second"
        )
        line = self._sell(variant, 5.0, 1.0)
        self.assertEqual(line.mercas_quality, "Second", "The quality of the variant")
        self.assertFalse(line.mercas_size)

    def test_sales_report_adds_up_both_kinds(self):
        self._sell_bulk(30.0, 2.0, "Extra", "03")
        self._sell_bulk(20.0, 1.5, "First", "04")
        extra_variant = self.classified.product_variant_ids.filtered(
            lambda product: product.product_template_attribute_value_ids.name == "Extra"
        )
        self._sell(extra_variant, 10.0, 3.0)
        products = self.bulk.product_variant_id | self.classified.product_variant_ids
        groups = self.env["sale.report"]._read_group(
            [("product_id", "in", products.ids)], ["mercas_quality"], ["product_uom_qty:sum"],
        )
        self.assertEqual(dict(groups), {"Extra": 40.0, "First": 20.0})
        groups = self.env["sale.report"]._read_group(
            [("product_id", "in", products.ids)], ["mercas_size"], ["product_uom_qty:sum"],
        )
        self.assertEqual(dict(groups), {"03": 30.0, "04": 20.0, False: 10.0})

    def test_lot_breakdown(self):
        self.assertFalse(self.lot.mercas_sale_classification, "Nothing sold yet")
        self._sell_bulk(30.0, 2.0, "Extra", "03")
        self._sell_bulk(20.0, 1.0, "Extra", "03")
        self._sell_bulk(10.0, 1.5, "First", "04")
        self.lot.invalidate_recordset()
        self.assertEqual(self.lot._mercas_sale_classification_groups(), [
            {"quality": "Extra", "size": "03", "qty": 50.0, "amount": 80.0},
            {"quality": "First", "size": "04", "qty": 10.0, "amount": 15.0},
        ])
        html = str(self.lot.mercas_sale_classification)
        self.assertIn("Extra", html)
        self.assertIn("First", html)

    def test_lot_without_classification(self):
        self._sell(self.bulk.product_variant_id, 10.0, 1.0, lot=self.lot)
        self.lot.invalidate_recordset()
        self.assertFalse(self.lot.mercas_sale_classification, "No sale has quality or size")

    def test_settlement_breakdown_text(self):
        self._sell_bulk(30.0, 2.0, "Extra", "03")
        self._sell(self.bulk.product_variant_id, 10.0, 1.0, lot=self.lot)
        lines = self.lot._mercas_sale_breakdown_text().splitlines()
        self.assertTrue(lines[0].endswith("=> Extra · 03"), lines[0])
        self.assertNotIn("·", lines[1], "Nothing added without quality or size")
