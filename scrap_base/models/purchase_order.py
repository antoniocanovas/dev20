import re

from odoo import api, fields, models
from odoo.exceptions import UserError

from .res_company import VEHICLE_TYPES

# Kinds of entry of the vehicle recycling, as `unbuild_type` of scrap_unbuild (Odoo 17)
UNBUILD_TYPES = [
    ('main', 'Vehículo o Parte para desguace'),
    ('subproduct', 'Subproducto'),
    ('refurbish', 'Para compra/venta'),
    ('other', 'Otros finales desguazados'),
]
# Spaces and hyphens, left out of the license plates
PLATE_SEPARATORS = re.compile(r'[\s\-]+')


def normalize_plate(value):
    """ A license plate as it is saved: in capitals, without spaces nor hyphens, so that
    "1234 ABC", "1234-abc" and "1234ABC" are the same vehicle. """
    return PLATE_SEPARATORS.sub('', value).upper() if isinstance(value, str) else ''


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    unbuild_type = fields.Selection(
        UNBUILD_TYPES, string='Scrap Type', index=True, copy=True,
        help="Kind of entry of the purchase: vehicles to dismantle, or to repair and sell whole.")

    def button_confirm(self):
        for order in self.filtered(lambda order: order.state in ('draft', 'sent')):
            order._scrap_create_vehicles()
        return super().button_confirm()

    def button_cancel(self):
        result = super().button_cancel()
        self.filtered(lambda order: order.state == 'cancel').order_line._scrap_release_vehicles()
        return result

    def _scrap_create_vehicles(self):
        """ Each vehicle bought to dismantle, or to repair and sell, becomes a product of its
        own: a copy of its scrap template, with its license plate, the cost of the purchase, an
        analytic account in the plan of its kind of entry and a location named after its
        license plate, under the one of its kind of entry, where it is received. The line of
        the purchase, and so its receipt and its bill, then go with the new product. """
        self.ensure_one()
        if self.unbuild_type not in VEHICLE_TYPES:
            return
        lines = self.order_line.filtered(lambda line: not line.display_type and line.product_id.is_template)
        if not lines:
            return
        company = self.company_id
        plan = company._get_scrap_analytic_plan(self.unbuild_type)
        parent_location = company._get_scrap_location(self.unbuild_type)
        if not plan or not parent_location:
            raise UserError(self.env._(
                "Set the analytic plan and the location of the vehicles of this kind of entry in "
                "the CAT tab of the company %s.", company.name))
        plates = set()
        for line in lines:
            line._scrap_check_vehicle_line()
            if line.scrap_lot_name in plates:
                raise UserError(self.env._(
                    "The license plate %s is in more than one line.", line.scrap_lot_name))
            plates.add(line.scrap_lot_name)
        for line in lines:
            line._scrap_create_vehicle(plan, parent_location)


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    scrap_lot_name = fields.Char(
        'License Plate', copy=False,
        help="License plate of the vehicle, given to it as serial number when it is received.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('scrap_lot_name'):
                vals['scrap_lot_name'] = normalize_plate(vals['scrap_lot_name'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('scrap_lot_name'):
            vals = dict(vals, scrap_lot_name=normalize_plate(vals['scrap_lot_name']))
        return super().write(vals)

    def _scrap_check_vehicle_line(self):
        """ A vehicle is bought alone in its line, with its license plate, not used by another
        vehicle. """
        self.ensure_one()
        product = self.product_id
        if len(product.product_tmpl_id.product_variant_ids) > 1:
            raise UserError(self.env._(
                "The scrap template %s has variants: a vehicle template can't have them.",
                product.display_name))
        if self.uom_id.compare(self.product_qty, 1.0) or self.uom_id != product.uom_id:
            raise UserError(self.env._(
                "Each vehicle goes in a line of its own, with a quantity of 1 %(uom)s: %(product)s.",
                uom=product.uom_id.name, product=product.display_name))
        if not self.scrap_lot_name:
            raise UserError(self.env._("Enter the license plate of %s.", product.display_name))
        if self.env['product.template']._scrap_find_vehicles(self.scrap_lot_name, self.company_id):
            raise UserError(self.env._(
                "There is already a vehicle with the license plate %s.", self.scrap_lot_name))

    def _scrap_vehicle_unbuild_type(self):
        """ The scrap type of the product bought: the one of the purchase, but a subproduct
        bought to dismantle (as an engine, of a template of subproducts) is still a subproduct,
        dismantled without decontaminating it nor legal deadlines, and the origin of its own
        subproducts. """
        unbuild_type = self.order_id.unbuild_type
        if unbuild_type == 'main' and self.product_id.scrap_unbuild_type == 'subproduct':
            return 'subproduct'
        return unbuild_type

    def _scrap_create_vehicle(self, plan, parent_location):
        self.ensure_one()
        company = self.company_id
        template = self.product_id.product_tmpl_id
        plate = self.scrap_lot_name
        # Made by confirming the purchase, also by users that can't create products
        vehicle = template.sudo().with_company(company).copy({
            'name': f"{template.name} {plate}",
            'is_template': False,
            'default_code': False,
            'scrap_template_id': template.id,
            'scrap_unbuild_type': self._scrap_vehicle_unbuild_type(),
            'company_id': company.id,
            'scrap_lot_name': plate,
            # Sold whole, although its template isn't sold
            **({'sale_ok': True} if self.order_id.unbuild_type == 'refurbish' else {}),
        })
        vehicle._scrap_complete_vehicle(plan, parent_location)
        product = vehicle.product_variant_id
        # The cost of the purchase, in the currency of the company
        product.with_company(company).standard_price = self._get_stock_move_price_unit()
        product = product.with_env(self.env)
        account = vehicle.scrap_analytic_account_id
        # The values computed from the product are written again, so that they are kept
        self.write({
            'product_id': product.id,
            'product_qty': self.product_qty,
            'uom_id': self.uom_id.id,
            'price_unit': self.price_unit,
            'discount': self.discount,
            'tax_ids': [fields.Command.set(self.tax_ids.ids)],
            'date_planned': self.date_planned,
            'analytic_distribution': {str(account.id): 100},
        })

    def _scrap_release_vehicles(self):
        """ The vehicles of a cancelled purchase that were never received give their license
        plate back: the line goes back to their scrap template, and the vehicle, its location,
        its analytic account and its distribution are archived or removed. """
        for line in self.filtered(lambda line: line.product_id.scrap_template_id):
            product = line.product_id
            if self.env['stock.move'].search_count([('product_id', '=', product.id), ('state', '=', 'done')], limit=1):
                continue
            template = product.scrap_template_id.product_variant_id
            if not template:
                continue
            line.write({
                'product_id': template.id,
                'product_qty': line.product_qty,
                'uom_id': line.uom_id.id,
                'price_unit': line.price_unit,
                'discount': line.discount,
                'tax_ids': [fields.Command.set(line.tax_ids.ids)],
                'date_planned': line.date_planned,
                'analytic_distribution': False,
                'scrap_lot_name': product.scrap_lot_name,
            })
            self.env['account.analytic.distribution.model'].sudo().search([('product_id', '=', product.id)]).unlink()
            product.scrap_location_id.sudo().active = False
            product.scrap_analytic_account_id.sudo().active = False
            product.product_tmpl_id.sudo().active = False
