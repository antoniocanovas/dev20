from collections import defaultdict

from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # Computed again when its products or their quantities change, not on validating it nor
    # when the products change: what is written by hand is kept
    scrap_material_line_ids = fields.One2many(
        'stock.picking.scrap.material', 'picking_id', string="GAIA Materials",
        compute='_compute_scrap_material_line_ids', store=True, readonly=False, copy=False,
        help="Weight of each material of the products delivered, for GAIA: from their weight and "
             "their percentages of each material. It can be changed by hand.")
    scrap_weight_uom_name = fields.Char(compute='_compute_scrap_weight_uom_name')
    scrap_gaia_warning = fields.Text("GAIA Warnings", compute='_compute_scrap_gaia_warning')

    def _compute_scrap_weight_uom_name(self):
        self.scrap_weight_uom_name = self.env['product.template']._get_weight_uom_name_from_ir_config_parameter()

    def _scrap_gaia_moves(self):
        """ The moves of the products of the vehicle recycling, the ones with a scrap type: not
        the ones only bought and sold, as a new can of oil. """
        return self.move_ids.filtered(lambda move: move.state != 'cancel' and move.product_id.scrap_unbuild_type)

    def _scrap_gaia_weights(self):
        """ {material: weight} of its products: their weight, by the quantity to deliver, by
        their percentage of each material. """
        self.ensure_one()
        weights = defaultdict(float)
        for move in self._scrap_gaia_moves():
            product = move.product_id
            quantity = move.uom_id._compute_quantity(move.product_uom_qty, product.uom_id)
            for line in product.scrap_material_line_ids:
                weights[line.scrap_material_id] += product.weight * quantity * line.percent / 100
        return weights

    @api.depends('picking_type_code', 'move_ids.product_id', 'move_ids.product_uom_qty', 'move_ids.uom_id')
    def _compute_scrap_material_line_ids(self):
        for picking in self:
            if picking.picking_type_code != 'outgoing':
                # Only the deliveries are computed; the rest keep what is written by hand
                picking.scrap_material_line_ids = picking.scrap_material_line_ids
                continue
            weights = picking._scrap_gaia_weights()
            picking.scrap_material_line_ids = [fields.Command.clear(), *(
                fields.Command.create({'scrap_material_id': material.id, 'weight': weight})
                for material, weight in sorted(weights.items(), key=lambda item: (item[0].sequence, item[0].id))
            )]

    @api.depends('picking_type_code', 'move_ids.product_id', 'move_ids.state')
    def _compute_scrap_gaia_warning(self):
        for picking in self:
            notes = []
            if picking.picking_type_code == 'outgoing':
                products = picking._scrap_gaia_moves().product_id.filtered('is_storable')
                for product in products:
                    if product.weight <= 0:
                        notes.append(self.env._("- %s: without weight.", product.display_name))
                    if not product.scrap_material_line_ids:
                        notes.append(self.env._("- %s: without GAIA materials.", product.display_name))
            picking.scrap_gaia_warning = "\n".join(notes) or False

    def action_scrap_compute_gaia(self):
        """ Computed again from the products, as they are now: what was written by hand is lost. """
        self.filtered(lambda picking: picking.picking_type_code == 'outgoing')._compute_scrap_material_line_ids()
        return True
