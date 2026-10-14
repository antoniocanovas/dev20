from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestMercasAiUi(HttpCase):

    def test_chat_widgets(self):
        self.start_tour("/odoo/action-mercas_ai.ai_chat_wizard_action", "mercas_ai_chat_tour", login="admin")

    def test_mcp_dashboard(self):
        self.start_tour("/odoo/action-odoo_mcp_manager.ai_hub_dashboard_client_action", "mercas_ai_mcp_dashboard_tour", login="admin")
