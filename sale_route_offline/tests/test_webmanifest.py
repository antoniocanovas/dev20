from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestRouteWebManifest(HttpCase):

    def _shortcut_urls(self):
        manifest = self.url_open('/web/manifest.webmanifest').json()
        return [shortcut['url'] for shortcut in manifest.get('shortcuts', [])]

    def test_route_shortcut(self):
        new_test_user(self.env, login='route_manifest_salesman', groups='sales_team.group_sale_salesman')
        new_test_user(self.env, login='route_manifest_user', groups='base.group_user')
        self.authenticate('route_manifest_salesman', 'route_manifest_salesman')
        self.assertIn('/odoo/route-sales', self._shortcut_urls())
        self.authenticate('route_manifest_user', 'route_manifest_user')
        self.assertNotIn('/odoo/route-sales', self._shortcut_urls())
