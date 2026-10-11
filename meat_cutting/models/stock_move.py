from odoo import models
from odoo.tools import float_round


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def _get_meat_packing_box(self):
        """ Box the line is packed in on the packing screen, if any. """
        self.ensure_one()
        package = self.result_package_id
        if not package:
            return package
        box = package._get_meat_box()
        # A piece, or a package moved whole, is not a box by itself
        if box.meat_piece or box == self.package_id:
            return self.env['stock.package']
        return box

    def _is_meat_whole_package(self):
        """ The line takes all its package: the package itself is moved. """
        self.ensure_one()
        if not self.package_id:
            return False
        content = sum(self.package_id.quant_ids.filtered(lambda q: q.product_id == self.product_id).mapped('quantity'))
        return self.product_id.uom_id.compare(self.quantity_product_uom, content) >= 0 \
            and self.package_id.quant_ids.product_id == self.product_id

    def _meat_box(self, box):
        """ A whole piece goes in the box in its package, anything else
        directly in the box. """
        for move_line in self:
            if move_line._is_meat_whole_package():
                move_line.result_package_id = move_line.package_id
                if move_line.package_id != box:
                    move_line.package_id.package_dest_id = box
            else:
                move_line.result_package_id = box
            move_line.picked = True

    def _meat_unbox(self):
        for move_line in self:
            box = move_line._get_meat_packing_box()
            if move_line.result_package_id == box:
                move_line.result_package_id = move_line.package_id if move_line._is_meat_whole_package() else False
            else:
                move_line.result_package_id.package_dest_id = False
            move_line.picked = False


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _is_meat_piece_move(self):
        """ Whole pieces ordered by number (in a packaging unit), not by weight. """
        self.ensure_one()
        return bool(
            self.product_id.meat_piece and self.packaging_uom_id
            and self.packaging_uom_id != self.product_id.uom_id
        )

    def _get_meat_pieces_ordered(self):
        self.ensure_one()
        return float_round(self.packaging_uom_qty, precision_digits=0, rounding_method='UP')

    def _get_meat_piece_count(self, move_lines=None):
        """ Each piece is a package, a piece out of a package is one more. """
        self.ensure_one()
        if move_lines is None:
            move_lines = self.move_line_ids
        move_lines = move_lines.filtered(lambda ml: ml.product_id.uom_id.compare(ml.quantity, 0) > 0)
        return len(move_lines.package_id) + len(move_lines.filtered(lambda ml: not ml.package_id))

    def _get_meat_ordered_presentation(self):
        """ Presentation the customer ordered, shown when packing. """
        self.ensure_one()
        return ''

    def _has_meat_pieces_reserved(self):
        self.ensure_one()
        return self._is_meat_piece_move() and self._get_meat_piece_count() >= self._get_meat_pieces_ordered()

    def _update_reserved_quantity_vals(self, need, location_id, lot_id=None, package_id=None, owner_id=None, strict=True):
        """ Whole pieces ordered by number are reserved whole: a free package per
        piece, whatever its weight, instead of the estimated weight split
        across packages. Stock out of packages is then reserved by weight. """
        self.ensure_one()
        if strict or package_id or not self._is_meat_piece_move() or self.product_id.uom_id.compare(need, 0) <= 0:
            return super()._update_reserved_quantity_vals(need, location_id, lot_id, package_id, owner_id, strict)
        uom = self.product_id.uom_id
        missing_pieces = self._get_meat_pieces_ordered() - self._get_meat_piece_count()
        quants = self.env['stock.quant'].sudo()._gather(
            self.product_id, location_id, lot_id=lot_id, owner_id=owner_id, strict=False)
        quants = quants.filtered(lambda q: uom.compare(q.quantity, 0) > 0)
        move_line_vals, taken_quantity = [], 0
        for package in quants.package_id:
            if missing_pieces <= 0:
                break
            package_quants = quants.filtered(lambda q: q.package_id == package)
            if uom.compare(sum(package_quants.mapped('reserved_quantity')), 0) > 0:
                continue  # Part of the piece is taken by another transfer
            for quant in package_quants:
                vals, taken = super()._update_reserved_quantity_vals(
                    quant.quantity, quant.location_id, quant.lot_id, package, quant.owner_id, strict=True)
                move_line_vals += vals
                taken_quantity += taken
            missing_pieces -= 1
        # Stock out of packages, by weight
        for quant in quants.filtered(lambda q: not q.package_id):
            remaining = need - taken_quantity
            if missing_pieces <= 0 or uom.compare(remaining, 0) <= 0:
                break
            available = quant.quantity - quant.reserved_quantity
            if uom.compare(available, 0) <= 0:
                continue
            vals, taken = super()._update_reserved_quantity_vals(
                min(available, remaining), quant.location_id, quant.lot_id, quant.package_id, quant.owner_id,
                strict=True)
            move_line_vals += vals
            taken_quantity += taken
        return move_line_vals, taken_quantity

    def _action_assign(self, force_qty=False):
        res = super()._action_assign(force_qty=force_qty)
        # Ready once the pieces are reserved, whatever their weight
        self.filtered(
            lambda m: m.state == 'partially_available' and m._has_meat_pieces_reserved()
        ).write({'state': 'assigned'})
        return res

    def _recompute_state(self):
        res = super()._recompute_state()
        if not self.env.context.get('preserve_state'):
            self.filtered(
                lambda m: m.state == 'partially_available' and m._has_meat_pieces_reserved()
            ).write({'state': 'assigned'})
        return res
