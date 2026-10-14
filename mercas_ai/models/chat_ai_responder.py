import logging

from odoo import models

from ..wizard.domain_chat_mixin import _DOMAIN_TOOL, _OUT_OF_SCOPE_REPLY

_logger = logging.getLogger(__name__)


class ChatAiResponder(models.AbstractModel):
    """Route Chat AI / Discuss conversations through the same classify +
    deterministic report tools already used (and validated) by 'Chat IA'
    console (wizard/domain_chat_mixin.py), instead of chat_ai's default
    generic ask_ai passthrough.

    Deliberately does NOT go through the generic LLMRouter — see
    ai_chat_wizard.py's own docstring for why that path was retired from
    this business flow (LLMRouter never sees a tool's input_schema, only
    its one-line description, so it can't fill in sales_report's
    customer/date_from/group_by correctly).

    Reuses mercas.mcp.domain.chat.mixin's classification/dispatch methods
    directly (they don't touch any wizard-only field), so there is exactly
    one place that knows how to answer a sales/purchases/invoicing/stock
    question — the wizard, the debug wizard and Discuss all share it.
    """

    _inherit = "chat.ai.responder"

    def _get_reply(self, text, history):
        mixin = self.env["mercas.mcp.domain.chat.mixin"]
        try:
            parsed = mixin._classify(text, history)
        except RuntimeError:
            # No active ai.provider with chat models configured at all — a
            # setup problem, not an out-of-scope question (see the same
            # guard in domain_chat_mixin.py's action_send).
            _logger.warning("mercas_ai: no active AI provider configured")
            return self.env._(
                "There is no active AI provider configured. Ask an "
                "administrator to configure one in MCP Gateway → "
                "Configuration → Providers."
            )
        except Exception:
            _logger.exception("mercas_ai: domain classification failed")
            parsed = {"domain": "otro"}

        domain_key = (parsed.get("domain") or "otro").strip().lower()
        tool_name = _DOMAIN_TOOL.get(domain_key)
        if not tool_name:
            return self.env._(_OUT_OF_SCOPE_REPLY)

        params = mixin._build_tool_params(domain_key, parsed)
        return mixin._run_report(tool_name, domain_key, params)
