from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMercasDashboard(TransactionCase):
    """Management summary: sales and purchases in amount and net kg by
    period, debt, pending work; shown in the backend and sent by email."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Dashboard = cls.env["mercas.management.dashboard"]
        cls.customer = cls.env["res.partner"].create({"name": "Dashboard Customer"})
        kg = cls.env.ref("uom.product_uom_kgm")
        cls.box = cls.env["product.product"].create({
            "name": "Dashboard Box", "is_storable": True, "is_box": True, "weight": 0.5, "list_price": 1.0,
        })
        cls.tomato = cls.env["product.product"].create({
            "name": "Dashboard Tomato", "is_storable": True, "tracking": "lot", "uom_id": kg.id,
            "box_product_id": cls.box.id, "taxes_id": [Command.clear()],
        })
        cls.melon = cls.env["product.product"].create({
            "name": "Dashboard Melon", "is_storable": True, "weight": 2.0, "taxes_id": [Command.clear()],
        })

    def _sell(self, lines):
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [Command.create(line) for line in lines],
        })
        order.action_confirm()
        return order

    def test_lot_no_expiration_from_product(self):
        self.tomato.mercas_no_expiration = True
        lot = self.env["stock.lot"].create({"name": "DASH-1", "product_id": self.tomato.id})
        self.assertTrue(lot.mercas_no_expiration)
        lot.mercas_no_expiration = False
        self.assertFalse(lot.mercas_no_expiration, "It can be changed on the lot")

    def test_sales_figures(self):
        """Untaxed amount and net kg of the goods, without the boxes: a
        product in units counts its weight."""
        today = fields.Date.context_today(self.Dashboard)
        before = self.Dashboard._mercas_sales_figures(today, today)
        self._sell([
            {"product_id": self.tomato.id, "product_uom_qty": 40.0, "price_unit": 1.5, "box_qty": 4},
            {"product_id": self.melon.id, "product_uom_qty": 5.0, "price_unit": 3.0},
        ])
        self._sell([{"product_id": self.tomato.id, "product_uom_qty": 10.0, "price_unit": 2.0}]).action_cancel()
        after = self.Dashboard._mercas_sales_figures(today, today)
        self.assertAlmostEqual(after["amount"] - before["amount"], 75.0)
        self.assertAlmostEqual(after["kg"] - before["kg"], 50.0, msg="40 kg + 5 melons of 2 kg")
        self.assertEqual(after["count"] - before["count"], 1, "Not the cancelled sale")
        self.assertEqual(after["boxes"] - before["boxes"], 4)

    def test_periods(self):
        periods = {key: (current, previous, year_before)
                   for key, current, previous, year_before in self.Dashboard._mercas_periods(date(2026, 3, 31))}
        self.assertEqual(periods["day"][1], (date(2026, 3, 30),) * 2)
        self.assertEqual(periods["day"][2], (date(2025, 4, 1),) * 2, "Tuesday of the week 14 of 2025")
        self.assertEqual(periods["week"][2], (date(2025, 3, 31), date(2025, 4, 6)), "The whole week 14 of 2025")
        self.assertEqual(periods["week"][0], (date(2026, 3, 30), date(2026, 3, 31)), "From Monday")
        self.assertEqual(periods["month"][1], (date(2026, 2, 1), date(2026, 2, 28)))
        self.assertEqual(periods["year"][0], (date(2026, 1, 1), date(2026, 3, 31)))
        self.assertIsNone(periods["year"][1])
        references = {key: dates for key, (_label, dates) in self.Dashboard._mercas_chart_references(date(2026, 3, 31)).items()}
        self.assertEqual(references["day"], (date(2026, 3, 24),) * 2, "Same weekday, the week before")
        self.assertEqual(references["week"], (date(2026, 3, 23), date(2026, 3, 29)), "The whole week before")
        self.assertEqual(references["month"], (date(2026, 2, 1), date(2026, 2, 28)), "The whole month before")
        self.assertEqual(periods["year"][2], (date(2025, 1, 1), date(2025, 3, 31)))

    def test_summary_and_mail(self):
        self._sell([{"product_id": self.tomato.id, "product_uom_qty": 40.0, "price_unit": 1.5}])
        manager = self.env["res.users"].create({
            "name": "Dashboard Manager", "login": "dashboard_manager", "email": "manager@example.com",
            "group_ids": [Command.link(self.env.ref("base.group_user").id),
                          Command.link(self.env.ref("mercas_base.group_mercas_summary_mail").id)],
        })
        dashboard = self.Dashboard.with_user(manager).create({})
        self.assertIn(self.env.company.name, dashboard.summary_html)
        self.assertIn("o_mercas_summary_sales_row", dashboard.summary_html)
        for chart in ("o_mercas_summary_tile", "o_mercas_summary_tile_reference", "o_mercas_summary_pace", "o_mercas_summary_debt_bar"):
            self.assertIn(chart, dashboard.summary_html)
        dashboard.action_send_mail()
        mail = self.env["mail.mail"].search([("recipient_ids", "in", manager.partner_id.id)])
        self.assertEqual(len(mail), 1)
        self.assertIn(self.env.company.name, mail.body_html)
        self.assertNotIn(self.customer, self.Dashboard._mercas_summary_recipients())

    def test_sales_and_billing_administrators(self):
        for group in ("sales_team.group_sale_manager", "account.group_account_manager"):
            user = self.env["res.users"].create({
                "name": group, "login": group,
                "group_ids": [Command.link(self.env.ref(group).id)],
            })
            self.assertTrue(user.has_group("mercas_base.group_mercas_management"), group)
            self.assertTrue(self.Dashboard.with_user(user).create({}).summary_html)
            self.assertNotIn(user.partner_id, self.Dashboard._mercas_summary_recipients(),
                             "Seeing it isn't receiving it by email")
        salesman = self.env["res.users"].create({
            "name": "Salesman", "login": "dashboard_salesman",
            "group_ids": [Command.link(self.env.ref("sales_team.group_sale_salesman").id)],
        })
        self.assertFalse(salesman.has_group("mercas_base.group_mercas_management"))

    def test_cron(self):
        self.env.ref("mercas_base.ir_cron_mercas_management_summary").method_direct_trigger()

    def test_debt_on_a_past_date(self):
        """ The debt of a month ago counts the invoices paid after it as open. """
        today = fields.Date.context_today(self.Dashboard)
        month_ago = today - relativedelta(months=1)
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.customer.id,
            "invoice_date": month_ago - relativedelta(days=40),
            "invoice_date_due": month_ago - relativedelta(days=40),
            "invoice_line_ids": [Command.create({"product_id": self.melon.id, "quantity": 1, "price_unit": 100.0})],
        })
        invoice.action_post()
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=invoice.ids,
        ).create({"payment_date": today}).action_create_payments()
        self.assertEqual(invoice.payment_state, "paid")

        def customer_debt(day):
            top = dict((partner, total) for partner, total, _overdue in self.Dashboard._mercas_customer_debt(day)["top"])
            return top.get(self.customer, 0.0)

        self.assertAlmostEqual(customer_debt(month_ago), 100.0, msg="Paid after that date")
        self.assertAlmostEqual(customer_debt(today), 0.0)
        ages = self.Dashboard._mercas_customer_debt(month_ago)["ages"]
        self.assertGreaterEqual(ages[2], 100.0, "31-60 days overdue on that date")

    def test_week_53(self):
        """ 2026 has a week 53, 2025 hasn't: its week 52. """
        periods = {key: year_before for key, _current, _previous, year_before in self.Dashboard._mercas_periods(date(2026, 12, 31))}
        self.assertEqual(periods["day"], (date(2025, 12, 25),) * 2, "Thursday of the week 52")
        self.assertEqual(periods["week"], (date(2025, 12, 22), date(2025, 12, 28)))

    def test_pace(self):
        pace = self.Dashboard._mercas_pace("Month", date(2026, 3, 10), date(2026, 3, 1), date(2026, 3, 31), 1000.0, 800.0)
        self.assertAlmostEqual(pace["forecast"], 3100.0, msg="1000 in 10 days, 31 days")
        self.assertEqual(pace["scale"], max(3100.0, pace["last_year"]))

    def test_chart_data(self):
        """ The series of the charts add up to the figures of the summary. """
        self._sell([{"product_id": self.tomato.id, "product_uom_qty": 40.0, "price_unit": 1.5}])
        today = fields.Date.context_today(self.Dashboard)
        data = self.Dashboard._mercas_chart_data(today)
        figures = {key: self.Dashboard._mercas_sales_figures(*current)["amount"]
                   for key, current, _previous, _year_before in self.Dashboard._mercas_periods(today)}
        now = {name: next(serie for serie in data[name]["series"] if serie["key"] == "now")["data"]
               for name in ("week", "month", "year")}
        self.assertAlmostEqual(now["week"][-1], figures["day"])
        self.assertEqual(len(now["week"]), today.weekday() + 1)
        self.assertAlmostEqual(sum(now["week"]), figures["week"])
        self.assertAlmostEqual(now["month"][-1], figures["month"], places=2)
        self.assertAlmostEqual(now["year"][-1], figures["year"], places=2)
        self.assertEqual(len(data["debt"]["data"]), len(data["debt"]["labels"]))
        dashboard = self.Dashboard.create({})
        self.assertEqual(dashboard.chart_data["month"]["series"][0]["data"], now["month"])
