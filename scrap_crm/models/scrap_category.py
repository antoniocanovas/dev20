from odoo import _, api, fields, models

import logging
_logger = logging.getLogger(__name__)


class ScrapCategory(models.Model):
    _name = 'scrap.category'
    _description = 'SCRAP Category'

    name = fields.Char('Category')
    active = fields.Boolean('Active', default=True)