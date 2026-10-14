from odoo import fields, models


class AiBotConversation(models.Model):
    """odoo_mcp_manager's ai.bot.conversation already tracks chat memory per
    platform (telegram/whatsapp/web/discord) keyed by
    ``platform:platform_user_id``. Add 'discuss' as another platform so
    internal Discuss conversations with the Chat AI bot get the same
    persisted history, keyed by the discuss.channel id."""

    _inherit = "ai.bot.conversation"

    platform = fields.Selection(
        selection_add=[("discuss", "Discuss (Internal)")],
        # The base field is required=True with no default, so 'set default'
        # (what mercas_ai's ai_bot_channel.py uses for its own
        # selection_add) is not valid here — it would raise on load. If
        # chat_ai is ever uninstalled, drop the now-orphaned conversations
        # instead of leaving them with an undefined platform value.
        ondelete={"discuss": "cascade"},
    )
