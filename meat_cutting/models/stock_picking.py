from odoo import api, fields, models
from odoo.exceptions import UserError


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

    # ------------------------------------------------------------------
    # Packing screen: put the pieces of a delivery in boxes
    # ------------------------------------------------------------------

    @api.model
    def get_meat_packing_pickings(self):
        """ Deliveries to pack: with reserved products, not done yet. """
        pickings = self.search([
            ('picking_type_code', '=', 'outgoing'),
            ('state', 'in', ('confirmed', 'waiting', 'assigned')),
            ('company_id', '=', self.env.company.id),
        ], order='scheduled_date, id')
        result = []
        for picking in pickings:
            move_lines = picking._get_meat_packing_move_lines()
            if not move_lines:
                continue
            result.append({
                'id': picking.id,
                'name': picking.name,
                'partner_name': picking.partner_id.display_name or '',
                'origin': picking.origin or '',
                'scheduled_date': fields.Datetime.to_string(picking.scheduled_date),
                'line_count': len(move_lines),
                'packed_count': len(move_lines.filtered(lambda ml: ml._get_meat_packing_box())),
            })
        return result

    def get_meat_packing_data(self):
        self.ensure_one()
        move_lines = self._get_meat_packing_move_lines()
        boxes = self.env['stock.package']
        lines = []
        for move_line in move_lines:
            box = move_line._get_meat_packing_box()
            boxes |= box
            package = move_line.package_id or move_line.result_package_id.filtered('meat_piece')
            lines.append({
                'id': move_line.id,
                'product_id': move_line.product_id.id,
                'product_name': move_line.product_id.display_name,
                'lot_name': move_line.lot_id.name or '',
                'package_name': package.name or '',
                'presentation': package.meat_presentation_id.name or '',
                'expiration_date': fields.Datetime.to_string(move_line.lot_id.expiration_date) or '',
                'quantity': move_line.quantity,
                'uom_name': move_line.uom_id.name,
                'box_id': box.id,
                'box_name': box.name or '',
            })
        return {
            'id': self.id,
            'name': self.name,
            'state': self.state,
            'partner_name': self.partner_id.display_name or '',
            'origin': self.origin or '',
            'moves': [{
                'id': move.id,
                'product_name': move.product_id.display_name,
                'demand': move.product_uom_qty,
                'quantity': move.quantity,
                'uom_name': move.uom_id.name,
                'pieces_ordered': move._get_meat_pieces_ordered() if move._is_meat_piece_move() else 0,
                'pieces': move._get_meat_piece_count() if move._is_meat_piece_move() else 0,
                'packaging_name': move.packaging_uom_id.name if move._is_meat_piece_move() else '',
                'presentation': move._get_meat_ordered_presentation(),
            } for move in self.move_ids.filtered(lambda m: m.state not in ('done', 'cancel'))],
            'lines': lines,
            'boxes': [{
                'id': box.id,
                'name': box.name,
                'count': len([line for line in lines if line['box_id'] == box.id]),
                'weight': sum(line['quantity'] for line in lines if line['box_id'] == box.id),
            } for box in boxes.sorted('name')],
        }

    def action_meat_new_box(self):
        """ New empty box, named with a SSCC when a package type has a GS1
        company prefix. Returns its id and name. """
        self.ensure_one()
        package_type = self.env['stock.package.type'].search([
            ('meat_sscc_prefix', '!=', False),
            ('company_id', 'in', [self.company_id.id, False]),
        ], limit=1)
        box = self.env['stock.package'].create({'package_type_id': package_type.id})
        return {'id': box.id, 'name': box.name}

    def action_meat_toggle_box(self, move_line_id, box_id):
        """ Put the line (its piece) in the box, or take it out if it is in. """
        self.ensure_one()
        move_line = self._get_meat_packing_move_lines().filtered(lambda ml: ml.id == move_line_id)
        if not move_line:
            raise UserError(self.env._("This line is not in %s anymore.", self.name))
        box = self.env['stock.package'].browse(box_id).exists()
        if move_line._get_meat_packing_box() and (not box or move_line._get_meat_packing_box() == box):
            move_line._meat_unbox()
        else:
            if not box:
                raise UserError(self.env._("Open a box first."))
            move_line._meat_box(box)
        return True

    def action_meat_scan_package(self, barcode, box_id):
        """ Put the scanned package in the box. A package that is not reserved
        in the delivery replaces a piece of the same product still unpacked. """
        self.ensure_one()
        box = self.env['stock.package'].browse(box_id).exists()
        if not box:
            raise UserError(self.env._("Open a box first."))
        package = self.env['stock.package'].search([('name', '=', barcode)], limit=1)
        if not package:
            raise UserError(self.env._("No package %s.", barcode))
        move_lines = self._get_meat_packing_move_lines()
        move_line = move_lines.filtered(lambda ml: package in (ml.package_id | ml.result_package_id))[:1]
        if not move_line:
            move_line = self._meat_replace_package(package)
        move_line._meat_box(box)
        return True

    def _meat_replace_package(self, package):
        """ Reserve the package instead of an unpacked piece of its product. """
        quants = package.quant_ids.filtered(lambda q: q.location_id.usage == 'internal')
        product = quants.product_id
        move = self.move_ids.filtered(lambda m: m.product_id == product and m.state not in ('done', 'cancel'))[:1]
        if len(product) != 1 or not move:
            raise UserError(self.env._("Package %(package)s has no product of %(picking)s.",
                                       package=package.name, picking=self.name))
        if product.uom_id.compare(sum(quants.mapped('reserved_quantity')), 0) > 0:
            raise UserError(self.env._("Package %s is reserved for another transfer.", package.name))
        unpacked = move.move_line_ids.filtered(lambda ml: not ml._get_meat_packing_box())
        replaced = unpacked.filtered('package_id')[:1] or unpacked[:1]
        if not replaced and move._is_meat_piece_move() and \
                move._get_meat_piece_count() >= move._get_meat_pieces_ordered():
            raise UserError(self.env._("All the pieces of %s ordered are already packed.", product.display_name))
        replaced.unlink()
        quant = quants[:1]
        return self.env['stock.move.line'].create({
            'move_id': move.id,
            'picking_id': self.id,
            'product_id': product.id,
            'uom_id': product.uom_id.id,
            'quantity': sum(quants.mapped('quantity')),
            'lot_id': quant.lot_id.id,
            'package_id': package.id,
            'result_package_id': package.id,
            'location_id': quant.location_id.id,
            'location_dest_id': move.location_dest_id.id,
        })

    def _get_meat_packing_move_lines(self):
        return self.move_line_ids.filtered(
            lambda ml: ml.state not in ('done', 'cancel') and ml.uom_id.compare(ml.quantity, 0) > 0)
