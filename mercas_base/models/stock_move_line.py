from odoo import api, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _log_message(self, record, move, template, vals):
        # The pallets placed right after a delivery aren't a correction of it
        if self.env.context.get("mercas_skip_move_line_log"):
            return
        return super()._log_message(record, move, template, vals)

    @api.model
    def _mercas_pallet_buckets(self, sale_line, total, uom):
        """[[package, qty]] the `total` of the line goes to: its pallets in
        proportion to their boxes, then its loose boxes (no package). The
        rounding left goes to the last one."""
        pallet_lines = sale_line.mercas_pallet_line_ids.filtered(
            lambda pl: pl.pallet_id.package_id
        ).sorted(lambda pl: (pl.pallet_id.sequence, pl.pallet_id.id, pl.id))
        boxes = sale_line.box_qty
        buckets = []
        for pallet_line in pallet_lines:
            buckets.append([pallet_line.pallet_id.package_id, uom.round(total * pallet_line.box_qty / boxes)])
        rest = uom.round(total - sum(qty for _package, qty in buckets))
        on_pallets = sum(pallet_lines.mapped("box_qty"))
        if buckets and on_pallets >= boxes:
            buckets[-1][1] = uom.round(buckets[-1][1] + rest)
        elif uom.compare(rest, 0) > 0:
            buckets.append([self.env["stock.package"], rest])
        # One bucket per package
        merged = {}
        for package, qty in buckets:
            merged[package] = merged.get(package, 0.0) + qty
        return [[package, qty] for package, qty in merged.items() if uom.compare(qty, 0) > 0]

    @api.model
    def _mercas_apply_pallets_to_move(self, sale_line, move):
        """Share out the done move lines of `move` between the packages of the
        pallets of `sale_line`: each line keeps its lot and locations, and is
        split when part of it goes to another pallet."""
        uom = move.product_id.uom_id
        move_lines = move.move_line_ids.sorted("id")
        total = sum(move_lines.mapped("quantity_product_uom"))
        if uom.compare(total, 0) <= 0:
            return
        buckets = self._mercas_pallet_buckets(sale_line, total, uom) if sale_line.box_qty else []
        if not buckets:
            buckets = [[self.env["stock.package"], total]]

        current = {}
        for ml in move_lines:
            if uom.compare(ml.quantity_product_uom, 0) > 0:
                current[ml.result_package_id] = current.get(ml.result_package_id, 0.0) + ml.quantity_product_uom
        if set(current) == {package for package, _qty in buckets} and all(
            uom.compare(current[package], qty) == 0 for package, qty in buckets
        ):
            return

        # Lines that only differ by their package are filled again together
        groups = move_lines.grouped(
            lambda ml: (ml.lot_id, ml.package_id, ml.location_id, ml.location_dest_id, ml.owner_id)
        )
        index = 0
        writes = []
        creates = []
        for group in groups.values():
            group_qty = sum(group.mapped("quantity_product_uom"))
            pieces = {}
            while uom.compare(group_qty, 0) > 0:
                package, available = buckets[index]
                last = index == len(buckets) - 1
                take = group_qty if last else min(group_qty, available)
                if uom.compare(take, 0) > 0:
                    pieces[package] = pieces.get(package, 0.0) + take
                group_qty = uom.round(group_qty - take)
                buckets[index][1] = uom.round(available - take)
                if not last and uom.compare(buckets[index][1], 0) <= 0:
                    index += 1
            pieces = list(pieces.items())
            for position, ml in enumerate(group):
                package, qty = pieces[position] if position < len(pieces) else (self.env["stock.package"], 0.0)
                writes.append((ml, package, qty))
            creates += [(group[0], package, qty) for package, qty in pieces[len(group):]]

        # Less first and then more, so the stock left never goes negative
        writes.sort(key=lambda w: w[2] - w[0].quantity_product_uom)
        for ml, package, qty in writes:
            ml_qty = uom._compute_quantity(qty, ml.uom_id)
            vals = {}
            if ml.uom_id.compare(ml.quantity, ml_qty) != 0:
                vals["quantity"] = ml_qty
            if ml.result_package_id != package:
                vals["result_package_id"] = package.id
            if vals:
                ml.write(vals)
        for template, package, qty in creates:
            template.copy({
                "quantity": uom._compute_quantity(qty, template.uom_id),
                "result_package_id": package.id,
            })
