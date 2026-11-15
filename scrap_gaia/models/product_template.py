from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    scrap_material_line_ids = fields.One2many(
        'product.scrap.material', 'product_tmpl_id', string="GAIA Materials", copy=True,
        help="Estimated share of its weight of each material, for the GAIA reports of the "
             "deliveries. A product made from a scrap template gets the ones of the template.")
    scrap_material_percent = fields.Float(
        "Total (%)", digits=(5, 2), compute='_compute_scrap_material_percent')

    @api.depends('scrap_material_line_ids.percent')
    def _compute_scrap_material_percent(self):
        for template in self:
            template.scrap_material_percent = sum(template.scrap_material_line_ids.mapped('percent'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('scrap_template_id'):
                template = self.browse(vals['scrap_template_id'])
                vals.update(template._scrap_gaia_values(vals))
        return super().create(vals_list)

    def write(self, vals):
        if not vals.get('scrap_template_id'):
            return super().write(vals)
        # Another template set by hand: its weight and its materials, instead of the ones there
        changed = self.filtered(lambda product: product.scrap_template_id.id != vals['scrap_template_id'])
        res = super().write(vals)
        if changed:
            template = self.browse(vals['scrap_template_id'])
            gaia_vals = template._scrap_gaia_values(vals)
            if 'scrap_material_line_ids' in gaia_vals:
                gaia_vals['scrap_material_line_ids'].insert(0, fields.Command.clear())
            if gaia_vals:
                super(ProductTemplate, changed).write(gaia_vals)
        return res

    @api.onchange('scrap_template_id')
    def _onchange_scrap_template_gaia(self):
        template = self.scrap_template_id
        if template:
            self.weight = template.weight
            self.scrap_material_line_ids = [fields.Command.clear(), *template.scrap_material_line_ids._scrap_copy_values()]

    def _scrap_gaia_values(self, vals):
        """ The weight and the GAIA materials of this scrap template, for a product made from it,
        the ones not given in `vals`. """
        self.ensure_one()
        gaia_vals = {}
        if not vals.get('weight') and self.weight:
            gaia_vals['weight'] = self.weight
        if not vals.get('scrap_material_line_ids') and self.scrap_material_line_ids:
            gaia_vals['scrap_material_line_ids'] = self.scrap_material_line_ids._scrap_copy_values()
        return gaia_vals
