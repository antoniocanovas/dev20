import logging

from odoo import fields, models
from odoo.exceptions import AccessDenied

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    chat_ai_greeted = fields.Boolean(
        default=False,
        readonly=True,
        help="Whether the Chat AI bot has already sent this user its "
             "welcome DM. Prevents re-greeting on every page load.",
    )

    def _check_credentials(self, credential, env):
        """Hard-block any login attempt for the Chat AI bot user, no matter
        what is submitted. This does not rely on the account simply having
        no password set (which a later password-reset flow or an admin
        typo could silently undo) — the bot account can never authenticate,
        full stop."""
        bot = self.env.ref("chat_ai.user_chat_ai_bot", raise_if_not_found=False)
        if bot and self.id == bot.id:
            raise AccessDenied()
        return super()._check_credentials(credential, env)

    def _on_webclient_bootstrap(self):
        super()._on_webclient_bootstrap()
        try:
            self._chat_ai_maybe_greet()
        except Exception:
            _logger.exception("chat_ai: greeting failed for user %s", self.id)

    def _chat_ai_maybe_greet(self):
        """Proactively open (or reuse) the 1:1 Discuss chat with the bot and
        send a one-time welcome message, exactly like core's OdooBot does
        via _init_odoobot — so authorized users see the AI in their Discuss
        sidebar without having to find it via 'New Message' search first."""
        self.ensure_one()
        if self.chat_ai_greeted or not self._is_internal():
            return
        if not self.has_group("chat_ai.group_ai_chat_user"):
            return
        bot = self.env.ref("chat_ai.user_chat_ai_bot", raise_if_not_found=False)
        if not bot or bot.id == self.id:
            return
        channel = self.env["discuss.channel"]._get_or_create_chat(
            [bot.partner_id.id, self.partner_id.id]
        )
        channel.sudo().message_post(
            author_id=bot.partner_id.id,
            body=self.env._(
                "Hola, soy el Asistente IA. Pregúntame lo que necesites."
            ),
            message_type="comment",
            silent=True,
            subtype_xmlid="mail.mt_comment",
        )
        self.sudo().chat_ai_greeted = True
