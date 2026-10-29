from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero


class PurchaseOrder(models.Model):
    _name = "purchase.order"
    _inherit = ["purchase.order", "mercas.box.order.mixin"]

    _mercas_box_link_field = "box_purchase_line_id"
    _mercas_box_qty_field = "product_qty"
    _mercas_section_vals = {"product_qty": 0}

    mercas_origin_country = fields.Boolean(related="company_id.origin_country")
    mercas_origin_state = fields.Boolean(related="company_id.origin_state")
    mercas_origin_filter = fields.Boolean(related="company_id.origin_filter")

    def action_open_box_delivery(self):
        """Open a new sale order to deliver boxes back to this purchase's supplier."""
        self.ensure_one()
        if not self.env["product.template"]._mercas_any_box_product_exists():
            raise UserError(_("There is no product marked as a box/container."))
        new_so = self.env["sale.order"].create({
            "partner_id": self.partner_id.id,
            "origin": self.name,
            "box_delivery_purchase_id": self.id,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": new_so.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_print_mercas_labels(self):
        """Open the wizard to print product labels for this purchase's boxes."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Print Labels"),
            "res_model": "mercas.label.print.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_purchase_id": self.id},
        }

    mercas_is_box_return = fields.Boolean(
        compute="_compute_mercas_is_box_return",
        store=True,
        string="Is Box Return",
    )

    @api.depends("order_line.display_type", "order_line.product_id.is_box")
    def _compute_mercas_is_box_return(self):
        for order in self:
            product_lines = order.order_line.filtered(lambda l: not l.display_type)
            order.mercas_is_box_return = bool(product_lines) and all(
                line.product_id.is_box for line in product_lines
            )

    def button_confirm(self):
        # Pre-confirm: auto-create lots for tracked lines without one
        for order in self:
            if order.company_id.purchase_lot_autocomplete:
                order._mercas_autocreate_lots()

        # Regular purchases (not box-return): ensure supplier location and
        # auto-create box lines before confirming, same treatment as sales,
        # so the box product is included in the receipt generated on confirm.
        regular_orders = self.filtered(lambda o: not o.mercas_is_box_return)
        for order in regular_orders:
            order.partner_id.mercas_ensure_supplier_location(order.company_id)
            order._mercas_prepare_box_lines()

        result = super().button_confirm()

        # Sync partner to all lots on confirmed lines that still lack it
        for order in self:
            for line in order.order_line.filtered(
                lambda l: l.lot_id and not l.lot_id.partner_id
            ):
                line.lot_id.partner_id = order.partner_id

        return result

    def _mercas_autocreate_lots(self):
        """Auto-assign new lots to tracked lines that have no lot set."""
        Lot = self.env["stock.lot"]
        for line in self.order_line:
            if line.product_id.tracking in ("lot", "serial") and not line.lot_id:
                line.lot_id = Lot.create({
                    "product_id": line.product_id.id,
                    "company_id": self.company_id.id,
                    "partner_id": self.partner_id.id,
                    "origin_country_id": line.origin_country_id.id,
                    "origin_state_id": line.origin_state_id.id,
                    "mercas_firm_negotiation": line.mercas_firm_negotiation,
                })

    def action_mercas_box_receive_and_invoice(self):
        """Button target: receive the boxes and invoice the supplier now, for a
        box-return order (mercas_is_box_return). A deliberate user action, not
        automatic on confirm, so a purchase that happens to contain only box
        products for an unrelated reason never triggers this by accident."""
        self.ensure_one()
        return self._mercas_box_confirm_flow()

    def _mercas_box_confirm_flow(self):
        """Receive boxes from customer location, create vendor bill and post it."""
        self.ensure_one()

        # Ensure the partner has a sub-location under the mercas parent (same logic as sales)
        self.partner_id.mercas_ensure_customer_location(self.company_id)

        partner = self.partner_id.commercial_partner_id
        customer_loc = partner.with_company(self.company_id).property_stock_customer

        pending = self.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
        for picking in pending:
            active_moves = picking.move_ids.filtered(
                lambda m: m.state not in ("done", "cancel")
            )
            # Set done qty to trigger move_line creation
            for move in active_moves:
                move.quantity = move.product_uom_qty
            # Redirect source from virtual supplier to the customer's physical location
            if customer_loc:
                picking.move_line_ids.write({"location_id": customer_loc.id})
            picking._mercas_validate()

        # Create and immediately post the vendor bill (deposit refund)
        self.action_create_invoice()
        invoice = self.invoice_ids.filtered(lambda i: i.state == "draft")[:1]
        if not invoice:
            return True
        invoice.invoice_date = fields.Date.context_today(self)
        invoice.action_post()

        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": invoice.id,
            "view_mode": "form",
            "target": "current",
        }

    def _mercas_standard_bill_lines(self):
        """Lines still to invoice with the standard bill of the purchase: all
        but the ones invoiced from their lot (see
        purchase.order.line._mercas_is_invoiced_from_lot)."""
        precision = self.env["decimal.precision"].precision_get("Product Unit")
        return self.order_line.filtered(
            lambda l: not l.display_type
            and not l._mercas_is_invoiced_from_lot()
            and not float_is_zero(l.qty_to_invoice, precision_digits=precision)
        )

    def action_create_invoice(self, attachment_ids=False):
        """The standard bill leaves out the lines invoiced from their lot:
        billing them at the price of the purchase would skip the sale
        settlement, and the lot would be invoiced twice when settled."""
        with_lots = self.filtered(
            lambda o: any(line._mercas_is_invoiced_from_lot() for line in o.order_line)
        )
        if with_lots and not self._mercas_standard_bill_lines():
            raise UserError(
                _("The lines with a lot of %s are invoiced from their lots: "
                  "settlement, advance or firm invoice.")
                % ", ".join(with_lots.mapped("name"))
            )
        previous = self.invoice_ids
        result = super().action_create_invoice(attachment_ids=attachment_ids)
        lot_lines = with_lots.order_line - with_lots.order_line._mercas_without_lot_lines()
        for invoice in self.invoice_ids - previous:
            to_remove = invoice.invoice_line_ids.filtered(
                lambda l: l.purchase_line_id in lot_lines
            )
            if to_remove:
                invoice.write({
                    "invoice_line_ids": [Command.delete(line.id) for line in to_remove],
                })
        return result

    def button_purchase_and_receive(self):
        """Confirm the PO and validate receipts. For box-return orders this also
        runs the automated receive+invoice flow (same as the "Receive & Invoice"
        button) since this shortcut is itself an explicit "do it all now" action.
        For regular orders the invoice is created manually by the user."""
        self.button_confirm()
        if self.mercas_is_box_return:
            self._mercas_box_confirm_flow()
        else:
            self._mercas_auto_receive()

    def _mercas_auto_receive(self):
        pending = self.picking_ids.filtered(
            lambda p: p.state not in ("done", "cancel")
        )
        for picking in pending:
            for move in picking.move_ids.filtered(
                lambda m: m.state not in ("done", "cancel")
            ):
                move.quantity = move.product_uom_qty
            picking._mercas_validate()


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    box_qty = fields.Integer(string="Boxes", default=0)
    box_purchase_line_id = fields.Many2one(
        comodel_name="purchase.order.line",
        string="Product Line",
        ondelete="cascade",
        copy=False,
        index=True,
    )
    box_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Box",
        compute="_compute_box_product_id",
        store=True,
        readonly=False,
        domain=[("is_box", "=", True)],
    )
    origin_country_id = fields.Many2one(
        comodel_name="res.country",
        string="Country of Origin",
    )
    origin_state_id = fields.Many2one(
        comodel_name="res.country.state",
        string="State of Origin",
        domain="[('country_id', '=', origin_country_id)]",
    )
    mercas_firm_negotiation = fields.Boolean(
        string="Firm Negotiation",
        compute="_compute_mercas_firm_negotiation",
        store=True,
        readonly=False,
        help=(
            "The supplier is paid in full for what was received on this "
            "line, regardless of what was sold. Defaults to the value "
            "configured on the supplier, but can be changed here. It is "
            "carried over to the lot when the purchase is confirmed."
        ),
    )

    def _mercas_is_invoiced_from_lot(self):
        """A line with a lot under sale settlement is invoiced from the lot
        (settlement or advance). Under firm negotiation the standard bill
        does it, unless the lot was already invoiced from the lot (an
        advance before turning firm, a firm invoice of the lot): then the
        lot goes on, to deduct those invoices and not to invoice twice."""
        self.ensure_one()
        lot = self.lot_id
        if not lot:
            return False
        if not lot.mercas_firm_negotiation:
            return True
        return bool(lot.supplier_invoice_line_ids.filtered(
            lambda l: l.move_id.state != "cancel" and not l.purchase_line_id
        ))

    def _mercas_without_lot_lines(self):
        """These lines but the ones invoiced from their lot, and the sections
        and subsections left empty without them."""
        headers = ("line_section", "line_subsection")
        kept = self.browse()
        for order in self.order_id:
            pending = []  # open headers, waiting for a line under them
            for line in self.filtered(lambda l: l.order_id == order).sorted(lambda l: (l.sequence, l.id)):
                if line.display_type in headers:
                    level = headers.index(line.display_type)
                    pending = [h for h in pending if headers.index(h.display_type) < level] + [line]
                elif not line._mercas_is_invoiced_from_lot():
                    kept |= self.browse([h.id for h in pending]) | line
                    pending = []
        return self.filtered(lambda l: l in kept)

    @api.depends("order_id.partner_id")
    def _compute_mercas_firm_negotiation(self):
        for line in self:
            line.mercas_firm_negotiation = line.order_id.partner_id.mercas_firm_negotiation

    @api.depends("product_id")
    def _compute_box_product_id(self):
        for line in self:
            if line.display_type or line.box_purchase_line_id:
                line.box_product_id = False
            else:
                line.box_product_id = line.product_id.product_tmpl_id.box_product_id

    def _prepare_account_move_line(self, move=False):
        vals = super()._prepare_account_move_line(move)
        if self.lot_id:
            vals["lot_id"] = self.lot_id.id
            # The received kg of a firm lot billed at the purchase price: they
            # count as invoiced in the lot (net_invoiced_kg)
            vals["mercas_is_firm_line"] = self.lot_id.mercas_firm_negotiation
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        # A product line added after confirmation needs the same treatment
        # button_confirm applies on first confirm -- lot autocreation and
        # PRODUCTOS/Envases classification -- otherwise it's left untracked
        # and out of both sections.
        trigger_lines = lines.filtered(
            lambda l: not l.display_type and not l.box_purchase_line_id
        )
        confirmed_orders = trigger_lines.order_id.filtered(
            lambda o: o.state in ("purchase", "done")
        )
        for order in confirmed_orders:
            if order.company_id.purchase_lot_autocomplete:
                order._mercas_autocreate_lots()
            order._mercas_prepare_box_lines()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if "lot_id" in vals and vals.get("lot_id"):
            for line in self.filtered(lambda l: l.lot_id and not l.lot_id.partner_id):
                line.lot_id.partner_id = line.order_id.partner_id
            for line in self.filtered(
                lambda l: l.lot_id and (l.origin_country_id or l.origin_state_id)
            ):
                update = {}
                if line.origin_country_id:
                    update["origin_country_id"] = line.origin_country_id.id
                if line.origin_state_id:
                    update["origin_state_id"] = line.origin_state_id.id
                line.lot_id.write(update)
        if "origin_country_id" in vals or "origin_state_id" in vals:
            for line in self.filtered(lambda l: l.lot_id):
                update = {}
                if "origin_country_id" in vals:
                    update["origin_country_id"] = line.origin_country_id.id or False
                if "origin_state_id" in vals:
                    update["origin_state_id"] = line.origin_state_id.id or False
                line.lot_id.write(update)
        if vals.get("lot_id") or "mercas_firm_negotiation" in vals:
            for line in self.filtered(lambda l: l.lot_id):
                line.lot_id.with_context(mercas_propagate_firm_negotiation=True).write(
                    {"mercas_firm_negotiation": line.mercas_firm_negotiation}
                )
        if "box_qty" in vals or "box_product_id" in vals or "product_id" in vals:
            lines_to_check = self.filtered(lambda l: not l.display_type and not l.box_purchase_line_id)
            if lines_to_check:
                # One search for every affected line's box line instead of
                # one per line -- a multi-line update (e.g. a bulk quantity
                # change) would otherwise do N queries here.
                all_box_lines = self.env["purchase.order.line"].search(
                    [("box_purchase_line_id", "in", lines_to_check.ids)]
                )
                box_lines_by_parent = all_box_lines.grouped("box_purchase_line_id")

                to_unlink = self.env["purchase.order.line"]
                for line in lines_to_check:
                    box_lines = box_lines_by_parent.get(line)
                    if not box_lines:
                        continue
                    if "box_qty" in vals and line.box_qty == 0:
                        to_unlink |= box_lines
                        continue
                    update = {}
                    if "box_qty" in vals:
                        update["product_qty"] = line.box_qty
                    if ("box_product_id" in vals or "product_id" in vals) and line.box_product_id:
                        update["product_id"] = line.box_product_id.id
                    if update:
                        box_lines.write(update)
                if to_unlink:
                    to_unlink.unlink()

                # A previously box-less line that just got a box_qty/box_product_id
                # (or a product change that gives it one) needs its box line
                # created, same as create() -- write() above only updates lines
                # that already had one.
                confirmed_orders = lines_to_check.order_id.filtered(
                    lambda o: o.state in ("purchase", "done")
                )
                for order in confirmed_orders:
                    if "product_id" in vals and order.company_id.purchase_lot_autocomplete:
                        order._mercas_autocreate_lots()
                    order._mercas_prepare_box_lines()
        return result
