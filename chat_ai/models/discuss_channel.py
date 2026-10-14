import logging

from odoo import models

_logger = logging.getLogger(__name__)


class DiscussChannel(models.Model):
    """Same hook point core's mail_bot uses for OdooBot
    (odoo/addons/mail_bot/models/discuss_channel.py) — runs after every
    message post, wrapped defensively so a bug here can never break normal
    message posting on any channel."""

    _inherit = "discuss.channel"

    def _message_post_after_hook(self, message):
        try:
            self.env["chat.ai.bot"]._apply_logic(self, {
                "author_id": message.author_id.id,
                "message_type": message.message_type,
                "body": message.body,
            })
        except Exception:
            _logger.exception("chat_ai: bot dispatch failed for channel %s", self.id)
        return super()._message_post_after_hook(message)
