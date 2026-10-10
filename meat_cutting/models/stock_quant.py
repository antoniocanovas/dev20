from datetime import timedelta

from odoo import Command, fields, models
from odoo.exceptions import UserError

from ..tools import gs1_barcode_text, gs1_barcode_value, gs1_item_parts


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    # Data of the animal of the lot, stored to filter and group the stock
    crotal_id = fields.Many2one(related='lot_id.crotal_id', store=True, index='btree_not_null')
    crotal_partner_id = fields.Many2one(related='lot_id.crotal_partner_id', store=True)
    crotal_sex = fields.Selection(related='lot_id.crotal_sex', store=True)
    crotal_halal = fields.Boolean(related='lot_id.crotal_halal', store=True)
    crotal_breed = fields.Char(related='lot_id.crotal_breed', store=True)
    crotal_quality = fields.Char(related='lot_id.crotal_quality', store=True)
    crotal_birth_date = fields.Date(related='lot_id.crotal_birth_date', store=True)
    crotal_slaughter_date = fields.Date(related='lot_id.crotal_slaughter_date', store=True)
    crotal_birth_country = fields.Char(related='lot_id.crotal_birth_country', store=True)
    crotal_reared_country = fields.Char(related='lot_id.crotal_reared_country', store=True)

    def action_meat_freeze(self):
        """ Freeze fresh stock: its quantity becomes the frozen product of the
        cut, in the same location and package, in a lot of the same animal
        (crotal) whose shelf life starts now. """
        quants = self.filtered(lambda q: q.location_id.usage == 'internal' and q.product_id.uom_id.compare(q.quantity, 0) > 0)
        if not quants:
            raise UserError(self.env._("Select fresh stock to freeze."))
        for quant in quants:
            if not quant.product_id.frozen_product_id:
                raise UserError(self.env._("%s has no frozen product.", quant.product_id.display_name))
            if quant.product_id.uom_id.compare(quant.reserved_quantity, 0) > 0:
                raise UserError(self.env._(
                    "%(product)s %(lot)s is reserved for a transfer: unreserve it before freezing it.",
                    product=quant.product_id.display_name, lot=quant.lot_id.name or '',
                ))
        frozen_quants = self.browse()
        for quant in quants:
            frozen_quants |= quant._meat_freeze()
        # The pieces changed of product and shelf life: relabel them
        return self.env.ref('meat_cutting.action_report_meat_piece_label').report_action(frozen_quants)

    def _meat_freeze(self):
        self.ensure_one()
        product = self.product_id
        frozen_product = product.frozen_product_id
        company = self.company_id or self.env.company
        quantity = self.quantity
        frozen_lot = self._meat_get_frozen_lot()
        Move = self.env['stock.move']
        common_vals = {
            'uom_id': product.uom_id.id,
            'product_uom_qty': quantity,
            'procure_method': 'make_to_stock',
            'company_id': company.id,
            'origin': self.env._("Freezing of %s", self.lot_id.name or product.display_name),
        }
        consume_move = Move.create(dict(
            common_vals,
            product_id=product.id,
            location_id=self.location_id.id,
            location_dest_id=product.with_company(company).property_stock_production.id,
        ))
        produce_move = Move.create(dict(
            common_vals,
            product_id=frozen_product.id,
            uom_id=frozen_product.uom_id.id,
            product_uom_qty=product.uom_id._compute_quantity(quantity, frozen_product.uom_id),
            location_id=frozen_product.with_company(company).property_stock_production.id,
            location_dest_id=self.location_id.id,
        ))
        moves = consume_move | produce_move
        moves._action_confirm()
        moves.move_line_ids.unlink()
        self.env['stock.move.line'].create([{
            'move_id': consume_move.id,
            'product_id': product.id,
            'uom_id': product.uom_id.id,
            'quantity': quantity,
            'lot_id': self.lot_id.id,
            'package_id': self.package_id.id,
            'location_id': consume_move.location_id.id,
            'location_dest_id': consume_move.location_dest_id.id,
        }, {
            'move_id': produce_move.id,
            'product_id': frozen_product.id,
            'uom_id': frozen_product.uom_id.id,
            'quantity': produce_move.product_uom_qty,
            'lot_id': frozen_lot.id,
            # A frozen piece stays in its package
            'result_package_id': self.package_id.id,
            'location_id': produce_move.location_id.id,
            'location_dest_id': produce_move.location_dest_id.id,
        }])
        moves.picked = True
        consume_move._action_done()
        produce_move._action_done()
        # Traceability: the frozen lot comes from the fresh one
        consume_move.move_line_ids.produce_line_ids = [Command.set(produce_move.move_line_ids.ids)]
        return self.search([
            ('product_id', '=', frozen_product.id),
            ('location_id', '=', self.location_id.id),
            ('lot_id', '=', frozen_lot.id),
            ('package_id', '=', self.package_id.id),
            ('quantity', '>', 0),
        ])

    # ------------------------------------------------------------------
    # Piece label: the stock relabelled out of the cutting, e.g. once frozen
    # ------------------------------------------------------------------

    def _get_meat_label_values(self):
        """ Texts of the label of the stock, from its lot and crotal. The
        date is when it entered the stock: its cutting, or its freezing for a
        frozen product. """
        self.ensure_one()
        lot = self.lot_id
        crotal = lot.crotal_id
        product = self.product_id
        return {
            'product_name': product.name,
            'lot_name': lot.name or '',
            'package_name': self.package_id.name or '',
            'crotal': crotal,
            'birth_country': crotal.birth_country or '',
            'reared_country': crotal.reared_country or '',
            'slaughter_date': crotal.slaughter_date or False,
            'supplier': crotal.partner_id.name or '',
            'frozen': bool(self.env['product.template'].search_count(
                [('frozen_product_id', '=', product.id)], limit=1)),
            'date': self.in_date and fields.Datetime.context_timestamp(self, self.in_date).date(),
            'expiration_date': lot.expiration_date and fields.Datetime.context_timestamp(
                self, lot.expiration_date).date(),
            'weight': self.quantity,
            'uom': product.uom_id,
        }

    def _get_meat_label_gs1_parts(self):
        self.ensure_one()
        values = self._get_meat_label_values()
        is_kg = values['uom'] == self.env.ref('uom.product_uom_kgm', raise_if_not_found=False)
        return gs1_item_parts(
            self.product_id.barcode,
            weight_kg=values['weight'] if is_kg else None,
            expiration_date=values['expiration_date'],
            lot_name=values['lot_name'],
        )

    def _get_meat_label_barcode_value(self):
        self.ensure_one()
        parts = self._get_meat_label_gs1_parts()
        return gs1_barcode_value(parts) if parts else (self.lot_id.name or self.product_id.barcode or '')

    def _get_meat_label_barcode_text(self):
        self.ensure_one()
        parts = self._get_meat_label_gs1_parts()
        return gs1_barcode_text(parts) if parts else self._get_meat_label_barcode_value()

    def _meat_get_frozen_lot(self):
        """ Lot of the frozen product named after the fresh lot, dated when a
        lot of that name already exists (frozen at the cutting or another
        day), as the shelf life of the frozen stock starts today. """
        self.ensure_one()
        frozen_product = self.product_id.frozen_product_id
        Lot = self.env['stock.lot']
        if frozen_product.tracking == 'none':
            return Lot
        if not self.lot_id:
            raise UserError(self.env._("Select the lot of %s to freeze it.", self.product_id.display_name))
        company = self.company_id or self.env.company
        domain = [('product_id', '=', frozen_product.id), ('company_id', 'in', [company.id, False])]
        name = self.lot_id.name
        if Lot.search_count(domain + [('name', '=', name)], limit=1):
            name = f'{name}-{fields.Date.context_today(self):%y%m%d}'
            existing_lot = Lot.search(domain + [('name', '=', name)], limit=1)
            if existing_lot:
                return existing_lot
        vals = {
            'product_id': frozen_product.id,
            'name': name,
            'company_id': company.id,
            'crotal_id': self.lot_id.crotal_id.id,
        }
        if frozen_product.use_expiration_date:
            vals['expiration_date'] = fields.Datetime.now() + timedelta(days=frozen_product.expiration_time)
        return Lot.create(vals)
