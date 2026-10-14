from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestMercasKeysUi(HttpCase):

    def test_unified_screen(self):
        self.start_tour("/odoo/action-mercas_keys.action_mercas_unified_screen", "mercas_keys_tour", login="admin")
