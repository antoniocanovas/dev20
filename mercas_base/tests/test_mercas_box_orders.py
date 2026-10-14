from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMercasBoxOrders(TransactionCase):
    """A purchase/sale order is detected as a box return/delivery by its
    content (every product line is a product marked as box/container,
    `product.template.is_box`), without needing a dedicated order type. The
    automated receive/deliver-and-invoice flow no longer triggers on
    confirm alone: it requires explicitly pressing the "Receive & Invoice"
    button, except in the shortcuts that are themselves already a
    "do it all now" action (Purchase & Receive, Sold & Sent)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.supplier = cls.env["res.partner"].create({"name": "Box Supplier"})
        cls.customer = cls.env["res.partner"].create({"name": "Box Customer"})

        cls.box_product = cls.env["product.product"].create({
            "name": "Test Box",
            "type": "consu",
            "is_box": True,
            "taxes_id": [Command.clear()],
            "supplier_taxes_id": [Command.clear()],
        })
        cls.produce = cls.env["product.product"].create({
            "name": "Test Apple",
            "type": "consu",
            "is_storable": True,
            "taxes_id": [Command.clear()],
            "supplier_taxes_id": [Command.clear()],
        })

    def _box_purchase(self):
        return self.env["purchase.order"].create({
            "partner_id": self.supplier.id,
            "order_line": [Command.create({
                "product_id": self.box_product.id,
                "product_qty": 10.0,
                "price_unit": 0.5,
            })],
        })

    def _box_sale(self):
        return self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [Command.create({
                "product_id": self.box_product.id,
                "product_uom_qty": 10.0,
                "price_unit": 0.5,
            })],
        })

    # --- Detection by content ---

    def test_purchase_is_box_return_when_all_lines_are_box_products(self):
        po = self._box_purchase()
        self.assertTrue(po.mercas_is_box_return)

    def test_purchase_is_not_box_return_when_mixed_lines(self):
        po = self._box_purchase()
        po.order_line = [Command.create({
            "product_id": self.produce.id,
            "product_qty": 5.0,
            "price_unit": 1.0,
        })]
        self.assertFalse(po.mercas_is_box_return)

    def test_purchase_is_not_box_return_when_empty(self):
        po = self.env["purchase.order"].create({"partner_id": self.supplier.id})
        self.assertFalse(po.mercas_is_box_return)

    def test_sale_is_box_delivery_when_all_lines_are_box_products(self):
        so = self._box_sale()
        self.assertTrue(so.mercas_is_box_delivery)

    def test_sale_is_not_box_delivery_when_mixed_lines(self):
        so = self._box_sale()
        so.order_line = [Command.create({
            "product_id": self.produce.id,
            "product_uom_qty": 5.0,
            "price_unit": 2.0,
        })]
        self.assertFalse(so.mercas_is_box_delivery)

    # --- Confirming no longer auto-invoices ---

    def test_purchase_button_confirm_does_not_auto_invoice_box_order(self):
        po = self._box_purchase()
        po.button_confirm()
        self.assertEqual(po.state, "purchase")
        self.assertFalse(po.invoice_ids)
        pending = po.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
        self.assertTrue(pending)

    def test_sale_action_confirm_does_not_auto_invoice_box_order(self):
        so = self._box_sale()
        so.action_confirm()
        self.assertEqual(so.state, "sale")
        self.assertFalse(so.invoice_ids)
        pending = so.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
        self.assertTrue(pending)

    # --- Explicit "Receive & Invoice" button ---

    def test_purchase_action_receive_and_invoice(self):
        po = self._box_purchase()
        po.button_confirm()
        po.action_mercas_box_receive_and_invoice()
        pending = po.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
        self.assertFalse(pending)
        posted_invoices = po.invoice_ids.filtered(lambda i: i.state == "posted")
        self.assertTrue(posted_invoices)

    def test_sale_action_deliver_and_invoice(self):
        so = self._box_sale()
        so.action_confirm()
        so.action_mercas_box_deliver_and_invoice()
        pending = so.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
        self.assertFalse(pending)
        posted_invoices = so.invoice_ids.filtered(lambda i: i.state == "posted")
        self.assertTrue(posted_invoices)

    # --- "Do it all now" shortcuts still process end to end ---

    def test_purchase_button_purchase_and_receive_still_processes_box_order(self):
        po = self._box_purchase()
        po.button_purchase_and_receive()
        pending = po.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
        self.assertFalse(pending)
        posted_invoices = po.invoice_ids.filtered(lambda i: i.state == "posted")
        self.assertTrue(posted_invoices)

    def test_sale_button_sold_and_sent_still_processes_box_order(self):
        so = self._box_sale()
        so.button_sold_and_sent()
        pending = so.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
        self.assertFalse(pending)
        posted_invoices = so.invoice_ids.filtered(lambda i: i.state == "posted")
        self.assertTrue(posted_invoices)

    # --- The "Deliver Boxes"/"Return Boxes" buttons require at least one
    #     product marked as a box ---

    def test_action_open_box_delivery_requires_a_box_product_configured(self):
        # Unmark any existing box product (not just this test's own), so
        # the check remains valid even if other box products were created
        # by another module installed at the same time (e.g. demo data).
        self.env["product.template"].search([("is_box", "=", True)]).is_box = False
        po = self.env["purchase.order"].create({"partner_id": self.supplier.id})
        with self.assertRaises(UserError):
            po.action_open_box_delivery()

    def test_action_open_box_return_requires_a_box_product_configured(self):
        self.env["product.template"].search([("is_box", "=", True)]).is_box = False
        so = self.env["sale.order"].create({"partner_id": self.customer.id})
        with self.assertRaises(UserError):
            so.action_open_box_return()

    # --- mercas_is_box_return/mercas_is_box_delivery are actually
    #     searchable (store=True fields, not just readable) ---

    def test_purchase_mercas_is_box_return_is_searchable(self):
        box_po = self._box_purchase()
        regular_po = self.env["purchase.order"].create({
            "partner_id": self.supplier.id,
            "order_line": [Command.create({
                "product_id": self.produce.id,
                "product_qty": 5.0,
                "price_unit": 1.0,
            })],
        })
        found = self.env["purchase.order"].search([("mercas_is_box_return", "=", True)])
        self.assertIn(box_po, found)
        self.assertNotIn(regular_po, found)

    def test_sale_mercas_is_box_delivery_is_searchable(self):
        box_so = self._box_sale()
        regular_so = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [Command.create({
                "product_id": self.produce.id,
                "product_uom_qty": 5.0,
                "price_unit": 2.0,
            })],
        })
        found = self.env["sale.order"].search([("mercas_is_box_delivery", "=", True)])
        self.assertIn(box_so, found)
        self.assertNotIn(regular_so, found)

    # --- "Deliver Boxes"/"Return Boxes" buttons on the contact form ---

    def test_partner_action_open_box_delivery_creates_sale_order(self):
        action = self.supplier.action_mercas_open_box_delivery()
        self.assertEqual(action["res_model"], "sale.order")
        new_so = self.env["sale.order"].browse(action["res_id"])
        self.assertEqual(new_so.partner_id, self.supplier)

    def test_partner_action_open_box_return_creates_purchase_order(self):
        action = self.customer.action_mercas_open_box_return()
        self.assertEqual(action["res_model"], "purchase.order")
        new_po = self.env["purchase.order"].browse(action["res_id"])
        self.assertEqual(new_po.partner_id, self.customer)

    def test_partner_box_buttons_require_a_box_product_configured(self):
        self.env["product.template"].search([("is_box", "=", True)]).is_box = False
        with self.assertRaises(UserError):
            self.supplier.action_mercas_open_box_delivery()
        with self.assertRaises(UserError):
            self.customer.action_mercas_open_box_return()
