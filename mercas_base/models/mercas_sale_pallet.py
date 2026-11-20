from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MercasSalePallet(models.Model):
    """A pallet of a sale: how many boxes of each line go on it.

    Only the pallets are packages of the delivery (stock.package); the boxes
    are worked out from their line (its kg divided by its boxes)."""

    _name = "mercas.sale.pallet"
    _description = "Pallet of a Sale"
    _order = "order_id, sequence, id"

    order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Sale",
        required=True,
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(related="order_id.company_id", store=True)
    sequence = fields.Integer(default=1)
    name = fields.Char(compute="_compute_name")
    package_type_id = fields.Many2one(
        comodel_name="stock.package.type",
        string="Pallet Type",
        required=True,
        domain=[("mercas_is_pallet", "=", True)],
    )
    height = fields.Float(
        help="Height of this pallet, loaded, in the length unit of the package "
             "types. Empty: the height of its type. Used for the volume of the "
             "packing list.",
    )
    package_id = fields.Many2one(
        comodel_name="stock.package",
        string="Package",
        readonly=True,
        copy=False,
        help="Package of the delivery for this pallet, created when the sale is delivered.",
    )
    line_ids = fields.One2many(
        comodel_name="mercas.sale.pallet.line",
        inverse_name="pallet_id",
        string="Contents",
        copy=True,
    )
    box_qty = fields.Integer(string="Boxes", compute="_compute_box_qty")

    @api.depends("sequence")
    def _compute_name(self):
        for pallet in self:
            pallet.name = _("Pallet %s", pallet.sequence)

    @api.depends("line_ids.box_qty")
    def _compute_box_qty(self):
        for pallet in self:
            pallet.box_qty = sum(pallet.line_ids.mapped("box_qty"))


class MercasSalePalletLine(models.Model):
    _name = "mercas.sale.pallet.line"
    _description = "Boxes of a Sale Line on a Pallet"
    _order = "pallet_id, id"

    pallet_id = fields.Many2one(
        comodel_name="mercas.sale.pallet",
        string="Pallet",
        required=True,
        index=True,
        ondelete="cascade",
    )
    sale_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        string="Sale Line",
        required=True,
        index=True,
        ondelete="cascade",
    )
    box_qty = fields.Integer(string="Boxes", required=True)

    _box_qty_positive = models.Constraint(
        "CHECK(box_qty > 0)",
        "The boxes of a line on a pallet must be more than zero.",
    )

    @api.constrains("box_qty", "sale_line_id", "pallet_id")
    def _check_box_qty(self):
        for sale_line in self.sale_line_id:
            if sale_line.order_id != self.filtered(lambda l: l.sale_line_id == sale_line).pallet_id.order_id:
                raise ValidationError(_("A pallet can only hold lines of its own sale."))
            on_pallets = sum(self.search([("sale_line_id", "=", sale_line.id)]).mapped("box_qty"))
            if on_pallets > sale_line.box_qty:
                raise ValidationError(_(
                    "%(product)s has %(boxes)s boxes but %(pallets)s are on pallets.",
                    product=sale_line.product_id.display_name,
                    boxes=sale_line.box_qty,
                    pallets=on_pallets,
                ))
