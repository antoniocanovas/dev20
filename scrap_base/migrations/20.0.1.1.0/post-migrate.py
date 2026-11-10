from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """ The analytic plans and the locations of the vehicles, as on install. """
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['res.company']._scrap_base_set_defaults()
