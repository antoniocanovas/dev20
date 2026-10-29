from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSelfBilling(TransactionCase):
    """Suppliers whose invoices we issue: their bills go to the self-billing
    journal of the company, numbered by supplier, with the number as vendor
    reference."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.journal = cls.company.mercas_self_billing_journal_id
        cls.self_billed = cls.env["res.partner"].create({
            "name": "Self-Billed Supplier",
            "is_company": True,
            "mercas_self_billing": True,
        })
        cls.contact = cls.env["res.partner"].create({"name": "Its Contact", "parent_id": cls.self_billed.id})
        cls.supplier = cls.env["res.partner"].create({"name": "Usual Supplier", "is_company": True})
        cls.product = cls.env["product.product"].create({
            "name": "Self-Billing Product",
            "type": "service",
            "purchase_method": "purchase",
            "supplier_taxes_id": [Command.clear()],
        })

    def _bill(self, partner, **vals):
        return self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": partner.id,
            "invoice_date": "2026-10-15",
            "invoice_line_ids": [Command.create({"product_id": self.product.id, "quantity": 1, "price_unit": 10.0})],
            **vals,
        })

    def test_journal_of_the_company(self):
        self.assertTrue(self.journal)
        self.assertEqual(self.journal.type, "purchase")
        self.assertTrue(self.journal.is_self_billing)
        default = self.env["account.move"].with_context(default_move_type="in_invoice").new({}).journal_id
        self.assertFalse(default.is_self_billing, "It's never the default purchase journal")
        self.env["res.company"]._mercas_setup_self_billing_journal()
        self.assertEqual(self.company.mercas_self_billing_journal_id, self.journal, "Run again, it's kept")

    def test_bills_go_to_the_self_billing_journal(self):
        self.assertEqual(self._bill(self.self_billed).journal_id, self.journal)
        self.assertEqual(self._bill(self.contact).journal_id, self.journal, "Of its contacts as well")
        self.assertFalse(self._bill(self.supplier).journal_id.is_self_billing)
        refund = self._bill(self.self_billed, move_type="in_refund")
        self.assertEqual(refund.journal_id, self.journal)

        purchase = self.env["purchase.order"].create({
            "partner_id": self.self_billed.id,
            "order_line": [Command.create({"product_id": self.product.id, "product_qty": 2, "price_unit": 5.0})],
        })
        purchase.button_confirm()
        purchase.action_create_invoice()
        self.assertEqual(purchase.invoice_ids.journal_id, self.journal)

    def test_supplier_chosen_by_hand(self):
        with Form(self.env["account.move"].with_context(default_move_type="in_invoice")) as bill:
            bill.partner_id = self.self_billed
            self.assertEqual(bill.journal_id, self.journal)
            bill.partner_id = self.supplier
            self.assertFalse(bill.journal_id.is_self_billing)

    def test_number_by_supplier_as_vendor_reference(self):
        bill = self._bill(self.self_billed)
        bill.action_post()
        self.assertTrue(bill.name.startswith(self.journal.code + str(self.self_billed.id).zfill(5)))
        self.assertEqual(bill.ref, bill.name)
        given = self._bill(self.self_billed, ref="SUP-1")
        given.action_post()
        self.assertEqual(given.ref, "SUP-1", "A reference already given is kept")

    def test_only_suppliers_with_self_billing(self):
        bill = self._bill(self.supplier, journal_id=self.journal.id)
        with self.assertRaises(UserError):
            bill.action_post()

    def test_report(self):
        bill = self._bill(self.self_billed)
        bill.action_post()
        html = self.env["ir.actions.report"]._render_qweb_html("account.report_invoice", bill.ids)[0].decode()
        self.assertIn("mercas_self_billing_issuer", html)
        self.assertIn(self.self_billed.name, html)
        usual = self._bill(self.supplier)
        usual.action_post()
        html = self.env["ir.actions.report"]._render_qweb_html("account.report_invoice", usual.ids)[0].decode()
        self.assertNotIn("mercas_self_billing_issuer", html)
