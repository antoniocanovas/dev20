from odoo import _, api, fields, models


class CrmStage(models.Model):
    _inherit = 'crm.stage'

    type = fields.Selection([('comercial','Pendiente Gestión Comercial'),
                             ('taller','Pendiente Taller'),
                             ('administracion','Pendiente Gestión Administrativa'),
                             ('cliente','Pendiente del cliente'),
                             ('positiva','Gestión positiva'),
                             ('negativa', 'Gestión negativa')],
                            string="Tipo", store=True)
