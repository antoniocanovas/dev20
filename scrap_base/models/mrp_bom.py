from odoo import api, fields, models

# Margin of the sum of the cost shares of a bill of materials, around 100%
COST_SHARE_MARGIN = 0.01


class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    scrap_cost_ok = fields.Boolean(
        compute='_compute_scrap_cost_ok',
        help="A bill of materials to dismantle (of a scrap template, a vehicle or a subproduct): "
             "its lines share the cost of the product.")
    scrap_cost_share_total = fields.Float(
        "Total Cost Share (%)", compute='_compute_scrap_cost_share_total',
        help="The cost shares of the lines still to dismantle, of the parts dismantled and of "
             "the ones lost: 100% to dismantle it.")
    scrap_cost_share_valid = fields.Boolean(compute='_compute_scrap_cost_share_total')

    @api.depends('product_tmpl_id.is_template', 'product_tmpl_id.scrap_unbuild_type')
    def _compute_scrap_cost_ok(self):
        for bom in self:
            bom.scrap_cost_ok = bool(bom.product_tmpl_id.is_template or bom.product_tmpl_id.scrap_unbuild_type)

    @api.depends('bom_line_ids.scrap_cost_share', 'bom_line_ids.scrap_added')
    def _compute_scrap_cost_share_total(self):
        marked = self.env['scrap.dismantle.line'].sudo().search([
            ('bom_line_id', 'in', self.bom_line_ids.ids), ('stage', '=', 'dismantling')])
        for bom in self:
            lines = bom.bom_line_ids.filtered(lambda line: not line.scrap_added)
            parts = marked.filtered(lambda part: part.bom_line_id in lines)
            # The share of a part discarded or missing is in the lines it went to, or lost
            dismantled = parts.filtered(lambda part: part.result == 'dismantled')
            bom.scrap_cost_share_total = (sum(lines.mapped('scrap_cost_share'))
                                          + sum(dismantled.mapped('cost_share')) + sum(parts.mapped('cost_lost')))
            bom.scrap_cost_share_valid = abs(bom.scrap_cost_share_total - 100) <= COST_SHARE_MARGIN
