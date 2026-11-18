from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFirmNegotiationDefault(TransactionCase):
    """The option "Firm Negotiation" of the company is the default of new
    contacts; the existing ones keep theirs."""

    def test_new_contacts_take_the_option_of_the_company(self):
        company = self.env.company
        company.mercas_firm_negotiation = False
        before = self.env["res.partner"].create({"name": "Supplier Before"})
        self.assertFalse(before.mercas_firm_negotiation)

        company.mercas_firm_negotiation = True
        after = self.env["res.partner"].create({"name": "Supplier After"})
        self.assertTrue(after.mercas_firm_negotiation)
        self.assertFalse(before.mercas_firm_negotiation, "Existing contacts keep their option")

        # Still editable on each contact
        unchecked = self.env["res.partner"].create({
            "name": "Supplier Unchecked",
            "mercas_firm_negotiation": False,
        })
        self.assertFalse(unchecked.mercas_firm_negotiation)

    def test_purchase_takes_the_option_of_the_supplier_company(self):
        """A purchase addressed to a contact of the supplier takes the option of
        the supplier, not the one the contact got when it was created."""
        self.env.company.mercas_firm_negotiation = False
        supplier = self.env["res.partner"].create({"name": "Firm Supplier", "is_company": True})
        self.env.company.mercas_firm_negotiation = True
        contact = self.env["res.partner"].create({"name": "Firm Contact", "parent_id": supplier.id})
        product = self.env["product.product"].create({"name": "Firm Product", "type": "consu"})
        order = self.env["purchase.order"].create({
            "partner_id": contact.id,
            "order_line": [(0, 0, {"product_id": product.id, "product_qty": 1, "price_unit": 1})],
        })
        self.assertFalse(order.order_line.mercas_firm_negotiation)

    def test_contacts_follow_their_company(self):
        """Contacts and addresses take the option of their company, also when
        it is not set and the company of Odoo sets it by default, and follow it
        when it changes on the company."""
        self.env.company.mercas_firm_negotiation = True
        supplier = self.env["res.partner"].create({
            "name": "Settlement Supplier",
            "is_company": True,
            "mercas_firm_negotiation": False,
        })
        contact = self.env["res.partner"].create({"name": "Settlement Contact", "parent_id": supplier.id})
        address = self.env["res.partner"].create({
            "name": "Settlement Warehouse",
            "parent_id": supplier.id,
            "type": "delivery",
        })
        self.assertFalse(contact.mercas_firm_negotiation)
        self.assertFalse(address.mercas_firm_negotiation)

        supplier.mercas_firm_negotiation = True
        self.assertTrue(contact.mercas_firm_negotiation)
        self.assertTrue(address.mercas_firm_negotiation)
        supplier.mercas_firm_negotiation = False
        self.assertFalse(contact.mercas_firm_negotiation)
        self.assertFalse(address.mercas_firm_negotiation)
