from odoo import _, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    supplier_ref = fields.Char(
        string="Supplier Delivery Note",
        copy=False,
        index="trigram",
        help="Code of the supplier's delivery note for this receipt. The "
             "Auto-Complete of the vendor bill also finds the purchase by it.",
    )

    def _action_done(self):
        res = super()._action_done()
        # The goods of the deliveries go on the packages of their pallets
        for picking in self.filtered(
            lambda p: p.state == "done" and p.picking_type_code == "outgoing" and p.sale_id.mercas_pallet_ids
        ):
            picking.sale_id._mercas_apply_pallets(pickings=picking, initial=True)
        return res

    def action_print_mercas_packing_list(self):
        self.ensure_one()
        return self.env.ref("mercas_base.action_report_mercas_packing_list_picking").report_action(self)

    def _mercas_delivery_weights(self):
        """Boxes and weights of a delivery of a sale, for its delivery note,
        or False when none of its goods has boxes or tare (the delivery note
        keeps the standard columns then):

        - lines: {move line id: boxes, net, tare and gross weight}. The boxes
          of each line of the sale are shared out in whole boxes among its
          move lines (lots, pallets) in proportion to their quantity, and its
          tare with the boxes.
        - packaging: move lines of the boxes and pallets delivered (products
          that are boxes), printed in a table of their own.
        - totals: of the lines, plus the tare of the pallets (the weight of
          their type). A pallet weighed (shipping weight of its package)
          counts with that weight, as in the packing list.

        Weights in the weight unit of the products."""
        self.ensure_one()
        move_lines = self.move_ids.move_line_ids
        goods = move_lines.filtered(lambda ml: not ml.product_id.is_box)
        rows = {}
        for sale_line, line_mls in goods.grouped(lambda ml: ml.move_id.sale_line_id).items():
            qtys = [
                ml.uom_id._compute_quantity(ml.quantity, sale_line.product_uom_id, round=False)
                if sale_line else ml.quantity
                for ml in line_mls
            ]
            boxes_total = 0
            if sale_line.box_qty and sale_line.product_uom_qty:
                boxes_total = round(sale_line.box_qty * sum(qtys) / sale_line.product_uom_qty)
            for ml, boxes in zip(line_mls, self._mercas_share_out(boxes_total, qtys)):
                net = ml.product_id._mercas_net_weight(ml.quantity, ml.uom_id)
                tare = sale_line.mercas_tare * boxes / sale_line.box_qty if sale_line.box_qty else 0.0
                rows[ml.id] = {"boxes": boxes, "net": net, "tare": tare, "gross": net + tare}
        pallets = self.sale_id.mercas_pallet_ids.filtered(
            lambda p: p.package_id and p.package_id in move_lines.result_package_id
        )
        if not any(row["boxes"] or row["tare"] for row in rows.values()) and not pallets:
            return False
        net = sum(row["net"] for row in rows.values())
        box_tare = sum(row["tare"] for row in rows.values())
        pallet_tare = sum(pallet.package_type_id.base_weight for pallet in pallets)
        gross = net + box_tare + pallet_tare
        for pallet in pallets.filtered("package_id.shipping_weight"):
            worked_out = pallet.package_type_id.base_weight + sum(
                rows[ml.id]["gross"] for ml in goods if ml.result_package_id == pallet.package_id
            )
            gross += pallet.package_id.shipping_weight - worked_out
        Template = self.env["product.template"]
        packaging = move_lines - goods if goods else self.env["stock.move.line"]
        return {
            "lines": rows,
            "packaging": packaging,
            # Grouped by box and price, for the table of the packaging
            "packaging_summary": [
                {
                    "product": product,
                    "quantity": sum(group.mapped("quantity")),
                    "uom": uom,
                    "price_unit": price_unit,
                    "amount": sum(group.mapped("sale_price_subtotal")),
                }
                for (product, uom, price_unit), group in packaging.grouped(
                    lambda ml: (ml.product_id, ml.uom_id, ml.sale_price_unit)
                ).items()
            ],
            "totals": {
                "boxes": sum(row["boxes"] for row in rows.values()),
                "pallets": len(pallets),
                "net": net,
                "box_tare": box_tare,
                "pallet_tare": pallet_tare,
                "gross": gross,
                "weighed": any(pallets.package_id.mapped("shipping_weight")),
            },
            "weight_uom": Template._get_weight_uom_name_from_ir_config_parameter(),
        }

    @staticmethod
    def _mercas_share_out(total, weights):
        """`total` whole units shared out in proportion to `weights` (largest
        remainders): they always add up to `total`."""
        weight_sum = sum(weights)
        if not total or not weight_sum:
            return [0] * len(weights)
        exact = [total * weight / weight_sum for weight in weights]
        shares = [int(value) for value in exact]
        by_remainder = sorted(range(len(weights)), key=lambda i: exact[i] - shares[i], reverse=True)
        for i in by_remainder[:total - sum(shares)]:
            shares[i] += 1
        return shares

    def _mercas_validate(self):
        """Validate the transfers of the automatic flows ("Sold & Sent",
        "Purchase & Receive", boxes) without the dialogs of the standard
        validation: immediate transfer, backorder and, with stock_sms, the
        confirmation of the SMS of the delivery.

        A dialog the flow doesn't know would leave the transfer as it was while
        the order looks done, so a transfer still not done is an error."""
        self.with_context(
            skip_immediate=True,
            skip_backorder=True,
            skip_sms=True,
        ).button_validate()
        not_done = self.filtered(lambda picking: picking.state != "done")
        if not_done:
            raise UserError(
                _("The transfer %s couldn't be validated automatically. Validate it from the transfer itself.")
                % ", ".join(not_done.mapped("name"))
            )
