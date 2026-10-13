from odoo.http import request

from odoo.addons.web.controllers import webmanifest


class WebManifest(webmanifest.WebManifest):

    def _get_shortcuts(self):
        """ Open the route screen with a long press on the icon of the installed app. """
        shortcuts = super()._get_shortcuts()
        if request.env.user.has_group('sales_team.group_sale_salesman'):
            shortcuts.append({
                'name': request.env._("Route Sales"),
                'url': '/odoo/route-sales',
                'description': request.env._("Customers, orders and payments, also offline"),
                'icons': [{
                    'sizes': '100x100',
                    'src': '/sale_route_offline/static/description/icon.png',
                    'type': 'image/png',
                }],
            })
        return shortcuts
