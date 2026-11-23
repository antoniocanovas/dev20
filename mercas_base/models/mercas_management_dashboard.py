from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.tools import format_amount, format_date, formatLang

# Customers listed by their debt in the summary
TOP_DEBTORS = 10
# Days overdue of each column of the debt: up to 30, 31-60, 61-90 and more
DEBT_AGES = (30, 60, 90)
# Colours of the debt by age in the charts: not due, then from the most recent to the oldest
DEBT_AGE_COLORS = ("#198754", "#ffc107", "#fd7e14", "#dc3545", "#842029")


class MercasManagementDashboard(models.TransientModel):
    """ Figures of the business for the management, at a date: sales and purchases (amount and
    net kg) of the day, the week, the month and the year, compared with the period before and
    with the year before; scrap, debt of the customers and to the suppliers, sales to invoice,
    lots to settle and payments collected.

    The same summary is shown in the backend and sent each evening by email to the users of
    the group Management Summary by Email (see _cron_send_summary). The counter screen shows the sales
    of the day with _mercas_sales_figures.
    """
    _name = "mercas.management.dashboard"
    _description = "Mercas Management Dashboard"

    date = fields.Date(required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        comodel_name="res.company", required=True, default=lambda self: self.env.company,
    )
    summary_html = fields.Html(compute="_compute_summary_html", sanitize=False)
    # Data of the charts of the backend (see the widget mercas_management_charts): the mail
    # keeps the charts of the summary, as the mail clients don't run them
    chart_data = fields.Json(compute="_compute_chart_data")

    def _compute_display_name(self):
        for dashboard in self:
            dashboard.display_name = self.env._("Management")

    @api.depends("date", "company_id")
    def _compute_summary_html(self):
        # The figures of the whole company, whatever the rights of the user on each document:
        # the model is only for the group Mercas: Management
        for dashboard in self:
            dashboard.summary_html = dashboard.date and dashboard.sudo().with_company(
                dashboard.company_id)._mercas_render_summary(dashboard.date)

    @api.depends("date", "company_id")
    def _compute_chart_data(self):
        for dashboard in self:
            dashboard.chart_data = dashboard.date and dashboard.sudo().with_company(
                dashboard.company_id)._mercas_chart_data(dashboard.date)

    def action_send_mail(self):
        self.ensure_one()
        mail = self.sudo().with_company(self.company_id)._mercas_send_summary(self.date)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success" if mail else "warning",
                "message": self.env._("The summary has been sent.") if mail else self.env._(
                    "No user receiving the management summary by email has an email address."),
            },
        }

    # ------------------------------------------------------------------
    # Periods and figures
    # ------------------------------------------------------------------

    @api.model
    def _mercas_tz(self):
        return pytz.timezone(self.env.user.tz or self.env.company.partner_id.tz or "UTC")

    @api.model
    def _mercas_utc_bounds(self, date_from, date_to):
        """ The days from `date_from` to `date_to` (both included), in the time zone of the
        user, as naive UTC datetimes: [start, end). """
        tz = self._mercas_tz()

        def to_utc(day):
            return tz.localize(datetime.combine(day, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        return to_utc(date_from), to_utc(date_to + timedelta(days=1))

    @api.model
    def _mercas_kg(self, groups):
        """ Net kg of (product, uom, quantity) groups. """
        return sum(product._mercas_net_weight(qty, uom) for product, uom, qty in groups if product)

    @api.model
    def _mercas_sales_figures(self, date_from, date_to):
        """ Confirmed sales of the goods (not the boxes) dated in the period: untaxed amount,
        net kg, number of sales and of boxes. """
        start, end = self._mercas_utc_bounds(date_from, date_to)
        order_domain = [
            ("state", "=", "sale"),
            ("date_order", ">=", start),
            ("date_order", "<", end),
            ("company_id", "=", self.env.company.id),
        ]
        groups = self.env["sale.order.line"]._read_group(
            [
                *(("order_id." + field, op, value) for field, op, value in order_domain),
                ("display_type", "=", False),
                ("product_id.is_box", "=", False),
            ],
            ["product_id", "product_uom_id"],
            ["product_uom_qty:sum", "price_subtotal:sum", "box_qty:sum"],
        )
        return {
            "amount": sum(group[3] for group in groups),
            "kg": self._mercas_kg((product, uom, qty) for product, uom, qty, _amount, _boxes in groups),
            "count": self.env["sale.order"].search_count(order_domain),
            "boxes": sum(group[4] for group in groups),
        }

    @api.model
    def _mercas_purchase_figures(self, date_from, date_to):
        """ Confirmed purchases of goods dated in the period, and the kg scrapped in it. """
        start, end = self._mercas_utc_bounds(date_from, date_to)
        company = self.env.company
        groups = self.env["purchase.order.line"]._read_group(
            [
                ("order_id.state", "in", ("purchase", "done")),
                ("order_id.date_order", ">=", start),
                ("order_id.date_order", "<", end),
                ("company_id", "=", company.id),
                ("display_type", "=", False),
                ("product_id.is_box", "=", False),
            ],
            ["product_id", "uom_id"],
            ["product_qty:sum", "price_subtotal:sum"],
        )
        # Odoo 20 has no stock.scrap: the scraps are moves marked as such
        scraps = self.env["stock.move"]._read_group(
            [
                ("is_scrap", "=", True),
                ("state", "=", "done"),
                ("date", ">=", start),
                ("date", "<", end),
                ("company_id", "=", company.id),
            ],
            ["product_id", "uom_id"],
            ["quantity:sum"],
        )
        return {
            "amount": sum(group[3] for group in groups),
            "kg": self._mercas_kg((product, uom, qty) for product, uom, qty, _amount in groups),
            "scrap_kg": self._mercas_kg(scraps),
        }

    @api.model
    def _mercas_same_week_last_year(self, date):
        """ Monday of the week of the year before with the same number (ISO) as the one of
        `date`: the week 52 when that year had no week 53. """
        year, week, _weekday = date.isocalendar()
        last_weeks = datetime(year - 1, 12, 28).date().isocalendar()[1]
        return datetime.fromisocalendar(year - 1, min(week, last_weeks), 1).date()

    @api.model
    def _mercas_periods(self, date):
        """ Day, week (from Monday), month and year up to `date`, each with the period before
        and the same one a year before: (key, (from, to), previous, year before). A year
        before, the day is the same weekday of the week with the same number (Monday of the
        week 40 with Monday of the week 40), and the week the whole week with that number. """
        week_start = date - timedelta(days=date.weekday())
        month_start = date.replace(day=1)
        year_start = date.replace(month=1, day=1)
        year_ago = relativedelta(years=1)
        last_year_week = self._mercas_same_week_last_year(date)
        return [
            ("day", (date, date), (date - timedelta(days=1),) * 2,
             (last_year_week + timedelta(days=date.weekday()),) * 2),
            ("week", (week_start, date), (week_start - timedelta(weeks=1), date - timedelta(weeks=1)),
             (last_year_week, last_year_week + timedelta(days=6))),
            ("month", (month_start, date), (month_start - relativedelta(months=1), date - relativedelta(months=1)),
             (month_start - year_ago, date - year_ago)),
            ("year", (year_start, date), None, (year_start - year_ago, date - year_ago)),
        ]

    @api.model
    def _mercas_chart_references(self, date):
        """ What the charts compare each period with, besides the year before: the day with
        the same weekday of the week before (a whole day), the week and the month with the whole
        week and month before. The year has none. """
        week_start = date - timedelta(days=date.weekday())
        month_start = date.replace(day=1)
        return {
            "day": (self.env._("Same day last week"), (date - timedelta(weeks=1),) * 2),
            "week": (self.env._("Last week"), (week_start - timedelta(weeks=1), week_start - timedelta(days=1))),
            "month": (self.env._("Last month"), (month_start - relativedelta(months=1), month_start - timedelta(days=1))),
        }

    @api.model
    def _mercas_sales_by_day(self, date_from, date_to):
        """ Untaxed amount of the goods sold each day of the period (local days), as
        _mercas_sales_figures: {date: amount}. """
        start, end = self._mercas_utc_bounds(date_from, date_to)
        groups = self.env["sale.order.line"]._read_group(
            [
                ("order_id.state", "=", "sale"),
                ("order_id.date_order", ">=", start),
                ("order_id.date_order", "<", end),
                ("order_id.company_id", "=", self.env.company.id),
                ("display_type", "=", False),
                ("product_id.is_box", "=", False),
            ],
            ["order_id"], ["price_subtotal:sum"],
        )
        tz = self._mercas_tz()
        by_day = defaultdict(float)
        for order, amount in groups:
            by_day[pytz.utc.localize(order.date_order).astimezone(tz).date()] += amount
        return by_day

    @api.model
    def _mercas_chart_data(self, date):
        """ Series of the charts: the week day by day (with the week before and the week with
        the same number last year), the month and the year accumulated (with the month before,
        the same month and the year before, and the forecast) and the debt of the customers
        by age. The amounts of the days are those of _mercas_sales_figures. """
        _ = self.env._
        week_start = date - timedelta(days=date.weekday())
        last_year_week = self._mercas_same_week_last_year(date)
        month_start = date.replace(day=1)
        previous_month_start = month_start - relativedelta(months=1)
        year_start = date.replace(month=1, day=1)
        year_ago = relativedelta(years=1)
        last_year_start = year_start - year_ago
        by_day = self._mercas_sales_by_day(
            min(last_year_week, last_year_start, previous_month_start), date)

        def days(date_from, count):
            return [by_day.get(date_from + timedelta(days=index), 0.0) for index in range(count)]

        def accumulate(values):
            total, result = 0.0, []
            for value in values:
                total += value
                result.append(round(total, 2))
            return result

        def month_days(start):
            return ((start + relativedelta(months=1)) - start).days

        def by_month(start, months):
            return [sum(amount for day, amount in by_day.items()
                        if start + relativedelta(months=index) <= day < start + relativedelta(months=index + 1))
                    for index in range(months)]

        days_in_month = month_days(month_start)
        days_gone = date.day
        month = accumulate(days(month_start, days_gone))
        month_total = month[-1] if month else 0.0
        year = accumulate(by_month(year_start, date.month))
        year_days = (year_start.replace(year=year_start.year + 1) - year_start).days
        year_forecast = (year[-1] if year else 0.0) * year_days / ((date - year_start).days + 1)
        debt = self._mercas_customer_debt(date)["ages"]
        return {
            "currency": {
                "symbol": self.env.company.currency_id.symbol,
                "position": self.env.company.currency_id.position,
            },
            "colors": {"now": "#714B67", "previous": "#6ea8fe", "last_year": "#adb5bd"},
            "week": {
                "title": _("Week, day by day"),
                "series": [
                    {"key": "now", "label": _("This week"), "data": days(week_start, date.weekday() + 1)},
                    {"key": "previous", "label": _("Last week"), "data": days(week_start - timedelta(weeks=1), 7)},
                    {"key": "last_year", "label": _("Same week last year"), "data": days(last_year_week, 7)},
                ],
            },
            "month": {
                "title": _("Month, accumulated"),
                "days": max(days_in_month, month_days(previous_month_start), month_days(month_start - year_ago)),
                "series": [
                    {"key": "now", "label": _("This month"), "data": month},
                    {"key": "previous", "label": _("Last month"),
                     "data": accumulate(days(previous_month_start, month_days(previous_month_start)))},
                    {"key": "last_year", "label": _("Same month last year"),
                     "data": accumulate(days(month_start - year_ago, month_days(month_start - year_ago)))},
                ],
                "forecast": {"label": _("Forecast"), "from": [days_gone, month_total],
                             "to": [days_in_month, round(month_total * days_in_month / days_gone, 2)]},
            },
            "year": {
                "title": _("Year, accumulated by month"),
                "series": [
                    {"key": "now", "label": _("This year"), "data": year},
                    {"key": "last_year", "label": _("Last year"), "data": accumulate(by_month(last_year_start, 12))},
                ],
                "forecast": {"label": _("Forecast"), "from": [date.month, year[-1] if year else 0.0],
                             "to": [12, round(year_forecast, 2)]},
            },
            "debt": {
                "title": _("Customers' open debt"),
                "labels": self._mercas_debt_age_names(),
                "colors": list(DEBT_AGE_COLORS),
                "data": [round(max(amount, 0.0), 2) for amount in debt],
                "total": round(sum(debt), 2),
            },
        }

    @api.model
    def _mercas_debt_age_names(self):
        env = self.env
        return [
            env._("Not due"),
            env._("1-%s days", DEBT_AGES[0]),
            *(env._("%(from)s-%(to)s days", **{"from": DEBT_AGES[index - 1] + 1, "to": DEBT_AGES[index]})
              for index in range(1, len(DEBT_AGES))),
            env._("Over %s days", DEBT_AGES[-1]),
        ]

    @api.model
    def _mercas_balance(self, account_type, date):
        """ Balance of the receivable or payable accounts of the company on `date`. """
        groups = self.env["account.move.line"]._read_group(
            [
                ("account_id.account_type", "=", account_type),
                ("parent_state", "=", "posted"),
                ("date", "<=", date),
                ("company_id", "=", self.env.company.id),
            ],
            [], ["balance:sum"],
        )
        return groups[0][0] or 0.0

    @api.model
    def _mercas_customer_debt(self, date):
        """ Debt of the customers that was open on `date`, by days overdue on that date, and
        the customers that owed the most: the receivable lines dated up to then, without the
        reconciliations made later, so that a past date (a month ago) is right too. """
        lines = self.env["account.move.line"].search_fetch(
            [
                ("account_id.account_type", "=", "asset_receivable"),
                ("parent_state", "=", "posted"),
                ("date", "<=", date),
                ("company_id", "=", self.env.company.id),
                "|", "|",
                ("reconciled", "=", False),
                ("matched_debit_ids.max_date", ">", date),
                ("matched_credit_ids.max_date", ">", date),
            ],
            ["balance", "date_maturity", "date", "partner_id", "matched_debit_ids", "matched_credit_ids"],
        )
        currency = self.env.company.currency_id
        ages = [0.0] * (len(DEBT_AGES) + 2)
        by_partner = defaultdict(lambda: [0.0, 0.0])
        for line in lines:
            # A debit line is paid by its matched credits, a credit line used by its matched debits
            residual = (
                line.balance
                - sum(partial.amount for partial in line.matched_credit_ids if partial.max_date <= date)
                + sum(partial.amount for partial in line.matched_debit_ids if partial.max_date <= date)
            )
            if currency.is_zero(residual):
                continue
            overdue_days = (date - (line.date_maturity or line.date)).days
            if overdue_days <= 0:
                column = 0
            else:
                column = next((index + 1 for index, age in enumerate(DEBT_AGES) if overdue_days <= age),
                              len(DEBT_AGES) + 1)
            ages[column] += residual
            partner = by_partner[line.partner_id]
            partner[0] += residual
            if column:
                partner[1] += residual
        top = sorted(
            ((partner, total, overdue) for partner, (total, overdue) in by_partner.items() if total > 0),
            key=lambda item: -item[1],
        )[:TOP_DEBTORS]
        return {"ages": ages, "top": top}

    @api.model
    def _mercas_pace(self, name, date, date_from, date_to, current, year_before):
        """ How the month or the year goes up to `date` (from `date_from`, of `date_to` days in
        all): the sales up to now and at the same point a year before, the whole period of the
        year before, and the close forecast at the pace of the days gone by. """
        year_ago = relativedelta(years=1)
        last_year = self._mercas_sales_figures(date_from - year_ago, date_to - year_ago)["amount"]
        days_gone = (date - date_from).days + 1
        days = (date_to - date_from).days + 1
        forecast = current * days / days_gone
        return {
            "name": name,
            "current": current,
            "year_before": year_before,
            "last_year": last_year,
            "forecast": forecast,
            "scale": max(current, forecast, year_before, last_year),
        }

    @api.model
    def _mercas_summary_values(self, date):
        company = self.env.company
        sales, purchases = [], []
        period_names = {
            "day": self.env._("Day"),
            "week": self.env._("Week"),
            "month": self.env._("Month"),
            "year": self.env._("Year"),
        }
        chart_references = self._mercas_chart_references(date)
        for key, current, previous, year_before in self._mercas_periods(date):
            figures = self._mercas_sales_figures(*current)
            chart_reference = False
            if key in chart_references:
                label, (date_from, date_to) = chart_references[key]
                chart_reference = {
                    "key": key,
                    "label": label,
                    "amount": self._mercas_sales_figures(date_from, date_to)["amount"],
                }
            sales.append({
                "key": key,
                "name": period_names[key],
                "figures": figures,
                "previous": previous and self._mercas_sales_figures(*previous),
                "year_before": self._mercas_sales_figures(*year_before),
                "chart_reference": chart_reference,
            })
            sales[-1]["scale"] = max(
                figures["amount"], sales[-1]["year_before"]["amount"],
                chart_reference["amount"] if chart_reference else 0.0)
            purchases.append({"name": period_names[key], "figures": self._mercas_purchase_figures(*current)})
        sales_by_key = {row["key"]: row for row in sales}
        month_start = date.replace(day=1)
        year_start = date.replace(month=1, day=1)
        pace = [
            self._mercas_pace(
                self.env._("Month"), date, month_start, month_start + relativedelta(months=1, days=-1),
                sales_by_key["month"]["figures"]["amount"], sales_by_key["month"]["year_before"]["amount"]),
            self._mercas_pace(
                self.env._("Year"), date, year_start, year_start.replace(month=12, day=31),
                sales_by_key["year"]["figures"]["amount"], sales_by_key["year"]["year_before"]["amount"]),
        ]
        month_ago = date - relativedelta(months=1)
        debt = self._mercas_customer_debt(date)
        balance_dates = [
            (self.env._("Today"), date),
            (self.env._("End of last month"), date.replace(day=1) - timedelta(days=1)),
            (self.env._("A year ago"), date - relativedelta(years=1)),
        ]
        to_invoice = self.env["sale.order.line"]._read_group(
            [
                ("state", "=", "sale"),
                ("untaxed_amount_to_invoice", "!=", 0),
                ("company_id", "=", company.id),
            ],
            ["order_partner_id"], ["untaxed_amount_to_invoice:sum"],
        )
        lots = self.env["stock.lot"].search([
            ("completed", "=", True),
            ("invoiceable", "=", True),
            ("mercas_firm_negotiation", "=", False),
            ("company_id", "in", (company.id, False)),
        ])
        payments = self.env["account.payment"]._read_group(
            [
                ("payment_type", "=", "inbound"),
                ("partner_type", "=", "customer"),
                ("state", "in", ("in_process", "paid")),
                ("date", "=", date),
                ("company_id", "=", company.id),
            ],
            ["journal_id"], ["amount:sum"],
        )
        values = {
            "date": date,
            "company": company,
            "sales": sales,
            "pace": pace,
            "purchases": purchases,
            "balances": [
                {"name": self.env._("Customers owe us"), "values": [
                    (name, self._mercas_balance("asset_receivable", day)) for name, day in balance_dates]},
                {"name": self.env._("We owe suppliers"), "values": [
                    (name, -self._mercas_balance("liability_payable", day)) for name, day in balance_dates]},
            ],
            "debt": debt,
            "debt_history": [
                {"name": name, "total": sum(ages), "segments": list(zip(ages, DEBT_AGE_COLORS))}
                for name, ages in (
                    (self.env._("Today"), debt["ages"]),
                    (self.env._("A month ago"), self._mercas_customer_debt(month_ago)["ages"]),
                )
            ],
            "to_invoice": {
                "amount": sum(amount for _partner, amount in to_invoice),
                "customers": len(to_invoice),
            },
            "lots_to_settle": {
                "count": len(lots),
                "amount": sum(lot.supplier_amount - lot.net_invoiced_amount for lot in lots),
            },
            "payments": [(journal.name, amount) for journal, amount in payments],
            "payments_total": sum(amount for _journal, amount in payments),
        }
        # The same scale for the debt of today and of a month ago, to compare them
        values["debt_scale"] = max(
            sum(max(amount, 0.0) for amount, _color in row["segments"]) for row in values["debt_history"])
        return values

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    @api.model
    def _mercas_render_summary(self, date):
        values = self._mercas_summary_values(date)
        currency = self.env.company.currency_id
        env = self.env

        def money(amount):
            return format_amount(env, amount, currency)

        def kg(qty):
            return "%s kg" % formatLang(env, qty, digits=0)

        def price_kg(figures):
            return format_amount(env, figures["amount"] / figures["kg"], currency) if figures["kg"] else "—"

        def change(current, reference):
            """ (text, colour, arrow) of the change of `current` from `reference`, in %. """
            if not reference:
                return ("—", "#6c757d", "")
            percent = (current - reference) / abs(reference) * 100
            return ("%s%s %%" % ("+" if percent > 0 else "", formatLang(env, percent, digits=1)),
                    "#198754" if percent >= 0 else "#dc3545",
                    "▲" if percent >= 0 else "▼")

        def year_note(row, field="amount"):
            """ (text, colour, arrow) of a period against the year before: the change, but for
            the week, compared with the whole week of last year: how much of it is reached. """
            current, reference = row["figures"][field], row["year_before"][field]
            if row["key"] != "week":
                return change(current, reference)
            if not reference:
                return ("—", "#6c757d", "")
            return (env._("%s reached", "%s %%" % formatLang(env, current / reference * 100, digits=0)),
                    "#0d6efd", "")

        def reference_note(row):
            """ (text, colour) of the sales of a period against its chart reference: the change
            for the day (alike days), how much of the whole week or month before is reached. """
            reference = row["chart_reference"]
            if reference["key"] == "day":
                delta = change(row["figures"]["amount"], reference["amount"])
                return ("%s %s" % (delta[2], delta[0]) if delta[2] else delta[0], delta[1])
            if not reference["amount"]:
                return ("—", "#6c757d")
            percent = row["figures"]["amount"] / reference["amount"] * 100
            return (env._("%s reached", "%s %%" % formatLang(env, percent, digits=0)), "#0d6efd")

        def pace_text(row):
            return env._("%(current)s up to today · at this pace, closing at %(forecast)s",
                         current=money(row["current"]), forecast=money(row["forecast"]))

        def pace_change(delta):
            return env._("(%(arrow)s %(change)s on last year)", arrow=delta[2], change=delta[0]) if delta[2] else ""

        def pace_last_year_text(row):
            return env._("Last year: %(point)s at this point, %(total)s in all",
                         point=money(row["year_before"]), total=money(row["last_year"]))

        def bar(segments, scale=None):
            """ Widths in % of the (value, colour) segments of a bar of `scale` (their sum by
            default), and the empty rest: the cells of a table, as the mail clients draw them. """
            values = [(max(value, 0.0), color) for value, color in segments]
            scale = scale or sum(value for value, _color in values)
            if scale <= 0:
                return {"cells": [], "rest": 100.0}
            cells = [(round(value / scale * 100, 1), color) for value, color in values if value > 0]
            return {"cells": cells, "rest": max(round(100 - sum(width for width, _color in cells), 1), 0.0)}

        def scrap_percent(figures):
            if not figures["kg"]:
                return "—"
            return "%s %%" % formatLang(env, figures["scrap_kg"] / figures["kg"] * 100, digits=1)

        return self.env["ir.qweb"]._render("mercas_base.management_summary", {
            **values,
            "format_date": lambda day: format_date(env, day),
            "money": money,
            "kg": kg,
            "price_kg": price_kg,
            "change": change,
            "scrap_percent": scrap_percent,
            "bar": bar,
            "reference_note": reference_note,
            "year_note": year_note,
            "pace_text": pace_text,
            "pace_change": pace_change,
            "pace_last_year_text": pace_last_year_text,
            "age_colors": DEBT_AGE_COLORS,
            "age_names": self._mercas_debt_age_names(),
        })

    @api.model
    def _mercas_summary_recipients(self):
        group = self.env.ref("mercas_base.group_mercas_summary_mail", raise_if_not_found=False)
        if not group:
            return self.env["res.partner"]
        users = group.sudo().all_user_ids.filtered(
            lambda user: user.active and user.email and self.env.company in user.company_ids)
        return users.partner_id

    @api.model
    def _mercas_send_summary(self, date):
        """ Email the summary of `date` to the users of the group Management Summary by Email. """
        partners = self._mercas_summary_recipients()
        if not partners:
            return self.env["mail.mail"]
        company = self.env.company
        mail = self.env["mail.mail"].sudo().create({
            "subject": self.env._("%(company)s · Summary of %(date)s",
                                  company=company.name, date=format_date(self.env, date)),
            "body_html": self._mercas_render_summary(date),
            "email_from": company.email_formatted or self.env.user.email_formatted,
            "recipient_ids": [fields.Command.set(partners.ids)],
            "auto_delete": True,
        })
        return mail

    @api.model
    def _cron_send_summary(self):
        """ Each evening, the summary of the day of each company to its management. """
        for company in self.env["res.company"].search([]):
            dashboard = self.with_company(company).with_context(allowed_company_ids=company.ids)
            dashboard._mercas_send_summary(fields.Date.context_today(dashboard))
