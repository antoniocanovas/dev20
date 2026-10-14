from odoo import models


class ChatAiResponder(models.AbstractModel):
    """Reply engine for the Chat AI Discuss bot.

    This default implementation is a plain passthrough to the generic
    ``ask_ai`` tool from odoo_mcp_manager — no business logic, no domain
    restriction. Business modules should ``_inherit`` this model and
    override ``_get_reply`` to plug in their own classification and
    ``ai.tool`` dispatch instead (see mercas_ai, which routes through
    its existing sales/purchase/invoice/stock report tools rather than this
    default). chat_ai itself never assumes which business module, if any,
    is installed.
    """

    _name = "chat.ai.responder"
    _description = "Chat AI — Reply Engine"

    def _get_reply(self, text, history):
        """Return the plain-text reply for *text*, given prior *history*
        (list of {'role', 'content'} dicts, oldest first)."""
        tool = self.env["ai.tool"].sudo().search(
            [("name", "=", "ask_ai"), ("active", "=", True)], limit=1
        )
        if not tool:
            return self.env._(
                "No hay ningún proveedor de IA configurado todavía. Pide a un "
                "administrador que configure uno en MCP Gateway → "
                "Configuración → Proveedores."
            )
        convo = "\n".join(f"{h['role']}: {h['content']}" for h in (history or [])[-6:])
        prompt = text
        if convo:
            prompt = self.env._("Conversación previa:\n%s\n\n") % convo + text
        return tool.execute({"prompt": prompt})
