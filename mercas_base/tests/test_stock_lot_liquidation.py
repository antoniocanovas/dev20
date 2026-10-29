from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestStockLotLiquidation(TransactionCase):
    """Scenario:

    Estimated purchase of 2000 kg at 1 $/kg. 1000 kg are sold at 2 $/kg and
    200 kg are scrapped (10% margin). With 800 kg still in stock, an advance
    is invoiced to the supplier on what was sold + scrapped so far. The rest
    is sold (800 kg at 1.4 $/kg), the lot is completed, and the total is
    settled, deducting the advance already invoiced.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.supplier = cls.env["res.partner"].create({"name": "Settlement Supplier"})
        cls.customer = cls.env["res.partner"].create({"name": "Settlement Customer"})
        cls.uom_kg = cls.env.ref("uom.product_uom_kgm")
        cls.product = cls.env["product.product"].create({
            "name": "Settlement Product",
            "type": "consu",
            "is_storable": True,
            "tracking": "lot",
            "uom_id": cls.uom_kg.id,
            "taxes_id": [Command.clear()],
            "supplier_taxes_id": [Command.clear()],
        })
        cls.lot = cls.env["stock.lot"].create({
            "name": "LOTE-LIQ-TEST",
            "product_id": cls.product.id,
            "company_id": cls.company.id,
            "partner_id": cls.supplier.id,
            "mercas_margin": 10.0,
        })

        purchase = cls.env["purchase.order"].create({
            "partner_id": cls.supplier.id,
            "order_line": [Command.create({
                "product_id": cls.product.id,
                "product_qty": 2000.0,
                "uom_id": cls.uom_kg.id,
                "price_unit": 1.0,
                "lot_id": cls.lot.id,
            })],
        })
        purchase.button_purchase_and_receive()
        cls.purchase = purchase

        cls.manager_user = cls.env["res.users"].create({
            "name": "Accounting Manager",
            "login": "mercas_test_account_manager",
            "email": "mercas_test_account_manager@example.com",
            "group_ids": [
                Command.link(cls.env.ref("account.group_account_manager").id),
                Command.link(cls.env.ref("stock.group_stock_user").id),
                Command.link(cls.env.ref("purchase.group_purchase_user").id),
            ],
        })
        cls.regular_user = cls.env["res.users"].create({
            "name": "User Without Permission",
            "login": "mercas_test_regular_user",
            "email": "mercas_test_regular_user@example.com",
            "group_ids": [
                Command.link(cls.env.ref("stock.group_stock_manager").id),
                Command.link(cls.env.ref("purchase.group_purchase_manager").id),
            ],
        })

    def _sell(self, qty, price_unit):
        sale = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [Command.create({
                "product_id": self.product.id,
                "product_uom_qty": qty,
                "product_uom_id": self.uom_kg.id,
                "price_unit": price_unit,
                "lot_id": self.lot.id,
            })],
        })
        sale.button_sold_and_sent()
        return sale

    def _scrap(self, qty):
        scrap = self.env["stock.move"].create({
            "is_scrap": True,
            "product_id": self.product.id,
            "lot_ids": self.lot.ids,
            "quantity": qty,
            "uom_id": self.uom_kg.id,
            "location_id": self.env.ref("stock.stock_location_stock").id,
            "location_dest_id": self.env.company.scrap_location_id.id,
        })
        scrap.action_scrap()
        return scrap

    def test_liquidation_with_advance_then_final_settlement(self):
        lot = self.lot
        self.assertAlmostEqual(lot.purchase_kg, 2000.0, places=2)
        self.assertFalse(lot.mercas_firm_negotiation)

        self._sell(1000.0, 2.0)
        self._scrap(200.0)

        self.assertAlmostEqual(lot.sale_kg, 1000.0, places=2)
        self.assertAlmostEqual(lot.sale_amount, 2000.0, places=2)
        self.assertAlmostEqual(lot.scrap_kg, 200.0, places=2)
        self.assertFalse(lot.completed)
        self.assertTrue(lot.invoiceable)

        gross_qty, gross_price, gross_amount = lot._mercas_liquidation_gross()
        self.assertAlmostEqual(gross_qty, 1200.0, places=2)
        self.assertAlmostEqual(gross_price, 1.5, places=4)
        self.assertAlmostEqual(gross_amount, 1800.0, places=2)

        action = lot.action_create_supplier_invoices()
        advance_invoice = self.env["account.move"].browse(action["res_id"])
        self.assertEqual(len(advance_invoice.invoice_line_ids), 1)
        self.assertAlmostEqual(advance_invoice.invoice_line_ids.quantity, 1200.0, places=2)
        self.assertAlmostEqual(advance_invoice.invoice_line_ids.price_unit, 1.5, places=4)
        self.assertAlmostEqual(advance_invoice.amount_total, 1800.0, places=2)

        advance_invoice.action_post()
        self.assertAlmostEqual(lot.net_invoiced_amount, 1800.0, places=2)
        self.assertFalse(lot.invoiced)
        # What's resolved so far (1000 sold + 200 scrapped) is already
        # covered by the advance: there's nothing else to invoice yet.
        self.assertFalse(lot.invoiceable)

        self._sell(800.0, 1.4)

        self.assertTrue(lot.completed)
        self.assertAlmostEqual(lot.sale_kg, 1800.0, places=2)
        self.assertAlmostEqual(lot.sale_amount, 3120.0, places=2)
        self.assertAlmostEqual(lot.supplier_amount, 2808.0, places=2)
        self.assertAlmostEqual(lot.supplier_price_kg, 1.404, places=4)
        self.assertTrue(lot.invoiceable)

        action = lot.action_create_supplier_invoices()
        final_invoice = self.env["account.move"].browse(action["res_id"])
        self.assertEqual(len(final_invoice.invoice_line_ids), 2)
        gross_line = final_invoice.invoice_line_ids.filtered(lambda l: l.price_unit > 0)
        deduction_line = final_invoice.invoice_line_ids - gross_line
        self.assertAlmostEqual(gross_line.quantity, 2000.0, places=2)
        self.assertAlmostEqual(gross_line.price_unit, 1.404, places=4)
        self.assertAlmostEqual(gross_line.price_subtotal, 2808.0, places=2)
        self.assertAlmostEqual(deduction_line.quantity, 1.0, places=2)
        self.assertAlmostEqual(deduction_line.price_unit, -1800.0, places=2)
        self.assertAlmostEqual(final_invoice.amount_total, 1008.0, places=2)

        final_invoice.action_post()
        self.assertAlmostEqual(lot.net_invoiced_amount, 2808.0, places=2)
        self.assertTrue(lot.invoiced)
        self.assertFalse(lot.invoiceable)

        total_paid = advance_invoice.amount_total + final_invoice.amount_total
        self.assertAlmostEqual(total_paid, lot.supplier_amount, places=2)
        self.assertAlmostEqual(total_paid, 2808.0, places=2)

    def test_liquidation_advance_amount_independent_of_scrap(self):
        """An advance's amount depends only on what was sold (net of
        margin), never on scrap: on the same lot and the same sales,
        increasing scrap must not change the gross amount, only spread it
        over a lower price/kg."""
        lot = self.lot
        self._sell(1000.0, 2.0)

        self._scrap(200.0)
        qty_1, price_1, amount_1 = lot._mercas_liquidation_gross()
        self.assertAlmostEqual(amount_1, 1800.0, places=2)
        self.assertAlmostEqual(qty_1, 1200.0, places=2)
        self.assertAlmostEqual(price_1, 1.5, places=4)

        self._scrap(600.0)
        qty_2, price_2, amount_2 = lot._mercas_liquidation_gross()
        self.assertAlmostEqual(amount_2, amount_1, places=2)
        self.assertAlmostEqual(qty_2, 1800.0, places=2)
        self.assertAlmostEqual(price_2, 1.0, places=4)
        self.assertLess(price_2, price_1)

    def test_standard_bill_leaves_out_lot_lines(self):
        """The lines with a lot are invoiced from the lot: the standard bill
        of the purchase, and the one loaded from it, only take the others."""
        with self.assertRaises(UserError):
            self.purchase.action_create_invoice()

        transport = self.env["product.product"].create({
            "name": "Settlement Transport",
            "type": "service",
            "purchase_method": "purchase",
            "supplier_taxes_id": [Command.clear()],
        })
        self.purchase.order_line = [Command.create({
            "product_id": transport.id,
            "product_qty": 1.0,
            "price_unit": 50.0,
        })]
        lot_line = self.purchase.order_line.filtered("lot_id")
        transport_line = self.purchase.order_line.filtered(lambda l: l.product_id == transport)
        self.assertEqual(self.purchase._mercas_standard_bill_lines(), transport_line)

        loaded = self.env["account.move"].new({"move_type": "in_invoice", "partner_id": self.supplier.id})
        loaded._add_purchase_order_lines(self.purchase.order_line)
        self.assertNotIn(lot_line, loaded.invoice_line_ids.purchase_line_id)
        self.assertIn(transport_line, loaded.invoice_line_ids.purchase_line_id)

        self.purchase.action_create_invoice()
        bill = self.purchase.invoice_ids
        self.assertEqual(len(bill), 1)
        self.assertEqual(bill.invoice_line_ids.filtered("product_id").purchase_line_id, transport_line)
        self.assertEqual(bill.amount_total, 50.0)
        self.assertFalse(self.lot.supplier_invoice_line_ids, "The lot stays to invoice from the lot")

    def test_empty_lines_alert_ignores_sections(self):
        """The sections of a bill (at 0) aren't empty lines to remove."""
        bill = self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": self.supplier.id,
            "invoice_line_ids": [
                Command.create({"display_type": "line_section", "name": "PRODUCTOS"}),
                Command.create({"product_id": self.product.id, "quantity": 5, "price_unit": 2.0}),
                Command.create({"display_type": "line_section", "name": "Envases"}),
            ],
        })
        self.assertNotIn("account_remove_empty_lines", bill.alerts or {})
        bill.invoice_line_ids = [
            Command.create({"product_id": self.product.id, "quantity": 0, "price_unit": 2.0}),
            Command.create({"product_id": self.product.id, "quantity": 1, "price_unit": 0.0}),
        ]
        alert = bill.alerts["account_remove_empty_lines"]
        empty = bill.invoice_line_ids.filtered(lambda l: l.display_type == "product" and not l.price_total)
        self.assertEqual(sorted(alert["action_call"][2]), sorted(empty.ids))

    def test_firm_negotiation_access_control(self):
        """Only an Accounting Manager can change the firm negotiation, and
        nobody can do it once the lot has firm invoicing recorded."""
        lot = self.lot
        with self.assertRaises(UserError):
            lot.with_user(self.regular_user).write({"mercas_firm_negotiation": True})

        lot.with_user(self.manager_user).write({"mercas_firm_negotiation": True})
        self.assertTrue(lot.mercas_firm_negotiation)

        lot.with_user(self.manager_user).write({"mercas_firm_negotiation": False})
        self.assertFalse(lot.mercas_firm_negotiation)

    def test_firm_negotiation_after_advance_deducts_prior_settlement(self):
        """It's possible to switch to firm negotiation even if the lot
        already has a sale-settlement advance invoiced: the first firm
        invoice deducts that advance with a deduction line, without
        touching the main line's purchase price. Once there is firm
        invoicing, it's no longer possible to go back to sale settlement."""
        lot = self.lot
        self._sell(1000.0, 2.0)

        advance_action = lot.action_create_supplier_invoices()
        advance_invoice = self.env["account.move"].browse(advance_action["res_id"])
        advance_invoice.action_post()
        self.assertAlmostEqual(lot.net_invoiced_amount, 1800.0, places=2)
        self.assertFalse(lot.mercas_firm_negotiation)

        lot.with_user(self.manager_user).write({"mercas_firm_negotiation": True})
        self.assertTrue(lot.invoiceable)

        firm_action = lot.action_create_supplier_invoices()
        firm_invoice = self.env["account.move"].browse(firm_action["res_id"])
        self.assertEqual(len(firm_invoice.invoice_line_ids), 2)
        supply_line = firm_invoice.invoice_line_ids.filtered("mercas_is_firm_line")
        deduction_line = firm_invoice.invoice_line_ids - supply_line
        self.assertAlmostEqual(supply_line.quantity, 2000.0, places=2)
        self.assertAlmostEqual(supply_line.price_unit, 1.0, places=4)
        self.assertAlmostEqual(supply_line.price_subtotal, 2000.0, places=2)
        self.assertAlmostEqual(deduction_line.quantity, 1.0, places=2)
        self.assertAlmostEqual(deduction_line.price_unit, -1800.0, places=2)
        self.assertAlmostEqual(firm_invoice.amount_total, 200.0, places=2)

        firm_invoice.action_post()
        self.assertAlmostEqual(lot.net_invoiced_kg, 2000.0, places=2)
        self.assertTrue(lot.invoiced)
        self.assertFalse(lot.invoiceable)

        total_paid = advance_invoice.amount_total + firm_invoice.amount_total
        self.assertAlmostEqual(total_paid, 2000.0, places=2)
        self.assertAlmostEqual(total_paid, lot.purchase_kg * 1.0, places=2)

        with self.assertRaises(UserError):
            lot.with_user(self.manager_user).write({"mercas_firm_negotiation": False})

    def test_wizard_blocks_wrong_button_for_mode(self):
        """The wizard rejects invoicing a lot under firm negotiation with
        the advance button, and vice versa."""
        lot = self.lot
        lot.with_user(self.manager_user).write({"mercas_firm_negotiation": True})

        wizard = self.env["stock.lot.invoice.wizard"].create({})
        line = wizard.line_ids.filtered(lambda l: l.lot_id == lot)
        self.assertTrue(line)
        line.selected = True

        with self.assertRaises(UserError):
            wizard.action_invoice_advance()

        lot.with_user(self.manager_user).write({"mercas_firm_negotiation": False})
        wizard2 = self.env["stock.lot.invoice.wizard"].create({})
        line2 = wizard2.line_ids.filtered(lambda l: l.lot_id == lot)
        line2.selected = True
        with self.assertRaises(UserError):
            wizard2.action_invoice_firm()
