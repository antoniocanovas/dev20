import html
import logging

from markupsafe import Markup

from odoo import models
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)


class ChatAiBot(models.AbstractModel):
    """Detects messages addressed to the Chat AI persona in a 1:1 Discuss
    chat and posts the reply.

    Mirrors the core mail_bot module (OdooBot): discuss_channel.py hooks
    ``_message_post_after_hook`` and delegates here, exactly like
    ``discuss_channel._message_post_after_hook`` → ``mail.bot._apply_logic``
    does for base.partner_root. We use our own bot user instead of OdooBot
    so access can be gated by a dedicated group and the reply logic can be
    swapped per business module (see chat.ai.responder).
    """

    _name = "chat.ai.bot"
    _description = "Chat AI — Discuss Dispatcher"

    def _apply_logic(self, channel, values):
        channel.ensure_one()
        bot = self.env.ref("chat_ai.user_chat_ai_bot", raise_if_not_found=False)
        if not bot:
            return
        bot_partner_id = bot.partner_id.id

        # Never react to our own messages (avoids an infinite reply loop) and
        # ignore anything that isn't a plain user message (joins, leaves...).
        if values.get("author_id") == bot_partner_id:
            return
        if values.get("message_type") != "comment":
            return
        # Only 1:1 chats where the bot is actually a member — never group
        # channels or public channels, even if someone adds the bot there.
        if channel.channel_type != "chat":
            return
        if bot_partner_id not in channel.channel_member_ids.partner_id.ids:
            return

        text = html2plaintext(values.get("body") or "").strip()
        if not text:
            return

        # Reply in the asking user's language: a Discuss post doesn't always
        # carry the user's lang in its context, and every reply string goes
        # through self.env._(), which translates into env.lang.
        self = self.with_context(lang=self.env.user.lang or self.env.lang)

        if not self.env.user.has_group("chat_ai.group_ai_chat_user"):
            reply = self._not_authorized_reply()
        else:
            reply = self._get_reply(channel, text)

        # A business responder (e.g. mercas_ai's) returns a Markup instance:
        # already-safe HTML it built itself (every dynamic value individually
        # escaped, real <a> links to Odoo records allowed on purpose) — never
        # escape that again or the tags would show up as literal text. Plain
        # str replies (raw LLM text, our own fixed strings) are never HTML
        # and must be escaped: (a) a literal "\n\n" is invisible once
        # rendered as HTML (whitespace collapses, no visible line break), and
        # (b) anything that happens to contain "<"/">"/"&" (a partner name,
        # raw LLM text) would be interpreted as HTML instead of shown as text.
        if isinstance(reply, Markup):
            # Markup.replace() escapes a plain-str replacement before
            # substituting it in (it assumes any bare str passed to it needs
            # escaping) — a literal "<br/>" would come out as "&lt;br/&gt;".
            # Passing a Markup("<br/>") instead tells it the replacement is
            # already-safe HTML, so it's inserted as a real line break.
            safe_body = reply.replace("\n", Markup("<br/>"))
        else:
            safe_body = Markup(html.escape(reply).replace("\n", "<br/>"))

        channel.sudo().message_post(
            author_id=bot_partner_id,
            body=safe_body,
            message_type="comment",
            silent=True,
            subtype_xmlid="mail.mt_comment",
        )

    def _not_authorized_reply(self):
        """Single source of truth for the 'not in the group' message, so
        every entry point that gates on chat_ai.group_ai_chat_user (this
        Discuss hook, and mercas_ai's own wizard) says exactly the same
        thing instead of each hardcoding its own copy that can drift."""
        return self.env._(
            "No tienes habilitado este servicio, habla con tu administrador."
        )

    def _get_reply(self, channel, text):
        """Run the actual reply logic for an authorized user and persist
        the exchange. Kept separate from the group gate so a rejection
        message never touches conversation history or costs an LLM call."""
        conversation = self.env["ai.bot.conversation"].sudo().get_or_create(
            "discuss", str(channel.id), platform_user_name=self.env.user.name,
        )
        history = conversation.get_recent_messages(limit=10)
        try:
            reply = self.env["chat.ai.responder"]._get_reply(text, history)
        except Exception:
            _logger.exception(
                "chat_ai: reply generation failed on channel %s", channel.id
            )
            reply = self.env._(
                "Lo siento, ha ocurrido un error generando la respuesta. "
                "Inténtalo de nuevo."
            )
        conversation.sudo().add_message("user", text, None)
        conversation.sudo().add_message("assistant", reply, None)
        return reply
