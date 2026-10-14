from odoo import api, fields, models

from ..prompts import BASE_BUSINESS_INSTRUCTIONS

_CUSTOM_INSTRUCTIONS_PARAM = 'mercas_ai.custom_instructions'


class ResConfigSettings(models.TransientModel):
    """Two-tier prompt configuration for 'AI Chat':

    - mercas_ai_base_instructions: fixed business glossary owned by the
      module (readonly in the UI, sourced from prompts.py) -- not meant to be
      edited from Settings, only shown for transparency.
    - mercas_ai_custom_instructions: free text an admin can edit to tune
      behaviour without touching code, stored as an ir.config_parameter.

    Text fields cannot use the config_parameter="..." shortcut (res.config
    only supports it for boolean/integer/float/char/selection/many2one/
    datetime), so the custom instructions are read/written by hand below.
    """

    _inherit = 'res.config.settings'

    mercas_ai_base_instructions = fields.Text(
        string='General Instructions (fixed)',
        default=BASE_BUSINESS_INSTRUCTIONS,
        readonly=True,
    )
    mercas_ai_custom_instructions = fields.Text(string='Custom Instructions')

    @api.model
    def get_values(self):
        res = super().get_values()
        res['mercas_ai_custom_instructions'] = self.env['ir.config_parameter'].sudo().get_str(
            _CUSTOM_INSTRUCTIONS_PARAM, ''
        )
        return res

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_str(
            _CUSTOM_INSTRUCTIONS_PARAM, self.mercas_ai_custom_instructions or ''
        )
