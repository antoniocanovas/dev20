from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    mercas_customer_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Customer Warehouse",
        default=lambda self: self.env.ref(
            "stock.stock_location_customers", raise_if_not_found=False
        ),
        help=(
            "Parent location under which a per-customer location will be "
            "automatically created when the sale is confirmed, if it doesn't "
            "already exist."
        ),
    )
    mercas_supplier_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Supplier Warehouse",
        default=lambda self: self.env.ref(
            "stock.stock_location_suppliers", raise_if_not_found=False
        ),
        help=(
            "Parent location under which a per-supplier location will be "
            "automatically created when the purchase is confirmed, if it "
            "doesn't already exist."
        ),
    )
    purchase_lot_autocomplete = fields.Boolean(
        string="Auto Purchase Lot",
        default=True,
        help="Automatically create purchase lots on confirm if not already set.",
    )
    origin_country = fields.Boolean(
        string="Country of Origin Column",
        default=True,
        help="Shows the country of origin column on purchase order lines.",
    )
    origin_state = fields.Boolean(
        string="State of Origin Column",
        default=True,
        help="Shows the state of origin column on purchase order lines.",
    )
    origin_filter = fields.Boolean(
        string="Origin Filter",
        default=False,
        help="Restricts the country/state selection to those marked as Merca Origin.",
    )
    mercas_margin = fields.Float(
        string="Merca Margin (%)",
        digits=(10, 2),
        help="General margin when not in partner.",
    )
    auto_confirm_supplier_invoice = fields.Boolean(
        string="Auto-Confirm Supplier Invoice",
        default=False,
    )
    compensation_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Offsetting Journal",
        domain=[("type", "=", "general")],
        help=(
            "Miscellaneous operations journal used to offset purchase "
            "invoices against sale invoices of the same partner. The "
            "resulting entry appears as an outstanding credit on the "
            "customer invoices."
        ),
    )
    liquidation_mode = fields.Selection(
        selection=[
            ("average_price", "Average price (single line)"),
            ("average_price_scrap_split", "Average price + scrap separate"),
        ],
        string="Settlement Mode",
        default="average_price",
        required=True,
        help=(
            "How the sale line is generated on the sale-settlement invoice "
            "(does not affect lots under firm negotiation):\n"
            "- Average price: a single line with the gross amount spread "
            "over sold + scrapped kg (scrap dilutes the displayed price/kg).\n"
            "- Average price + scrap separate: the gross amount is spread "
            "only over sold kg, and an extra line at price 0 is added for "
            "the scrapped kg, so the invoice makes explicit that it isn't "
            "paid."
        ),
    )
    liquidation_show_sale_breakdown = fields.Boolean(
        string="Sale Breakdown on Invoice",
        default=False,
        help=(
            "Adds, in the description of the sale-settlement invoice line, "
            "an accumulated breakdown (date, order, quantity and unit "
            "price) of every sale of the lot up to that date. Informational "
            "text only: it does not affect the invoiced amount or quantity. "
            "Does not apply to lots under firm negotiation."
        ),
    )
