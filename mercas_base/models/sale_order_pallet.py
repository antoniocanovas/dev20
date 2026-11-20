from collections import Counter, defaultdict

from odoo import Command, _, api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    mercas_pallet_ids = fields.One2many(
        comodel_name="mercas.sale.pallet",
        inverse_name="order_id",
        string="Pallets",
        copy=False,
    )
    mercas_pallet_count = fields.Integer(
        string="Pallet Count",
        compute="_compute_mercas_pallet_count",
    )

    @api.depends("mercas_pallet_ids.line_ids")
    def _compute_mercas_pallet_count(self):
        for order in self:
            order.mercas_pallet_count = len(order.mercas_pallet_ids.filtered("line_ids"))

    # ------------------------------------------------------------------
    # Lines of the returnable pallets (envases)
    # ------------------------------------------------------------------

    def _mercas_product_lines(self):
        return super()._mercas_product_lines().filtered(lambda l: not l.mercas_pallet_box_line)

    def _mercas_reorder_box_sections(self, productos_section, envases_section):
        super()._mercas_reorder_box_sections(productos_section, envases_section)
        # The returnable pallets close the Envases section
        seq = max(self.order_line.mapped("sequence"))
        for line in self.order_line.filtered("mercas_pallet_box_line").sorted("id"):
            seq += 10
            line.sequence = seq

    def _mercas_pallet_box_counts(self):
        """{box product: pallets} of the returnable pallets that hold boxes."""
        self.ensure_one()
        return Counter(
            pallet.package_type_id.mercas_box_product_id
            for pallet in self.mercas_pallet_ids
            if pallet.line_ids and pallet.package_type_id.mercas_box_product_id
        )

    def _mercas_sync_pallet_box_lines(self):
        """One line per kind of returnable pallet, with the pallets of that kind,
        as the box lines do for the boxes. Only before the sale is confirmed:
        once delivered, the pallets given or taken back are regularized with a
        box delivery or return, like any box."""
        for order in self.filtered(lambda o: o.state in ("draft", "sent")):
            wanted = order._mercas_pallet_box_counts()
            to_unlink = self.env["sale.order.line"]
            for line in order.order_line.filtered("mercas_pallet_box_line"):
                qty = wanted.pop(line.product_id, 0)
                if not qty:
                    to_unlink |= line
                elif line.product_uom_qty != qty:
                    line.product_uom_qty = qty
            to_unlink.unlink()
            if wanted:
                sequence = max(order.order_line.mapped("sequence") or [0]) + 10
                self.env["sale.order.line"].create([
                    {
                        "order_id": order.id,
                        "product_id": product.id,
                        "product_uom_qty": qty,
                        "mercas_pallet_box_line": True,
                        "sequence": sequence + index,
                    }
                    for index, (product, qty) in enumerate(wanted.items())
                ])

    def _mercas_pallet_box_mismatch(self):
        """Returnable pallets of the sale that differ from the ones delivered:
        [(box product, on pallets, on the sale)]."""
        self.ensure_one()
        wanted = self._mercas_pallet_box_counts()
        on_sale = Counter()
        for line in self.order_line.filtered("mercas_pallet_box_line"):
            on_sale[line.product_id] += int(line.product_uom_qty)
        return [
            (product, wanted.get(product, 0), on_sale.get(product, 0))
            for product in set(wanted) | set(on_sale)
            if wanted.get(product, 0) != on_sale.get(product, 0)
        ]

    def write(self, vals):
        result = super().write(vals)
        if "mercas_pallet_ids" in vals:
            # Pallets corrected from the order: the delivery follows them
            self.filtered(lambda o: o.state not in ("draft", "sent", "cancel"))._mercas_apply_pallets()
        return result

    def action_confirm(self):
        self.filtered(lambda o: not o.mercas_is_box_delivery)._mercas_sync_pallet_box_lines()
        return super().action_confirm()

    # ------------------------------------------------------------------
    # Pallets
    # ------------------------------------------------------------------

    def _mercas_delivered_pickings(self):
        self.ensure_one()
        return self.picking_ids.filtered(
            lambda p: p.state == "done" and p.picking_type_code == "outgoing"
        )

    def _mercas_set_pallets(self, pallets):
        """Replace the pallets of the sale.

        :param list pallets: in order, [{'id': existing pallet or False,
            'package_type_id': int, 'height': float,
            'lines': [{'sale_line_id': int, 'box_qty': int}]}]
        :return: the returnable pallets that now differ from the sale, if it
            was delivered already (see `_mercas_pallet_box_mismatch`)
        """
        self.ensure_one()
        existing = self.mercas_pallet_ids
        # All the boxes are placed again: none is counted twice meanwhile
        existing.line_ids.unlink()
        kept = self.env["mercas.sale.pallet"]
        for sequence, vals in enumerate(pallets, start=1):
            pallet = existing.filtered(lambda p: p.id == vals.get("id"))
            data = {
                "sequence": sequence,
                "package_type_id": vals["package_type_id"],
                "height": vals.get("height") or 0.0,
                "line_ids": [
                    Command.create({"sale_line_id": line["sale_line_id"], "box_qty": line["box_qty"]})
                    for line in vals.get("lines") or []
                    if line.get("box_qty", 0) > 0
                ],
            }
            if pallet:
                pallet.write(data)
            else:
                pallet = pallet.create({**data, "order_id": self.id})
            kept |= pallet
        (existing - kept).unlink()

        if self.state in ("draft", "sent"):
            return []
        self._mercas_apply_pallets()
        return self._mercas_pallet_box_mismatch()

    def _mercas_apply_pallets(self, pickings=None, initial=False):
        """Put the delivered goods of each line on the packages of its pallets,
        in proportion to its boxes; the boxes on no pallet stay without package.

        Works on done move lines, which Odoo allows to change: it moves the
        quants itself. So it is the same right after the delivery and when the
        pallets are corrected later.

        :param pickings: the deliveries to change; by default, the done ones.
        :param bool initial: right after validating the delivery, so the
            changes aren't logged on it as corrections.
        """
        Package = self.env["stock.package"]
        for order in self:
            order_pickings = order._mercas_delivered_pickings()
            if pickings is not None:
                order_pickings &= pickings
            if not order_pickings:
                continue
            product_lines = order._mercas_product_lines()
            product_lines._mercas_trim_pallets()
            for pallet in order.mercas_pallet_ids.filtered("line_ids"):
                if not pallet.package_id:
                    pallet.package_id = Package.create({"package_type_id": pallet.package_type_id.id})
                elif pallet.package_id.package_type_id != pallet.package_type_id:
                    pallet.package_id.package_type_id = pallet.package_type_id
            MoveLine = self.env["stock.move.line"]
            if initial:
                MoveLine = MoveLine.with_context(mercas_skip_move_line_log=True)
            for line in product_lines:
                moves = line.move_ids.filtered(
                    lambda m: m.state == "done" and m.picking_id in order_pickings
                )
                for move in moves:
                    MoveLine._mercas_apply_pallets_to_move(line, move.with_env(MoveLine.env))

    def _mercas_net_weight(self, product, qty, uom):
        """Net weight of `qty` `uom` of `product`, in the weight unit of the
        products."""
        return product._mercas_net_weight(qty, uom)

    def action_print_mercas_packing_list(self):
        self.ensure_one()
        return self.env.ref("mercas_base.action_report_mercas_packing_list").report_action(self)

    def _mercas_packing_list(self):
        """Contents of the packing list: the pallets, as packages, with the
        boxes of each line on them, then the loose boxes, and the totals.

        The kg of a line are the delivered ones (the ordered ones before the
        delivery), shared out by boxes. The tare of the boxes is the one of
        their line (the weight of the box product when the boxes were set);
        the tare of a pallet, the weight of its type plus the boxes it holds.
        A pallet weighed (shipping weight of its package) shows that weight as
        its gross weight."""
        self.ensure_one()
        lines = self._mercas_product_lines().filtered(lambda l: l.box_qty > 0)

        def line_net(line):
            qty = line.qty_delivered or line.product_uom_qty
            return self._mercas_net_weight(line.product_id, qty, line.product_uom_id)

        def row(line, boxes):
            net = line_net(line) * boxes / line.box_qty
            tare = line.mercas_tare * boxes / line.box_qty
            lot = line.lot_id
            return {
                "line": line,
                "product": line.product_id,
                "lot": lot,
                "origin": ", ".join(
                    name for name in (lot.origin_state_id.name, lot.origin_country_id.name) if name
                ),
                "boxes": boxes,
                "box_name": line.box_product_id.name or "",
                "net": net,
                "tare": tare,
                "gross": net + tare,
            }

        on_pallets = defaultdict(int)
        pallets = []
        for pallet in self.mercas_pallet_ids.filtered("line_ids"):
            rows = [row(pl.sale_line_id, pl.box_qty) for pl in pallet.line_ids]
            for pl in pallet.line_ids:
                on_pallets[pl.sale_line_id] += pl.box_qty
            package_type = pallet.package_type_id
            net = sum(r["net"] for r in rows)
            tare = package_type.base_weight + sum(r["tare"] for r in rows)
            weighed = pallet.package_id.shipping_weight
            pallets.append({
                "pallet": pallet,
                "name": pallet.package_id.name or pallet.name,
                "type": package_type,
                "rows": rows,
                "boxes": sum(r["boxes"] for r in rows),
                "net": net,
                "tare": tare,
                "gross": weighed or net + tare,
                "weighed": bool(weighed),
                "dimensions": self._mercas_pallet_dimensions(pallet),
                "volume": self._mercas_pallet_volume(pallet),
            })
        loose = [
            row(line, line.box_qty - on_pallets[line])
            for line in lines
            if line.box_qty > on_pallets[line]
        ]
        loose_boxes = sum(r["boxes"] for r in loose)
        totals = {
            "pallets": len(pallets),
            "boxes": sum(p["boxes"] for p in pallets) + loose_boxes,
            "packages": len(pallets) + loose_boxes,
            "net": sum(p["net"] for p in pallets) + sum(r["net"] for r in loose),
            "tare": sum(p["tare"] for p in pallets) + sum(r["tare"] for r in loose),
            "gross": sum(p["gross"] for p in pallets) + sum(r["gross"] for r in loose),
            "volume": sum(p["volume"] for p in pallets),
            "has_volume": any(p["volume"] for p in pallets),
        }
        Template = self.env["product.template"]
        return {
            "order": self,
            "pickings": self._mercas_delivered_pickings(),
            "pallets": pallets,
            "loose": loose,
            "loose_boxes": loose_boxes,
            "totals": totals,
            "returnable": self._mercas_pallet_box_counts(),
            "weight_uom": Template._get_weight_uom_name_from_ir_config_parameter(),
            "length_uom": Template._get_length_uom_name_from_ir_config_parameter(),
        }

    def _mercas_pallet_height(self, pallet):
        return pallet.height or pallet.package_type_id.height

    def _mercas_pallet_dimensions(self, pallet):
        package_type = pallet.package_type_id
        sizes = (package_type.packaging_length, package_type.width, self._mercas_pallet_height(pallet))
        return sizes if all(sizes) else False

    def _mercas_pallet_volume(self, pallet):
        """Volume of the pallet in m³; 0 without its three sizes."""
        sizes = self._mercas_pallet_dimensions(pallet)
        if not sizes:
            return 0.0
        length_uom = self.env["product.template"]._get_length_uom_id_from_ir_config_parameter()
        meter = self.env.ref("uom.product_uom_meter")
        if not length_uom._has_common_reference(meter):
            return 0.0
        volume = 1.0
        for size in sizes:
            volume *= length_uom._compute_quantity(size, meter, round=False)
        return volume
