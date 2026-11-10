# Copyright
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import fields, models, api
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta


import logging

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    scrap_project_id = fields.Many2one('project.project', string='SCRAP Project')
    scrap_user_id = fields.Many2one('res.users', string='SCRAP User')

