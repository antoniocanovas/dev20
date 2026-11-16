from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockLotInventoryWizard(models.TransientModel):
    """Count the stock of a lot: the quantity is set on the lot's quant and
    applied as a standard inventory adjustment (stock.quant in inventory
    mode), so the difference goes to the inventory loss location and shows
    up in the lot's "Scrapped" like any other adjustment."""

    _name = "stock.lot.inventory.wizard"
    _description = "Lot Inventory Adjustment"

    lot_id = fields.Many2one(comodel_name="stock.lot", string="Lot", required=True, readonly=True)
    product_id = fields.Many2one(related="lot_id.product_id")
    product_uom_id = fields.Many2one(related="lot_id.product_id.uom_id", string="UoM")
    company_id = fields.Many2one(comodel_name="res.company", required=True)
    location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Location",
        required=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False])]",
    )
    current_qty = fields.Float(
        string="On Hand",
        compute="_compute_current_qty",
        digits="Product Unit",
    )
    counted_qty = fields.Float(string="Counted Quantity", digits="Product Unit")
    difference_qty = fields.Float(
        string="Difference",
        compute="_compute_difference_qty",
        digits="Product Unit",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        lot = self.env["stock.lot"].browse(res.get("lot_id") or self.env.context.get("default_lot_id"))
        if not lot:
            return res
        company = lot._mercas_company()
        res.setdefault("company_id", company.id)
        if not res.get("location_id"):
            res["location_id"] = lot._mercas_inventory_location(company).id
        if "counted_qty" in fields_list and "counted_qty" not in res:
            res["counted_qty"] = sum(lot._mercas_location_quants(
                self.env["stock.location"].browse(res["location_id"])
            ).mapped("quantity"))
        return res

    @api.depends("lot_id", "location_id")
    def _compute_current_qty(self):
        for wizard in self:
            wizard.current_qty = sum(
                wizard.lot_id._mercas_location_quants(wizard.location_id).mapped("quantity")
            ) if wizard.lot_id and wizard.location_id else 0.0

    @api.depends("current_qty", "counted_qty")
    def _compute_difference_qty(self):
        for wizard in self:
            wizard.difference_qty = wizard.counted_qty - wizard.current_qty

    def action_apply(self):
        self.ensure_one()
        self.lot_id._mercas_apply_inventory(self.counted_qty, self.location_id)
        return {"type": "ir.actions.act_window_close"}
