from odoo import _, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    mercas_margin = fields.Float(
        string="Merca Margin (%)",
        digits=(10, 2),
        help="Partner mercas margin used when not null.",
    )
    mercas_firm_negotiation = fields.Boolean(
        string="Firm Negotiation",
        help=(
            "Default value of the 'Firm Negotiation' field on new purchase "
            "order lines for this supplier. It can be changed manually on "
            "each line."
        ),
    )
    mercas_box_qty = fields.Float(
        string="Boxes",
        compute="_compute_mercas_box_qty",
        help=(
            "Number of boxes (products marked as box/container) present in "
            "this contact's own customer and supplier locations."
        ),
    )
    mercas_has_box_location = fields.Boolean(
        string="Has Box Location",
        compute="_compute_mercas_box_qty",
        help=(
            "The contact has its own customer or supplier location and "
            "there is at least one product marked as box/container, even if "
            "there is no stock right now. Controls the visibility of the "
            "boxes button."
        ),
    )

    def _mercas_box_locations(self, company):
        """Dedicated customer/supplier locations of this partner, excluding the
        company's generic parent locations."""
        self.ensure_one()
        partner = self.commercial_partner_id.with_company(company)
        locations = self.env["stock.location"]
        customer_loc = partner.property_stock_customer
        if customer_loc and customer_loc != company.mercas_customer_location_id:
            locations |= customer_loc
        supplier_loc = partner.property_stock_supplier
        if supplier_loc and supplier_loc != company.mercas_supplier_location_id:
            locations |= supplier_loc
        return locations

    def _mercas_box_quants_domain(self, company, any_box_product=None):
        locations = self._mercas_box_locations(company)
        if any_box_product is None:
            any_box_product = self.env["product.template"]._mercas_any_box_product_exists()
        if not locations or not any_box_product:
            return None
        return [
            ("location_id", "in", locations.ids),
            ("product_id.is_box", "=", True),
            ("quantity", "!=", 0),
        ]

    def _compute_mercas_box_qty(self):
        company = self.env.company
        any_box_product = self.env["product.template"]._mercas_any_box_product_exists()
        if not any_box_product:
            self.mercas_has_box_location = False
            self.mercas_box_qty = 0.0
            return

        # One search across every partner's locations instead of one search
        # per partner -- a contact list computing this column would otherwise
        # do N queries (plus a redundant _mercas_any_box_product_exists() per
        # partner, already hoisted above) instead of a single one.
        locations_by_partner = {partner.id: partner._mercas_box_locations(company) for partner in self}
        all_location_ids = {loc_id for locs in locations_by_partner.values() for loc_id in locs.ids}

        qty_by_location = {}
        if all_location_ids:
            quants = self.env["stock.quant"].search([
                ("location_id", "in", list(all_location_ids)),
                ("product_id.is_box", "=", True),
                ("quantity", "!=", 0),
            ])
            for quant in quants:
                loc_id = quant.location_id.id
                qty_by_location[loc_id] = qty_by_location.get(loc_id, 0.0) + quant.quantity

        for partner in self:
            locations = locations_by_partner[partner.id]
            partner.mercas_has_box_location = bool(locations)
            partner.mercas_box_qty = sum(qty_by_location.get(loc_id, 0.0) for loc_id in locations.ids)

    def action_view_mercas_box_quants(self):
        self.ensure_one()
        domain = self._mercas_box_quants_domain(self.env.company) or [("id", "=", 0)]
        return {
            "type": "ir.actions.act_window",
            "name": _("Box Summary"),
            "res_model": "stock.quant",
            "view_mode": "list",
            "domain": domain,
            "context": {"group_by": ["product_id", "location_id"]},
        }

    def action_mercas_open_box_delivery(self):
        """Open a new sale order to deliver boxes to this partner (acting as
        our supplier for this box exchange), same as the "Entrega cajas"
        button on a purchase order but without a specific origin purchase."""
        self.ensure_one()
        if not self.env["product.template"]._mercas_any_box_product_exists():
            raise UserError(_("There is no product marked as a box/container."))
        new_so = self.env["sale.order"].create({"partner_id": self.id})
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": new_so.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_mercas_open_box_return(self):
        """Open a new purchase order to receive boxes back from this partner
        (acting as our customer for this box exchange), same as the
        "Return Boxes" button on a sale order but without a specific
        origin sale."""
        self.ensure_one()
        if not self.env["product.template"]._mercas_any_box_product_exists():
            raise UserError(_("There is no product marked as a box/container."))
        new_po = self.env["purchase.order"].create({"partner_id": self.id})
        return {
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "res_id": new_po.id,
            "view_mode": "form",
            "target": "current",
        }

    def mercas_ensure_customer_location(self, company):
        """Ensure the commercial partner has a sub-location under the mercas parent.

        Creates one if missing and sets property_stock_customer on the partner.
        Safe to call repeatedly; no-op when the location already exists.
        """
        self.ensure_one()
        parent_loc = company.mercas_customer_location_id
        if not parent_loc:
            return
        partner = self.commercial_partner_id
        current = partner.with_company(company).property_stock_customer
        if current and current.location_id == parent_loc:
            return
        # A technical location made by the sale or purchase flow: also for users who can't
        # manage the locations or edit the partner
        new_loc = self.env["stock.location"].sudo().create({
            "name": partner.name,
            "location_id": parent_loc.id,
            "usage": "customer",
        })
        partner.sudo().with_company(company).property_stock_customer = new_loc

    def mercas_ensure_supplier_location(self, company):
        """Ensure the commercial partner has a sub-location under the mercas supplier parent.

        Creates one if missing and sets property_stock_supplier on the partner.
        Safe to call repeatedly; no-op when the location already exists.
        """
        self.ensure_one()
        parent_loc = company.mercas_supplier_location_id
        if not parent_loc:
            return
        partner = self.commercial_partner_id
        current = partner.with_company(company).property_stock_supplier
        if current and current.location_id == parent_loc:
            return
        # A technical location made by the sale or purchase flow: also for users who can't
        # manage the locations or edit the partner
        new_loc = self.env["stock.location"].sudo().create({
            "name": partner.name,
            "location_id": parent_loc.id,
            "usage": "supplier",
        })
        partner.sudo().with_company(company).property_stock_supplier = new_loc
