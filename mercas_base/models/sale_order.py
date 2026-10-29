from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "mercas.box.order.mixin"]

    _mercas_box_link_field = "box_sale_line_id"
    _mercas_box_qty_field = "product_uom_qty"

    box_delivery_purchase_id = fields.Many2one(
        comodel_name="purchase.order",
        string="Source Purchase (Box Delivery)",
        copy=False,
        readonly=True,
    )
    mercas_is_box_delivery = fields.Boolean(
        compute="_compute_mercas_is_box_delivery",
        store=True,
        string="Is Box Delivery to Supplier",
    )

    @api.depends(
        "box_delivery_purchase_id", "order_line.display_type",
        "order_line.product_id.is_box",
    )
    def _compute_mercas_is_box_delivery(self):
        for order in self:
            product_lines = order.order_line.filtered(lambda l: not l.display_type)
            content_is_box = bool(product_lines) and all(
                line.product_id.is_box for line in product_lines
            )
            order.mercas_is_box_delivery = bool(order.box_delivery_purchase_id) or content_is_box

    def action_confirm(self):
        regular_orders = self.filtered(lambda o: not o.mercas_is_box_delivery)
        for order in regular_orders:
            order._mercas_ensure_customer_location()
            order._mercas_prepare_box_lines()

        return super().action_confirm()

    def _mercas_ensure_customer_location(self):
        self.partner_id.mercas_ensure_customer_location(self.company_id)

    def action_mercas_box_deliver_and_invoice(self):
        """Button target: deliver the boxes and invoice the customer now, for a
        box-delivery order (mercas_is_box_delivery). A deliberate user action,
        not automatic on confirm, so a sale that happens to contain only box
        products for an unrelated reason never triggers this by accident."""
        self.ensure_one()
        return self._mercas_box_delivery_confirm_flow()

    def _mercas_box_delivery_confirm_flow(self):
        """Deliver boxes to the supplier's location, create and post the customer invoice.

        With account_financial_risk, an invoice over the customer's risk isn't
        posted: the risk dialog is returned instead of the invoice, and the
        invoice stays in draft until a risk manager goes on there."""
        self.ensure_one()

        # Ensure the partner has a sub-location under the mercas supplier parent
        self.partner_id.mercas_ensure_supplier_location(self.company_id)

        partner = self.partner_id.commercial_partner_id
        supplier_loc = partner.with_company(self.company_id).property_stock_supplier

        pending = self.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
        for picking in pending:
            active_moves = picking.move_ids.filtered(
                lambda m: m.state not in ("done", "cancel")
            )
            # Set done qty to trigger move_line creation
            for move in active_moves:
                move.quantity = move.product_uom_qty
            # Redirect destination from virtual customer to the supplier's physical location
            if supplier_loc:
                picking.move_line_ids.write({"location_dest_id": supplier_loc.id})
            picking._mercas_validate()

        # Create and immediately post the customer invoice
        invoices = self._create_invoices()
        invoice = invoices[:1]
        if not invoice:
            return True
        invoice.invoice_date = fields.Date.context_today(self)
        risk_action = invoice.action_post()
        if self._mercas_is_risk_action(risk_action):
            return risk_action

        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": invoice.id,
            "view_mode": "form",
            "target": "current",
        }

    def button_sold_and_sent(self):
        """Confirm the sale and immediately validate the delivery if all lots are assigned."""
        self.ensure_one()

        # 1. Lot check
        tracked_without_lot = self.order_line.filtered(
            lambda l: not l.display_type
            and not l.box_sale_line_id
            and l.product_id.tracking in ("lot", "serial")
            and not l.lot_id
        )
        if tracked_without_lot:
            names = ", ".join(tracked_without_lot.mapped("product_id.name"))
            raise UserError(
                _("Assign a lot to the following products before sending: %s") % names
            )

        # 2. Financial risk check (sale_financial_risk / account_financial_risk)
        if hasattr(self, "evaluate_risk_message"):
            allow_overrisk = getattr(
                self.company_id, "allow_overrisk_sale_confirmation", True
            )
            if not allow_overrisk:
                partner = self.partner_invoice_id.commercial_partner_id
                exception_msg = self.evaluate_risk_message(partner)
                if exception_msg:
                    return (
                        self.env["partner.risk.exceeded.wiz"]
                        .create({
                            "exception_msg": exception_msg,
                            "partner_id": partner.id,
                            "origin_reference": f"{self._name},{self.id}",
                            "continue_method": "_mercas_sold_and_sent_execute",
                        })
                        .action_show()
                    )

        return self._mercas_sold_and_sent_execute()

    def _mercas_sold_and_sent_execute(self):
        """Confirm and auto-deliver. Called directly or via the risk wizard continue.
        For box-delivery orders this also runs the automated deliver+invoice flow
        (same as the "Receive & Invoice" button) since this shortcut is itself
        an explicit "do it all now" action.

        The invoice of a box delivery is checked against the risk too, so its
        risk dialog is returned. Not when a risk manager has just accepted the
        risk of this sale: the dialog calls this method with `bypass_risk`,
        which the invoice gets as well, so it isn't asked twice."""
        self.with_context(bypass_risk=True).action_confirm()
        if self.mercas_is_box_delivery:
            result = self._mercas_box_delivery_confirm_flow()
            if self._mercas_is_risk_action(result):
                return result
        else:
            self._mercas_auto_deliver()

    @api.model
    def _mercas_is_risk_action(self, action):
        """Whether *action* is the risk dialog of account_financial_risk."""
        return isinstance(action, dict) and action.get("res_model") == "partner.risk.exceeded.wiz"

    def action_open_box_return(self):
        """Open a new purchase order pre-filled for box return from this sale's customer."""
        self.ensure_one()
        if not self.env["product.template"]._mercas_any_box_product_exists():
            raise UserError(_("There is no product marked as a box/container."))
        new_po = self.env["purchase.order"].create({
            "partner_id": self.partner_id.id,
            "origin": self.name,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "res_id": new_po.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_print_mercas_labels(self):
        """Open the wizard to print product labels for this sale's boxes."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Print Labels"),
            "res_model": "mercas.label.print.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_sale_id": self.id},
        }

    def _mercas_auto_deliver(self):
        pending = self.picking_ids.filtered(
            lambda p: p.state not in ("done", "cancel")
        )
        for picking in pending:
            for move in picking.move_ids.filtered(
                lambda m: m.state not in ("done", "cancel")
            ):
                move.quantity = move.product_uom_qty
            picking._mercas_validate()
