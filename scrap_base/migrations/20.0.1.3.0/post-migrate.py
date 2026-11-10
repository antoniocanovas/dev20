from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """ The subproducts dismantled before keep the vehicle they come from, found through the
    parts marked (the oldest first, so that a subproduct of a subproduct finds its vehicle),
    with its location and its analytic account. """
    env = api.Environment(cr, SUPERUSER_ID, {'active_test': False})
    lines = env['scrap.dismantle.line'].search([('stage', '=', 'dismantling')], order='id')
    Distribution = env['account.analytic.distribution.model']
    for line in lines:
        part = line.product_id.product_tmpl_id
        if not part.scrap_template_id or part.scrap_origin_id or part == line.bom_line_id.product_id.product_tmpl_id:
            continue
        origin = line.vehicle_id.scrap_origin_id or line.vehicle_id
        if part == origin:
            continue
        part.write({
            'scrap_origin_id': origin.id,
            'scrap_location_id': part.scrap_location_id.id or origin.scrap_location_id.id,
            'scrap_analytic_account_id': part.scrap_analytic_account_id.id or origin.scrap_analytic_account_id.id,
        })
        account = part.scrap_analytic_account_id
        product = part.product_variant_id
        if account and product and not Distribution.search_count([('product_id', '=', product.id)], limit=1):
            Distribution.create({
                'product_id': product.id,
                'analytic_distribution': {str(account.id): 100},
                'company_id': (part.company_id or line.company_id).id,
            })
