from odoo import _, api, fields, models

MERCAS_LINES_BUS_NOTIFICATION_TYPE = "mercas_sale_order_lines_updated"


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    box_qty = fields.Integer(
        string="Boxes",
        compute="_compute_box_qty",
        store=True,
        readonly=False,
    )
    box_sale_line_id = fields.Many2one(
        comodel_name="sale.order.line",
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
    mercas_product_is_box = fields.Boolean(related="product_id.is_box")
    mercas_has_assigned_lot = fields.Boolean(
        compute="_compute_mercas_has_assigned_lot",
        help="Has at least one delivery move line (done or pending) with a "
             "lot assigned: the lot can be corrected, before or after the "
             "order is delivered.",
    )
    product_qty_datetime = fields.Datetime(
        string="Quantity Updated On",
        copy=False,
        help="Date and time the line was created (with its initial "
             "quantity) or, if later, when the quantity was last modified.",
    )

    @api.depends("move_ids.move_line_ids.state", "move_ids.move_line_ids.lot_id")
    def _compute_mercas_has_assigned_lot(self):
        for line in self:
            line.mercas_has_assigned_lot = bool(
                line.move_ids.move_line_ids.filtered(
                    lambda ml: ml.state != "cancel" and ml.lot_id
                )
            )

    def action_open_lot_change_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Correct Sale Lot"),
            "res_model": "stock.lot.change.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_sale_line_id": self.id},
        }

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        for vals in vals_list:
            if not vals.get("display_type") and "product_qty_datetime" not in vals:
                vals["product_qty_datetime"] = now
        lines = super().create(vals_list)
        lines._mercas_notify_lines_changed(lines.order_id)
        # A product line added after confirmation needs the same PRODUCTOS/
        # Envases classification that action_confirm applies on first
        # confirm -- otherwise it's left out of both sections.
        trigger_lines = lines.filtered(
            lambda l: not l.display_type and not l.box_sale_line_id
        )
        confirmed_orders = trigger_lines.order_id.filtered(
            lambda o: o.state in ("sale", "done")
        )
        for order in confirmed_orders:
            order._mercas_prepare_box_lines()
        return lines

    @api.depends("product_id", "product_uom_id", "product_uom_qty")
    def _compute_box_qty(self):
        for line in self:
            if line.product_uom_id and line.product_uom_id in line.product_id.uom_ids:
                line.box_qty = line.product_uom_qty
            else:
                line.box_qty = line.box_qty

    @api.depends("product_id")
    def _compute_box_product_id(self):
        for line in self:
            if line.display_type or line.box_sale_line_id:
                line.box_product_id = False
            else:
                line.box_product_id = line.product_id.product_tmpl_id.box_product_id

    def _prepare_invoice_line(self, **optional_values):
        vals = super()._prepare_invoice_line(**optional_values)
        if self.lot_id:
            vals["lot_id"] = self.lot_id.id
        return vals

    def get_available_lots_for_line(self):
        result = super().get_available_lots_for_line()
        if not result or not result.get("available"):
            return result

        invoiced_lot_ids = set(
            self.env["stock.lot"]
            .search(
                [
                    ("id", "in", [item["id"] for item in result["available"]]),
                    ("invoiced", "=", True),
                ]
            )
            .ids
        )
        if invoiced_lot_ids:
            result["available"] = [
                item
                for item in result["available"]
                if item["id"] not in invoiced_lot_ids
            ]
        return result

    def write(self, vals):
        changed_qty_lines = self.env["sale.order.line"]
        if "product_uom_qty" in vals:
            changed_qty_lines = self.filtered(
                lambda l: l.product_uom_qty != vals["product_uom_qty"]
            )
        result = super().write(vals)
        if changed_qty_lines:
            changed_qty_lines.product_qty_datetime = fields.Datetime.now()
        if "box_qty" in vals or "box_product_id" in vals or "product_id" in vals:
            lines_to_check = self.filtered(lambda l: not l.display_type and not l.box_sale_line_id)
            if lines_to_check:
                # One search for every affected line's box line instead of
                # one per line -- a multi-line update (e.g. a bulk quantity
                # change) would otherwise do N queries here.
                all_box_lines = self.env["sale.order.line"].search(
                    [("box_sale_line_id", "in", lines_to_check.ids)]
                )
                box_lines_by_parent = {}
                for box_line in all_box_lines:
                    box_lines_by_parent.setdefault(
                        box_line.box_sale_line_id.id, self.env["sale.order.line"]
                    )
                    box_lines_by_parent[box_line.box_sale_line_id.id] |= box_line

                to_unlink = self.env["sale.order.line"]
                for line in lines_to_check:
                    box_lines = box_lines_by_parent.get(line.id)
                    if not box_lines:
                        continue
                    if "box_qty" in vals and line.box_qty == 0:
                        to_unlink |= box_lines
                        continue
                    update = {}
                    if "box_qty" in vals:
                        update["product_uom_qty"] = line.box_qty
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
                    lambda o: o.state in ("sale", "done")
                )
                for order in confirmed_orders:
                    order._mercas_prepare_box_lines()
        self._mercas_notify_lines_changed(self.order_id)
        return result

    def unlink(self):
        orders = self.order_id
        result = super().unlink()
        self._mercas_notify_lines_changed(orders)
        return result

    def _mercas_notify_lines_changed(self, orders):
        """Notify over the bus anyone who has one of these orders open that
        its lines have changed, so it can offer to reload the view (see
        static/src/js/sale_order_lines_bus_notification.js)."""
        for order in orders:
            self.env["bus.bus"]._sendone(
                self._mercas_lines_bus_channel(order.id),
                MERCAS_LINES_BUS_NOTIFICATION_TYPE,
                {
                    "order_id": order.id,
                    "user_id": self.env.user.id,
                    "user_name": self.env.user.name,
                },
            )

    @api.model
    def _mercas_lines_bus_channel(self, order_id):
        return "mercas_sale_order_lines-%s" % order_id
