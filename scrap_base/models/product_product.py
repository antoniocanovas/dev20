from odoo import api, fields, models
from odoo.fields import Domain

# Fields of the CAT data where a product is also found by its name, as its internal reference
CAT_SEARCH_FIELDS = ('chassis', 'plate', 'ref_oem', 'ref_market', 'references')


class ProductProduct(models.Model):
    _inherit = 'product.product'

    chassis = fields.Char(
        'Chassis', copy=False, index='btree_not_null',
        help="Chassis (VIN) of the vehicle or the accessory, of this variant.")

    def action_scrap_complete_vehicle(self):
        return self.product_tmpl_id.action_scrap_complete_vehicle()

    @api.model
    def _get_cat_search_domain(self, operator, value):
        """ Products whose CAT data match, or, with a negative operator, whose CAT data don't. """
        domains = [[(field, operator, value)] for field in CAT_SEARCH_FIELDS]
        if operator in Domain.NEGATIVE_OPERATORS:
            return Domain.AND(domains)
        return Domain.OR(domains)

    def _search_display_name(self, operator, value):
        """ Found by the CAT data too: in any product field, and in the products of a
        template. """
        domain = super()._search_display_name(operator, value)
        if not value:
            return domain
        if operator in Domain.NEGATIVE_OPERATORS:
            return Domain(domain) & self._get_cat_search_domain(operator, value)
        return Domain(domain) | self._get_cat_search_domain(operator, value)

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        """ After the internal reference, the barcode and the name, the CAT data. """
        result = super().name_search(name, domain, operator, limit)
        if not name or operator in Domain.NEGATIVE_OPERATORS or (limit and len(result) >= limit):
            return result
        found = [product_id for product_id, _name in result]
        products = self.search_fetch(
            Domain(domain or Domain.TRUE) & Domain('id', 'not in', found) & self._get_cat_search_domain(operator, name),
            ['display_name'], limit=limit and limit - len(result))
        return result + [(product.id, product.display_name) for product in products.sudo()]

    @api.onchange('chassis')
    def _onchange_chassis(self):
        return self._get_chassis_warning(self.chassis, self._origin)

    def _get_chassis_warning(self, chassis, products):
        """ A warning, as for the internal reference, when another product has the chassis. """
        if not chassis:
            return None
        domain = [('chassis', '=', chassis)]
        if products:
            domain.append(('id', 'not in', products.ids))
        other = self.env['product.product'].with_context(active_test=False).search(domain, limit=1)
        if other:
            return {'warning': {
                'title': self.env._("Note:"),
                'message': self.env._("The chassis %(chassis)s is already in %(product)s.",
                                      chassis=chassis, product=other.display_name),
            }}
        return None
