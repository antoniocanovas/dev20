from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

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

    def _mercas_prepare_box_lines(self):
        """Add PRODUCTOS/Envases sections, create/refresh one box line per
        product line with box_qty > 0 (using the box product's purchase
        price, same logic as sales), and re-sequence every line so it stays
        inside the section it belongs to. Runs again after confirm (from
        line create/write) so lines added later are grouped too, instead of
        trailing after Envases where the UI appends new rows by default."""
        PurchaseLine = self.env["purchase.order.line"]

        product_lines = self.order_line.filtered(
            lambda l: not l.display_type and not l.box_purchase_line_id
        )
        has_productos = self.order_line.filtered(
            lambda l: l.display_type == "line_section" and l.name == "PRODUCTOS"
        )
        box_lines_needed = product_lines.filtered(
            lambda l: l.box_qty > 0 and l.box_product_id
        )
        if not product_lines or (not box_lines_needed and not has_productos):
            return

        # --- PRODUCTOS section ---
        if has_productos:
            productos_section = has_productos[0]
        else:
            productos_section = PurchaseLine.create({
                "order_id": self.id,
                "display_type": "line_section",
                "name": "PRODUCTOS",
                "sequence": 0,
                "product_qty": 0,
            })

        # --- Envases section ---
        has_envases = self.order_line.filtered(
            lambda l: l.display_type == "line_section" and l.name == "Envases"
        )
        if has_envases:
            envases_section = has_envases[0]
        else:
            envases_section = PurchaseLine.create({
                "order_id": self.id,
                "display_type": "line_section",
                "name": "Envases",
                "sequence": 0,
                "product_qty": 0,
            })

        # --- Create / update box lines ---
        existing_by_parent = {
            bl.box_purchase_line_id.id: bl
            for bl in self.order_line.filtered(lambda l: l.box_purchase_line_id)
        }
        for line in box_lines_needed:
            if line.id in existing_by_parent:
                existing_by_parent[line.id].write({
                    "product_id": line.box_product_id.id,
                    "product_qty": line.box_qty,
                })
            else:
                PurchaseLine.create({
                    "order_id": self.id,
                    "product_id": line.box_product_id.id,
                    "product_qty": line.box_qty,
                    "box_purchase_line_id": line.id,
                })

        self._mercas_reorder_box_sections(productos_section, envases_section)

    def _mercas_reorder_box_sections(self, productos_section, envases_section):
        """Renumber sequence so every line sits inside its section: PRODUCTOS,
        then all product lines (keeping their current relative order), then
        Envases, then all box lines (following their parent line's order)."""
        product_lines = self.order_line.filtered(
            lambda l: not l.display_type and not l.box_purchase_line_id
        ).sorted(key=lambda l: (l.sequence, l.id))
        box_lines_by_parent = {
            bl.box_purchase_line_id.id: bl
            for bl in self.order_line.filtered(lambda l: l.box_purchase_line_id)
        }

        seq = 0
        productos_section.sequence = seq
        for line in product_lines:
            seq += 10
            line.sequence = seq

        seq += 10
        envases_section.sequence = seq

        for line in product_lines:
            box_line = box_lines_by_parent.get(line.id)
            if box_line:
                seq += 10
                box_line.sequence = seq

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
            picking.with_context(
                skip_immediate=True,
                skip_backorder=True,
            ).button_validate()

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
            picking.with_context(
                skip_immediate=True,
                skip_backorder=True,
            ).button_validate()


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
            for line in self.filtered(lambda l: l.lot_id):
                line.lot_id.with_context(mercas_propagate_firm_negotiation=True).write(
                    {"mercas_firm_negotiation": line.mercas_firm_negotiation}
                )
        if "origin_country_id" in vals or "origin_state_id" in vals:
            for line in self.filtered(lambda l: l.lot_id):
                update = {}
                if "origin_country_id" in vals:
                    update["origin_country_id"] = line.origin_country_id.id or False
                if "origin_state_id" in vals:
                    update["origin_state_id"] = line.origin_state_id.id or False
                line.lot_id.write(update)
        if "mercas_firm_negotiation" in vals:
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
                box_lines_by_parent = {}
                for box_line in all_box_lines:
                    box_lines_by_parent.setdefault(
                        box_line.box_purchase_line_id.id, self.env["purchase.order.line"]
                    )
                    box_lines_by_parent[box_line.box_purchase_line_id.id] |= box_line

                to_unlink = self.env["purchase.order.line"]
                for line in lines_to_check:
                    box_lines = box_lines_by_parent.get(line.id)
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
