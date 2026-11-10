from odoo import _, api, fields, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    lead_id = fields.Many2one('crm.lead', string="Lead", store=True)
    brand_id = fields.Many2one('fleet.vehicle.model.brand', string="Brand")
    categ_id = fields.Many2one('scrap.category', string="Category")
    product_id = fields.Many2one('product.product', string="Producto")
    product_tmpl_id = fields.Many2one('product.template', string="Producto")
    crm_stage_type = fields.Selection(related='lead_id.stage_id.type', store=True)
    datetime_deadline = fields.Datetime('Deadline time', store=True)
    partner_city = fields.Char(related='partner_id.city')
    partner_ref = fields.Char(related='partner_id.ref')

    # Petición 01/24 para poner hora en la fecha límite de las tareas:
    @api.depends('datetime_deadline')
    def get_date_deadline_from_datetime_deadline(self):
        for record in self:
            deadline = False
            if record.datetime_deadline:
                deadline = record.datetime_deadline.date()
            record['date_deadline'] = deadline


    @api.depends('crm_stage_type')
    def get_int_value_to_paint_tree_colors(self):
        for record in self:
            value = 0
            if record.crm_stage_type == 'comercial': value=1
            if record.crm_stage_type == 'taller': value=2
            if record.crm_stage_type == 'administracion': value = 3
            record['crm_stage_integer'] = value
    crm_stage_integer = fields.Integer('Code for colors', store=False, compute='get_int_value_to_paint_tree_colors')

    @api.depends('partner_id')
    def _get_partner_tags(self):
        for record in self:
            tags = []
            if (record.partner_id.parent_id.id) and (record.partner_id.parent_id.category_id.ids):
                for tag in record.partner_id.parent_id.category_id: tags.append(tag.id)
            if (record.partner_id.category_id.ids):
                for tag in record.partner_id.category_id: tags.append(tag.id)
            record['partner_tag_ids'] = [(6,0,tags)]
    partner_tag_ids = fields.Many2many('res.partner.category', compute='_get_partner_tags', store=False, string='Partner Tags')

    # Ver los anexos de la oportunidad en la tarea (previsualizar requiere módulo de pago odx_m2m_attachment_preview):
    @api.depends('lead_id')
    def _get_lead_attachments(self):
        for record in self:
            files = self.env['ir.attachment'].search([('res_model','=','crm.lead'), ('res_id','=',record.lead_id.id)])
            record['crm_file_ids'] = [(6,0,files.ids)]
    crm_file_ids = fields.Many2many('ir.attachment', string='CRM Attachments', store=  False,
                                    compute='_get_lead_attachments')

    # Abrir la tarea en una pestaña nueva del navegador desde la lista de tareas de la oportunidad:
    def action_open_in_new_tab(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/odoo/project.task/{self.id}',
            'target': 'new',
        }
