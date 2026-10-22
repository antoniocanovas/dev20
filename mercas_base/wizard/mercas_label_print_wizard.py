from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class MercasLabelPrintWizard(models.TransientModel):
    _name = "mercas.label.print.wizard"
    _description = "Print Box Labels (product + lot)"

    purchase_id = fields.Many2one(comodel_name="purchase.order", string="Purchase Order")
    sale_id = fields.Many2one(comodel_name="sale.order", string="Sale Order")
    print_format = fields.Selection(
        [
            ("dymo", "Dymo"),
            ("2x7xprice", "2 x 7 with price"),
            ("4x7xprice", "4 x 7 with price"),
            ("4x12", "4 x 12"),
            ("4x12xprice", "4 x 12 with price"),
        ],
        string="Format",
        default="2x7xprice",
        required=True,
    )
    line_ids = fields.One2many(
        comodel_name="mercas.label.print.wizard.line",
        inverse_name="wizard_id",
        string="Labels",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "line_ids" not in fields_list:
            return res

        lot_ids = self.env.context.get("mercas_label_lot_ids")
        if lot_ids:
            res["line_ids"] = self._lot_label_lines(self.env["stock.lot"].browse(lot_ids))
            return res

        order = None
        box_line_field = None
        if res.get("purchase_id"):
            order = self.env["purchase.order"].browse(res["purchase_id"])
            box_line_field = "box_purchase_line_id"
        elif res.get("sale_id"):
            order = self.env["sale.order"].browse(res["sale_id"])
            box_line_field = "box_sale_line_id"
        if not order:
            return res

        lines = order.order_line.filtered(
            lambda l: not l.display_type
            and not l[box_line_field]
            and l.product_id.type == "consu"
            and not l.product_id.is_box
        )
        res["line_ids"] = [
            Command.create({
                "product_id": line.product_id.id,
                "lot_id": line.lot_id.id,
                "quantity": line.box_qty,
            })
            for line in lines
        ]
        return res

    @api.model
    def _lot_label_lines(self, lots):
        """Lines to reprint the labels of `lots`: as many as boxes were
        bought of each lot, or one when the purchase doesn't tell."""
        groups = self.env["purchase.order.line"]._read_group(
            [
                ("lot_id", "in", lots.ids),
                ("state", "in", ("purchase", "done")),
                ("box_purchase_line_id", "=", False),
            ],
            ["lot_id"], ["box_qty:sum"],
        )
        boxes = {lot: box_qty for lot, box_qty in groups}
        return [
            Command.create({
                "product_id": lot.product_id.id,
                "lot_id": lot.id,
                "quantity": boxes.get(lot) or 1,
            })
            for lot in lots
        ]

    def action_print(self):
        self.ensure_one()
        printable = self.line_ids.filtered(lambda l: l.product_id and l.quantity > 0)
        if not printable:
            raise UserError(
                _("Enter a label quantity greater than zero on at least one line.")
            )

        # One entry per (product, lot): the same lot on two order lines
        # prints as a single run of labels.
        quantity_by_key = {}
        for line in printable:
            key = (line.product_id.id, line.lot_id.id or False)
            quantity_by_key[key] = quantity_by_key.get(key, 0) + line.quantity

        # Own report (see report/mercas_box_label.py) instead of the standard
        # product labels: those only know the product, and each box label
        # must also carry its lot, expiration and origin.
        xml_id = (
            "mercas_base.action_report_mercas_box_label_dymo"
            if self.print_format == "dymo"
            else "mercas_base.action_report_mercas_box_label"
        )
        data = {
            "print_format": self.print_format,
            "labels": [
                [product_id, lot_id, qty]
                for (product_id, lot_id), qty in quantity_by_key.items()
            ],
        }
        report_action = self.env.ref(xml_id).report_action(None, data=data, config=False)
        report_action.update({"close_on_report_download": True})
        return report_action


class MercasLabelPrintWizardLine(models.TransientModel):
    _name = "mercas.label.print.wizard.line"
    _description = "Label Print Line"

    wizard_id = fields.Many2one(
        comodel_name="mercas.label.print.wizard",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(comodel_name="product.product", string="Product", readonly=True)
    lot_id = fields.Many2one(comodel_name="stock.lot", string="Lot", readonly=True)
    quantity = fields.Integer(string="Labels", default=1)
