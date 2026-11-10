from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _prepare_move_line_vals(self, quantity=None, reserved_quant=None):
        """ The receipt of a vehicle comes with its license plate as serial number. """
        vals = super()._prepare_move_line_vals(quantity=quantity, reserved_quant=reserved_quant)
        plate = self.product_id.scrap_lot_name or self.purchase_line_id.scrap_lot_name
        if (plate and self.has_tracking and self.picking_code == 'incoming'
                and not vals.get('lot_id') and not vals.get('lot_name')):
            vals['lot_name'] = plate
        return vals

    def _action_done(self, cancel_backorder=False):
        moves = super()._action_done(cancel_backorder=cancel_backorder)
        moves._set_scrap_vehicle_refs()
        moves._set_scrap_discharge_date()
        return moves

    def _set_scrap_discharge_date(self):
        """ A vehicle to dismantle is discharged when it is received: its legal deadlines count
        from then. A subproduct bought (as an engine), when it is received, without deadlines:
        it can be dismantled then. A date already set is kept. """
        for move in self.filtered(lambda move: (
            move.state == 'done'
            and move.picking_code == 'incoming'
            and (move.product_id.scrap_unbuild_type == 'main'
                 or (move.product_id.scrap_unbuild_type == 'subproduct' and move.product_id.scrap_template_id))
            and not move.product_id.discharge_date
        )):
            move.product_id.product_tmpl_id.sudo().discharge_date = fields.Date.context_today(move, move.date)

    def _set_scrap_vehicle_refs(self):
        """ Give its internal reference to each vehicle received: the next one of the sequence of
        its kind of entry (the scrap type of its purchase), set in the company. A vehicle is a
        scrap template, or a copy of one, tracked by serial number. Its serial number, and its
        product when it has no internal reference, keep it once given. """
        receipts = self.filtered(lambda move: (
            move.state == 'done'
            and move.picking_code == 'incoming'
            and move.purchase_line_id.order_id.unbuild_type
            and (move.product_id.is_template or move.product_id.scrap_template_id)
            and move.has_tracking == 'serial'
        ))
        for move in receipts:
            sequence = move.company_id._get_scrap_sequence(move.purchase_line_id.order_id.unbuild_type)
            if not sequence:
                continue
            for lot in move.move_line_ids.lot_id.filtered(lambda lot: not lot.ref).sorted('id'):
                # The sequence is used, not configured, by the warehouse users
                lot.ref = sequence.sudo().next_by_id()
            product = move.product_id
            if product.scrap_template_id and not product.default_code and move.move_line_ids.lot_id.ref:
                product.sudo().default_code = move.move_line_ids.lot_id[:1].ref
