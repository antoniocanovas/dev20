from odoo import _, api, fields, models


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    brand_id = fields.Many2one(
        'fleet.vehicle.model.brand', string="Brand",
        help="Brand (manufacturer) of the vehicle the customer asks parts for, as the vehicles and "
             "their parts: the ones available are found by it.")
    scrap_template_id = fields.Many2one(
        'product.template', string="Scrap Template", domain=[('is_template', '=', True)],
        help="Scrap template of what the customer asks for, as a vehicle or a used engine.")
    scrap_available_count = fields.Integer(
        "Available Parts", compute='_compute_scrap_available_count',
        help="Vehicles and parts of the brand in stock.")
    task_ids = fields.One2many('project.task', 'lead_id', store=True)
    scrap_project_id = fields.Many2one('project.project', store=False, related='company_id.scrap_project_id')
    scrap_user_id = fields.Many2one('res.users', store=False, related='company_id.scrap_user_id')
    market_value    = fields.Monetary('Market value', currency_field='company_currency')
    quotation_value = fields.Monetary('Quotation', currency_field='company_currency')
    description_tech = fields.Text('Technical notes', store=True)
    stage_type = fields.Selection(string='Type', store=True, related='stage_id.type')
    price_note = fields.Char('Prices notes', store=True, copy=False)


    partner_tag_ids = fields.Many2many(comodel_name='res.partner.category',
                                       relation='crm_partner_tag_rel',
                                       column1 = 'lead_id',
                                       column2 = 'partner_categ_ids',
                                       related = 'partner_id.category_id',
                                       readonly=False, store=True, string='Partner Tags')

    parent_tag_ids = fields.Many2many(comodel_name='res.partner.category',
                                       relation='crm_parent_tag_rel',
                                       column1 = 'lead_id',
                                       column2 = 'partner_categ_ids',
                                       related = 'partner_id.parent_id.category_id',
                                       readonly=False, store=True, string='Parent Tags')


    def _get_scrap_available_domain(self):
        self.ensure_one()
        return [('scrap_vehicle_brand_id', '=', self.brand_id.id), ('is_template', '=', False),
                ('qty_available', '>', 0)]

    @api.depends('brand_id')
    def _compute_scrap_available_count(self):
        Template = self.env['product.template']
        for lead in self:
            lead.scrap_available_count = (
                Template.search_count(lead._get_scrap_available_domain()) if lead.brand_id else 0)

    def action_scrap_available_parts(self):
        """ The touch screen of what is available for the opportunity: the products in stock,
        of its brand by default, and the ones in stock with its scrap template still to
        dismantle (assembled). """
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'scrap_crm.available',
            'name': self.env._("Available: %s", self.display_name),
            'params': {'lead_id': self.id},
        }

    @api.depends('partner_id.ref','partner_id.parent_id','partner_id.parent_id.ref')
    def _get_partner_ref(self):
        for record in self:
            ref = ""
            if (record.partner_id.parent_id.id) and (record.partner_id.parent_id.ref):
                ref = record.partner_id.parent_id.ref
            else:
                ref = record.partner_id.ref
            record['partner_ref'] = ref
    partner_ref = fields.Char('Ref', compute='_get_partner_ref', store=True)

    @api.depends('partner_ref', 'name')
    def _compute_display_name(self):
        for lead in self:
            name = lead.name
            if lead.partner_ref: name = lead.partner_ref + " " + name
            lead.display_name = name
