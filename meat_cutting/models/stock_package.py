from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..tools import gs1_barcode_text, gs1_barcode_value, gs1_sscc


class StockPackageType(models.Model):
    _inherit = 'stock.package.type'

    meat_sscc_prefix = fields.Char(
        'SSCC Company Prefix',
        help="GS1 company prefix: the packages of this type are named with a SSCC (Serial Shipping Container "
             "Code) built from it, printed as a GS1-128 (00) barcode on their box label.")

    @api.constrains('meat_sscc_prefix')
    def _check_meat_sscc_prefix(self):
        for package_type in self.filtered('meat_sscc_prefix'):
            prefix = package_type.meat_sscc_prefix
            if not prefix.isdigit() or not 6 <= len(prefix) <= 12:
                raise ValidationError(self.env._("A GS1 company prefix has from 6 to 12 digits."))

    def _get_next_name_by_sequence(self):
        if len(self) == 1 and self.meat_sscc_prefix:
            serial = self.env['ir.sequence'].next_by_code('meat.package.sscc')
            sscc = serial and gs1_sscc(self.meat_sscc_prefix, int(serial))
            if sscc:
                return sscc
        return super()._get_next_name_by_sequence()


class StockPackage(models.Model):
    _inherit = 'stock.package'

    meat_piece = fields.Boolean('Whole Piece', readonly=True, help="Package of a single piece, weighed when cut.")

    def _get_meat_box(self):
        """ Outermost container of the package, planned or current. """
        self.ensure_one()
        package = self
        while package.package_dest_id or package.parent_package_id:
            package = package.package_dest_id or package.parent_package_id
        return package

    def _get_meat_box_move_lines(self):
        """ Move lines of the last transfer that put products in the package,
        directly or through the packages it contains (the pieces of the box):
        before the validation they are only planned in it, afterwards the
        products have left the stock (no quants to read at the customer). """
        self.ensure_one()
        children_by_dest, _dummy = self._get_all_children_package_dest_ids()
        package_ids = {self.id, *children_by_dest[self]}
        package_ids.update(self.search([('id', 'child_of', self.id)]).ids)
        move_lines = self.env['stock.move.line'].search([
            ('result_package_id', 'in', list(package_ids)),
            ('state', '!=', 'cancel'),
            ('picking_id', '!=', False),
            ('quantity', '>', 0),
        ], order='id desc')
        picking = move_lines[:1].picking_id
        return move_lines.filtered(lambda ml: ml.picking_id == picking)

    def _get_meat_box_label_values(self):
        """ Contents of the box: one row per product and lot, with its pieces,
        weight and expiration date, and the totals of the box. """
        self.ensure_one()
        move_lines = self._get_meat_box_move_lines()
        kg = self.env.ref('uom.product_uom_kgm')
        rows = defaultdict(lambda: {'quantity': 0.0, 'packages': self.browse()})
        for move_line in move_lines:
            row = rows[move_line.product_id, move_line.lot_id]
            row['quantity'] += move_line.uom_id._compute_quantity(
                move_line.quantity, move_line.product_id.uom_id, round=False)
            if move_line.product_id.meat_piece and move_line.result_package_id != self:
                row['packages'] |= move_line.result_package_id
        lines = []
        for (product, lot), row in rows.items():
            lines.append({
                'product': product,
                'lot': lot,
                'crotal': lot.crotal_id,
                'quantity': row['quantity'],
                'uom': product.uom_id,
                'pieces': len(row['packages']),
                'expiration_date': lot.expiration_date and fields.Datetime.context_timestamp(
                    self, lot.expiration_date).date(),
            })
        lines.sort(key=lambda line: (line['product'].display_name, line['lot'].name or ''))
        weighed = [line for line in lines if line['uom']._has_common_reference(kg)]
        lots = move_lines.lot_id
        picking = move_lines.picking_id
        return {
            'picking': picking,
            'partner': picking.partner_id,
            'origin': picking.origin or '',
            'lines': lines,
            'net_weight': sum(line['uom']._compute_quantity(line['quantity'], kg, round=False) for line in weighed),
            'pieces': sum(line['pieces'] for line in lines),
            # Only when all its meat comes from halal slaughtered animals
            'halal': bool(lots) and all(lot.crotal_id.halal for lot in lots),
            'expiration_date': min((line['expiration_date'] for line in lines if line['expiration_date']), default=False),
        }

    def _get_meat_box_gs1_parts(self):
        """ (00) SSCC of the box when its name is one, (13) packaging date. """
        self.ensure_one()
        if not self.valid_sscc:
            return []
        parts = [('00', self.name)]
        if self.pack_date:
            parts.append(('13', self.pack_date.strftime('%y%m%d')))
        return parts

    def _get_meat_box_barcode_value(self):
        self.ensure_one()
        parts = self._get_meat_box_gs1_parts()
        return gs1_barcode_value(parts) if parts else self.name

    def _get_meat_box_barcode_text(self):
        self.ensure_one()
        parts = self._get_meat_box_gs1_parts()
        return gs1_barcode_text(parts) if parts else self.name
