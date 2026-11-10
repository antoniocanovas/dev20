from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.scrap_base.models.purchase_order import normalize_plate

# Products shown on the screen
PRODUCT_LIMIT = 100
MODES = ('stock', 'assembled')


def is_record_id(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


class ScrapCrmAvailable(models.AbstractModel):
    """ What is available for an opportunity, on a touch screen opened from it:

    * In stock: the products in stock (not the scrap templates), of a brand (the one of the
      opportunity by default) or of all, and made of the scrap template asked for (the one of
      the opportunity by default), as the engines dismantled, or of any;
    * Assembled: the products in stock with the scrap template asked for (the one of the
      opportunity by default) still to dismantle in their bills of materials, as a vehicle
      with its engine.

    Both are searched by name, barcode, internal reference and the other references.
    """
    _name = 'scrap.crm.available'
    _description = "Available for an Opportunity"

    @api.model
    def get_screen_data(self, lead_id=False):
        """ The opportunity, its brand and its scrap template, and the brands and templates to
        choose from. """
        lead = self.env['crm.lead']
        if lead_id:
            if not is_record_id(lead_id):
                raise ValidationError(self.env._("Invalid opportunity."))
            lead = lead.browse(lead_id).exists()
            lead.check_access('read')
        Template = self.env['product.template']
        brands = self.env['fleet.vehicle.model.brand'].browse([
            brand.id for [brand] in Template._read_group(
                [('scrap_vehicle_brand_id', '!=', False), ('is_template', '=', False)],
                ['scrap_vehicle_brand_id'])
        ]) | lead.brand_id
        templates = Template.search([('is_template', '=', True)], order='name, id') | lead.scrap_template_id
        return {
            'lead': lead and {'id': lead.id, 'name': lead.display_name, 'partner': lead.partner_id.display_name or ''},
            'brand_id': lead.brand_id.id,
            'template_id': lead.scrap_template_id.id,
            'brands': [{'id': brand.id, 'name': brand.name} for brand in brands.sorted('name')],
            'templates': [{'id': template.id, 'name': template.display_name} for template in templates.sorted('name')],
        }

    @api.model
    def search_available(self, mode='stock', query='', brand_id=False, template_id=False):
        """ The products of `mode` ('stock' or 'assembled'), with how many there are of each one.

        :return: {'products': [...], 'counts': {'stock': int, 'assembled': int}}
        """
        if mode not in MODES:
            raise ValidationError(self.env._("Invalid option."))
        for value in (brand_id, template_id):
            if value and not is_record_id(value):
                raise ValidationError(self.env._("Invalid filter."))
        template = self.env['product.template'].browse(template_id or [])
        Template = self.env['product.template']
        domains = {
            'stock': self._get_stock_domain(query, brand_id) + (
                [('scrap_template_id', '=', template.id)] if template else []),
            'assembled': self._get_assembled_domain(query, brand_id, template),
        }
        products = Template.search(domains[mode], limit=PRODUCT_LIMIT, order='write_date desc, id desc') if domains[mode] is not None else Template
        return {
            'products': [self._get_product_data(product, template if mode == 'assembled' else False) for product in products],
            'counts': {key: Template.search_count(domain) if domain is not None else 0 for key, domain in domains.items()},
        }

    def _get_stock_domain(self, query, brand_id):
        """ In stock, of the brand. """
        domain = [
            ('is_template', '=', False), ('qty_available', '>', 0),
            *self.env['product.template']._check_company_domain(self.env.company),
        ]
        if brand_id:
            domain.append(('scrap_vehicle_brand_id', '=', brand_id))
        return domain + self._get_query_domain(query)

    def _get_assembled_domain(self, query, brand_id, template):
        """ In stock, with the template still to dismantle in a bill of materials; None without
        template. """
        if not template:
            return None
        return self._get_stock_domain(query, brand_id) + [
            ('bom_ids.bom_line_ids', 'any', [
                ('product_id.product_tmpl_id', '=', template.id), ('product_qty', '>', 0)]),
        ]

    def _get_query_domain(self, query):
        """ By name, barcode, internal reference and the other references of the product. """
        query = query.strip() if isinstance(query, str) else ''
        if not query:
            return []
        plate = normalize_plate(query) or query
        conditions = [
            ('name', 'ilike', query),
            ('default_code', 'ilike', query),
            ('product_variant_ids.default_code', 'ilike', query),
            ('product_variant_ids.barcode', 'ilike', query),
            ('ref_market', 'ilike', query),
            ('ref_oem', 'ilike', query),
            ('references', 'ilike', query),
            ('product_variant_ids.chassis', 'ilike', query),
            ('plate', 'ilike', query),
            ('scrap_lot_name', 'ilike', plate),
        ]
        return ['|'] * (len(conditions) - 1) + conditions

    def _get_product_data(self, product, template=False):
        variant = product.product_variant_id
        quant = self.env['stock.quant'].sudo().search([
            ('product_id', 'in', product.product_variant_ids.ids), ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)], limit=1, order='quantity desc')
        unbuild_types = dict(product._fields['scrap_unbuild_type']._description_selection(self.env))
        data = {
            'id': product.id,
            'product_id': variant.id,
            'name': product.display_name,
            'ref': product.default_code or '',
            'plate': product.scrap_lot_name or product.plate or '',
            'model': product.vehicle_model_id.name or '',
            'brand': product.scrap_vehicle_brand_id.name or '',
            'ref_market': product.ref_market or '',
            'ref_oem': product.ref_oem or '',
            'qty_available': product.qty_available,
            'uom': product.uom_id.name,
            'location': quant.location_id.sudo().complete_name or '',
            'unbuild_type_label': unbuild_types.get(product.scrap_unbuild_type, ''),
            'image_unique': str(product.write_date) if product.image_128 else False,
            # Its photos (website_sale), the main one among them
            'image_count': len(variant._get_images().filtered('image_1920')) if product.image_128 else 0,
        }
        if template:
            # How many of the template are still to dismantle in it
            lines = product.sudo().bom_ids.bom_line_ids.filtered(
                lambda line: line.product_id.product_tmpl_id == template and line.product_qty > 0)
            data['pending_qty'] = sum(lines.mapped('product_qty'))
            data['pending_name'] = template.display_name
        return data

    @api.model
    def get_product_images(self, template_id):
        """ The photos of a product, as in the shop (website_sale): its main image and the extra
        ones, in their order.

        :return: [{'model', 'id', 'name', 'unique'}], to show their image_1024
        """
        if not is_record_id(template_id):
            raise ValidationError(self.env._("Invalid product."))
        product = self.env['product.template'].browse(template_id).exists()
        product.check_access('read')
        return [{
            'model': image._name,
            'id': image.id,
            'name': image.name or product.display_name,
            'unique': str(image.write_date),
        } for image in product.product_variant_id._get_images() if image.image_1920]
