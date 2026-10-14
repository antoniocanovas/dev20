from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSaleOrderLineProductQtyDatetime(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({"name": "Cliente Pesado"})
        cls.product = cls.env["product.product"].create({
            "name": "Producto Pesado",
            "type": "consu",
        })

    def test_create_sets_datetime(self):
        before = fields.Datetime.now()
        sale = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [
                Command.create({
                    "product_id": self.product.id,
                    "product_uom_qty": 10.0,
                }),
            ],
        })
        after = fields.Datetime.now()
        self.assertTrue(sale.order_line.product_qty_datetime)
        self.assertTrue(before <= sale.order_line.product_qty_datetime <= after)

    def test_create_does_not_set_datetime_on_section_lines(self):
        sale = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [
                Command.create({
                    "display_type": "line_section",
                    "name": "Section",
                }),
            ],
        })
        self.assertFalse(sale.order_line.product_qty_datetime)

    def test_write_same_value_does_not_change_datetime(self):
        sale = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [
                Command.create({
                    "product_id": self.product.id,
                    "product_uom_qty": 10.0,
                }),
            ],
        })
        created_at = sale.order_line.product_qty_datetime
        sale.order_line.product_uom_qty = 10.0
        self.assertEqual(sale.order_line.product_qty_datetime, created_at)

    def test_write_different_value_updates_datetime(self):
        sale = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [
                Command.create({
                    "product_id": self.product.id,
                    "product_uom_qty": 10.0,
                }),
            ],
        })
        created_at = sale.order_line.product_qty_datetime

        before = fields.Datetime.now()
        sale.order_line.product_uom_qty = 25.0
        after = fields.Datetime.now()

        self.assertTrue(before <= sale.order_line.product_qty_datetime <= after)
        self.assertGreaterEqual(sale.order_line.product_qty_datetime, created_at)
