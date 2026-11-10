from odoo import models
from odoo.exceptions import AccessError, UserError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _scrap_sold_to(self):
        """ The customer the vehicle was delivered to, if it isn't in stock anymore: the one of
        its last delivery done. """
        self.ensure_one()
        move = self.env['stock.move'].sudo().search([
            ('product_id', 'in', self.product_variant_ids.ids),
            ('state', '=', 'done'),
            ('location_dest_id.usage', '=', 'customer'),
        ], order='date desc, id desc', limit=1)
        return (move.picking_id.partner_id or move.partner_id or move.sale_line_id.order_id.partner_id).sudo(False)

    def _scrap_stock_quant(self):
        """ Where the vehicle is in stock, with its serial number. """
        self.ensure_one()
        return self.env['stock.quant'].sudo().search([
            ('product_id', 'in', self.product_variant_ids.ids),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0),
        ], limit=1)

    def _scrap_can_repair(self):
        """ A vehicle to repair and sell, in stock or already sold. """
        self.ensure_one()
        return (
            self.scrap_unbuild_type == 'refurbish' and bool(self.scrap_template_id)
            and (bool(self._scrap_stock_quant()) or bool(self._scrap_sold_to()))
        )

    def _scrap_open_repairs(self):
        self.ensure_one()
        return self.env['repair.order'].search([
            ('product_id', 'in', self.product_variant_ids.ids),
            ('state', 'in', ('draft', 'confirmed')),
        ], order='id desc')

    def _scrap_get_repair(self):
        """ The repair of the vehicle not done yet, or a new one: in stock, where it is, without
        customer (it is repaired to sell it); already sold, of its customer, at the customer
        location. Its parts and services go to the analytic account of the vehicle, and, sold,
        also its sales. """
        self.ensure_one()
        if not self.env.user.has_group('stock.group_stock_user'):
            raise AccessError(self.env._("Only the inventory users can repair the vehicles."))
        self.check_access('read')
        if self.scrap_unbuild_type != 'refurbish' or not self.scrap_template_id:
            raise UserError(self.env._("%s isn't a vehicle to repair and sell.", self.display_name))
        repair = self._scrap_open_repairs()[:1]
        if repair:
            return repair
        product = self.product_variant_id
        company = self.company_id or self.env.company
        vals = {
            'product_id': product.id,
            'company_id': company.id,
            'product_qty': 1.0,
            'uom_id': product.uom_id.id,
        }
        quant = self._scrap_stock_quant()
        if quant:
            vals.update({
                'lot_id': quant.lot_id.id,
                'product_location_src_id': quant.location_id.id,
                'product_location_dest_id': quant.location_id.id,
            })
        else:
            partner = self._scrap_sold_to()
            if not partner:
                raise UserError(self.env._("%s isn't in stock nor sold: receive it first.", self.display_name))
            location = partner.with_company(company).property_stock_customer
            lot = self.env['stock.lot'].search([('product_id', '=', product.id)], limit=1)
            vals.update({
                'partner_id': partner.id,
                'lot_id': lot.id,
                'product_location_src_id': location.id,
                'product_location_dest_id': location.id,
            })
        return self.env['repair.order'].with_company(company).create(vals)
