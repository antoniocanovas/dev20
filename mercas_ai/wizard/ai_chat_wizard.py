from odoo import models


class AiChatWizard(models.TransientModel):
    """Backend console covering sales/purchases/invoicing/stock ('AI Chat').

    Always-visible menu entry. All logic (classification prompt, business
    rules, deterministic formatting) lives in MercasDomainChatMixin
    (domain_chat_mixin.py), shared with the debug-only 'AI Queries'
    wizard (ai_domain_chat_wizard.py) — see that mixin's docstring.

    Was previously a general-purpose assistant that used LLMRouter to pick
    freely among every ai.tool (search/create/update/delete on any model)
    and humanized results with a second LLM call. Retired: LLMRouter only
    ever sees each tool's one-line ``description`` (never its
    ``input_schema``), so it had no idea about the report tools' own
    parameters or the business rules in prompts.py, and the "humanize" step
    risked letting the model rephrase — and mangle — numbers that were
    already exact. That generic routing capability still exists in
    odoo_mcp_manager (used by Telegram/WhatsApp/Web bot gateway); it's just
    no longer exposed via this menu.
    """

    _name = 'mercas.mcp.chat.wizard'
    _inherit = ['mercas.mcp.domain.chat.mixin']
    _description = 'AI Chat (Sales / Purchases / Invoicing / Stock)'
    _conversation_prefix = 'backend'
