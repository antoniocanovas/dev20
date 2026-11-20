from odoo import api, fields, models


class MercasWeighedLineMixin(models.AbstractModel):
    """Weights of an order line sold or bought with boxes: the quantity of the
    line is the net weight (the one priced), the tare is the weight of its
    boxes and the gross weight is the one of the scale, net + tare.

    The tare is kept on the line when its boxes are set, so a later change of
    the weight of the box doesn't change the weight that was weighed. Setting
    the gross weight sets the net one (gross - tare) on lines in a unit of
    weight."""

    _name = "mercas.weighed.line.mixin"
    _description = "Order Line Weighed with its Boxes"

    # Field of the quantity of the line, in its unit (_mercas_uom_field)
    _mercas_qty_field = None
    # Field of the unit of the line: uom_id on the purchase lines of v20
    _mercas_uom_field = "product_uom_id"

    mercas_tare = fields.Float(
        string="Tare",
        digits="Stock Weight",
        compute="_compute_mercas_tare",
        store=True,
        readonly=False,
        help="Weight of the boxes of the line: boxes × weight of the box "
             "product. Set when the boxes change, so it can be corrected by "
             "hand.",
    )
    mercas_gross_weight = fields.Float(
        string="Gross Weight",
        digits="Stock Weight",
        compute="_compute_mercas_gross_weight",
        inverse="_inverse_mercas_gross_weight",
        help="Weight on the scale: net weight + tare. On lines in a unit of "
             "weight, setting it sets the quantity (net weight = gross - "
             "tare).",
    )
    mercas_weighed = fields.Boolean(
        string="Weighed",
        compute="_compute_mercas_weighed",
        help="The line is in a unit of weight: its quantity is its net weight.",
    )

    # The fields of the lines are only on the models that use the mixin
    @api.depends(lambda self: ("box_qty", "box_product_id") if self._mercas_qty_field else ())
    def _compute_mercas_tare(self):
        for line in self:
            line.mercas_tare = line.box_qty * line.box_product_id.weight if line.box_product_id else 0.0

    def _mercas_qty(self):
        return self[self._mercas_qty_field]

    def _mercas_uom(self):
        return self[self._mercas_uom_field]

    def _mercas_net_weight(self):
        """Net weight of the line, in the weight unit of the products."""
        self.ensure_one()
        if not self.product_id:
            return 0.0
        return self.product_id._mercas_net_weight(self._mercas_qty(), self._mercas_uom())

    @api.depends(lambda self: (
        (self._mercas_qty_field, self._mercas_uom_field, "product_id.weight", "mercas_tare")
        if self._mercas_qty_field else ()
    ))
    def _compute_mercas_gross_weight(self):
        for line in self:
            line.mercas_gross_weight = line._mercas_net_weight() + line.mercas_tare if line.product_id else 0.0

    @api.depends(lambda self: ("product_id", self._mercas_uom_field) if self._mercas_qty_field else ())
    def _compute_mercas_weighed(self):
        for line in self:
            line.mercas_weighed = line._mercas_is_weighed()

    def _mercas_is_weighed(self):
        self.ensure_one()
        return bool(self.product_id) and self.product_id._mercas_is_weighed(self._mercas_uom())

    def _inverse_mercas_gross_weight(self):
        # Not mercas_weighed: while the gross weight is written, the fields of
        # its computation are protected and could read their default
        for line in self:
            if line._mercas_is_weighed():
                line[self._mercas_qty_field] = line._mercas_qty_from_gross(line.mercas_gross_weight)

    def _mercas_qty_from_gross(self, gross):
        """Quantity of the line, in its unit, of the net weight left by `gross`."""
        self.ensure_one()
        weight_uom = self.env["product.template"]._get_weight_uom_id_from_ir_config_parameter()
        return weight_uom._compute_quantity(max(gross - self.mercas_tare, 0.0), self._mercas_uom(), round=False)

    @api.onchange("mercas_gross_weight")
    def _onchange_mercas_gross_weight(self):
        # The net weight at once in the form, not only when it is saved
        for line in self:
            if line._mercas_is_weighed():
                line[self._mercas_qty_field] = line._mercas_qty_from_gross(line.mercas_gross_weight)

    def _mercas_invoice_weight_vals(self, quantity):
        """Boxes and tare of an invoice line of `quantity` (in the unit of
        the line) of this line: in proportion when it invoices only a part."""
        self.ensure_one()
        if not self.box_qty and not self.mercas_tare:
            return {}
        line_qty = self._mercas_qty()
        ratio = abs(quantity / line_qty) if line_qty else 1.0
        return {
            "box_qty": round(self.box_qty * ratio),
            "mercas_tare": self.mercas_tare * ratio,
        }
