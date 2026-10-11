from odoo import Command, fields, models


class MrpUnbuild(models.Model):
    _inherit = 'mrp.unbuild'

    cutting_session_id = fields.Many2one(
        'meat.cutting.session', 'Cutting Session', readonly=True, copy=False, index='btree_not_null')

    def _action_unbuild_cutting(self, lot_by_product):
        """ Unbuild driven by the weighed cuts of a cutting session instead of
        the BoM ratios: the produced quantities are the real weights of the
        produced products (frozen ones for the cuts to freeze), put in the
        given lots ({product: stock.lot}). """
        self.ensure_one()
        self._check_company()
        session = self.cutting_session_id
        Move = self.env['stock.move']
        production_location = self.product_id.with_company(self.company_id).property_stock_production

        consume_move = Move.create({
            'date': self.create_date,
            'product_id': self.product_id.id,
            'product_uom_qty': self.product_qty,
            'uom_id': self.uom_id.id,
            'procure_method': 'make_to_stock',
            'location_id': self.location_id.id,
            'location_dest_id': production_location.id,
            'warehouse_id': self.location_id.warehouse_id.id,
            'unbuild_id': self.id,
            'company_id': self.company_id.id,
        })
        produce_vals = []
        lines_by_produce = session.line_ids.grouped(lambda l: (l.output_product_id, l.bom_line_id))
        for (product, bom_line), lines in lines_by_produce.items():
            prod_location = product.with_company(self.company_id).property_stock_production
            produce_vals.append({
                'date': self.create_date,
                'bom_line_id': bom_line.id,
                'product_id': product.id,
                'product_uom_qty': sum(lines.mapped('weight')),
                'uom_id': product.uom_id.id,
                'procure_method': 'make_to_stock',
                'location_id': prod_location.id,
                'location_dest_id': self.location_dest_id.id,
                'warehouse_id': self.location_dest_id.warehouse_id.id,
                'unbuild_id': self.id,
                'company_id': self.company_id.id,
            })
        produce_moves = Move.create(produce_vals)

        moves = consume_move | produce_moves
        moves._action_confirm()
        moves.move_line_ids.unlink()
        move_line_vals = [{
            'move_id': consume_move.id,
            'product_id': consume_move.product_id.id,
            'uom_id': consume_move.uom_id.id,
            'quantity': consume_move.product_uom_qty,
            'lot_id': session.lot_id.id,
            'package_id': session.package_id.id,
            'location_id': consume_move.location_id.id,
            'location_dest_id': consume_move.location_dest_id.id,
        }]
        for move, lines in zip(produce_moves, lines_by_produce.values()):
            # Each weighed piece goes in its package, the rest of the cut in bulk
            pieces = lines.filtered('package_id')
            quantities = [(piece.weight, piece.package_id) for piece in pieces]
            if lines - pieces:
                quantities.append((sum((lines - pieces).mapped('weight')), self.env['stock.package']))
            move_line_vals += [{
                'move_id': move.id,
                'product_id': move.product_id.id,
                'uom_id': move.uom_id.id,
                'quantity': quantity,
                'lot_id': lot_by_product.get(move.product_id, self.env['stock.lot']).id,
                'result_package_id': package.id,
                'location_id': move.location_id.id,
                'location_dest_id': move.location_dest_id.id,
            } for quantity, package in quantities]
        self.env['stock.move.line'].create(move_line_vals)
        moves.picked = True
        consume_move._action_done()
        produce_moves._action_done()
        consume_move.move_line_ids.produce_line_ids = [Command.set(produce_moves.move_line_ids.ids)]
        self.state = 'done'
