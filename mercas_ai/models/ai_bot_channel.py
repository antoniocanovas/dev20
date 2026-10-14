from odoo import fields, models


class AiBotChannel(models.Model):
    """odoo_mcp_manager ships the 'web' platform handler (_connect_web, the
    controller adapter, the views) but forgets to list it as a valid
    ai.bot.channel.platform value, so the Web Widget option never appears
    in the channel form. Add it back."""

    _inherit = 'ai.bot.channel'

    platform = fields.Selection(
        selection_add=[('web', 'Web Widget')],
        ondelete={'web': 'set default'},
    )
