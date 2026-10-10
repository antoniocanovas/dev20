from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    cutting_session_ids = fields.One2many('meat.cutting.session', 'picking_id', 'Cutting Sessions')
    cutting_session_count = fields.Integer(compute='_compute_cutting_session_count')

    def _compute_cutting_session_count(self):
        counts = dict(self.env['meat.cutting.session']._read_group(
            [('picking_id', 'in', self.ids)], ['picking_id'], ['__count']))
        for picking in self:
            picking.cutting_session_count = counts.get(picking, 0)

    def action_open_cutting_screen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'meat_cutting_screen',
            'name': self.env._("Cutting"),
            'context': {'meat_cutting_picking_id': self.id},
        }

    def action_register_carcasses(self):
        """ Receive the carcasses one by one, with their crotal and real weight. """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Register Carcasses"),
            'res_model': 'meat.carcass.register',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_picking_id': self.id,
                'default_partner_id': self.partner_id.commercial_partner_id.id,
            },
        }

    def action_view_cutting_sessions(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('meat_cutting.meat_cutting_session_action')
        action['domain'] = [('picking_id', '=', self.id)]
        action['context'] = {'default_picking_id': self.id}
        return action

    def _get_meat_boxes(self):
        """ Boxes of the transfer: the outermost packages its products are put
        in, but the pieces that were not boxed. """
        boxes = self.env['stock.package']
        for package in self.move_line_ids.result_package_id:
            boxes |= package._get_meat_box()
        return boxes.filtered(lambda box: not box.meat_piece).sorted('name')

    def _pre_action_done_hook(self):
        self._adjust_meat_piece_demand()
        return super()._pre_action_done_hook()

    def _adjust_meat_piece_demand(self):
        """ Whole pieces ordered by number (in a packaging unit) are complete
        once that number of pieces is picked, whatever their real weight: the
        demand becomes the picked weight, so that no backorder is proposed for
        the weight difference with the estimate. If nothing is picked, the
        reserved pieces are, as on validation. """
        for picking in self:
            nothing_picked = not any(picking.move_ids.mapped('picked'))
            for move in picking.move_ids:
                if (
                    move.state in ('done', 'cancel') or not (move.picked or nothing_picked)
                    or not move._is_meat_piece_move()
                    or move.uom_id.compare(move.quantity, move.product_uom_qty) >= 0
                ):
                    continue
                if move._get_meat_piece_count() >= move._get_meat_pieces_ordered():
                    move.product_uom_qty = move.quantity
