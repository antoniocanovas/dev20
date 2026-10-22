from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPurchaseBillUnion(TransactionCase):
    """Auto-Complete of the vendor bill: the purchase orders show their receipts,
    and are found by the name of the receipt or by the supplier's delivery note."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supplier = cls.env["res.partner"].create({"name": "Bill Union Supplier"})
        cls.product = cls.env["product.product"].create({
            "name": "Bill Union Product",
            "type": "consu",
            "is_storable": True,
        })
        cls.purchase = cls.env["purchase.order"].create({
            "partner_id": cls.supplier.id,
            "order_line": [Command.create({
                "product_id": cls.product.id,
                "product_qty": 10.0,
                "price_unit": 2.0,
            })],
        })
        cls.purchase.button_confirm()
        cls.receipt = cls.purchase.picking_ids
        cls.receipt.supplier_ref = "ALB-PROV-778"

    def _found(self, text):
        return self.env["purchase.bill.union"].search([("display_name", "ilike", text)]).purchase_order_id

    def test_receipts_of_the_purchase(self):
        union = self.env["purchase.bill.union"].search([("purchase_order_id", "=", self.purchase.id)])
        self.assertEqual(union.mercas_receipts, f"{self.receipt.name} (ALB-PROV-778)")
        self.assertIn(self.receipt.name, union.display_name)
        self.assertIn("ALB-PROV-778", union.with_context(formatted_display_name=True).display_name)

    def test_search_by_receipt_or_supplier_note(self):
        self.assertEqual(self._found("ALB-PROV-778"), self.purchase)
        self.assertEqual(self._found(self.receipt.name), self.purchase)
        self.assertEqual(self._found(self.purchase.name), self.purchase, "Still found by its own name")

    def test_receipt_without_supplier_note_and_cancelled(self):
        self.receipt.supplier_ref = False
        union = self.env["purchase.bill.union"].search([("purchase_order_id", "=", self.purchase.id)])
        self.assertEqual(union.mercas_receipts, self.receipt.name)
        self.receipt.action_cancel()
        union = self.env["purchase.bill.union"].search([("purchase_order_id", "=", self.purchase.id)])
        self.assertFalse(union.mercas_receipts, "A cancelled receipt isn't shown")
