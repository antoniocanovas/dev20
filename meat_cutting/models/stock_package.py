from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..tools import gs1_barcode_text, gs1_barcode_value, gs1_parse, gs1_sscc
from .meat_cutting_line import LABEL_KEYS


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
    meat_presentation_id = fields.Many2one(
        'product.attribute.value', 'Presentation', help="How the product of the package was prepared.")
    # Texts of the piece label edited before reprinting it (stored as meat_label_<key>)
    meat_label_custom = fields.Boolean('Edited Label', copy=False)
    meat_label_product_name = fields.Char('Label Product', copy=False)
    meat_label_birth_country = fields.Char('Label Born In', copy=False)
    meat_label_reared_country = fields.Char('Label Reared In', copy=False)
    meat_label_slaughter_date = fields.Date('Label Slaughter Date', copy=False)
    meat_label_origin = fields.Char('Label Origin', copy=False)
    meat_label_supplier = fields.Char('Label Supplier', copy=False)
    meat_label_note = fields.Char('Label Note', copy=False)
    # Texts of the box label edited before reprinting it
    meat_box_label_custom = fields.Boolean('Edited Box Label', copy=False)
    meat_box_label_partner_name = fields.Char('Box Label Customer', copy=False)
    meat_box_label_note = fields.Char('Box Label Note', copy=False)

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
            presentation = move_line.result_package_id.meat_presentation_id if move_line.result_package_id != self \
                else self.env['product.attribute.value']
            row = rows[move_line.product_id, move_line.lot_id, presentation]
            row['quantity'] += move_line.uom_id._compute_quantity(
                move_line.quantity, move_line.product_id.uom_id, round=False)
            if move_line.product_id.meat_piece and move_line.result_package_id != self:
                row['packages'] |= move_line.result_package_id
        lines = []
        for (product, lot, presentation), row in rows.items():
            lines.append({
                'product': product,
                'presentation': presentation,
                'lot': lot,
                'crotal': lot.crotal_id,
                'quantity': row['quantity'],
                'uom': product.uom_id,
                'pieces': len(row['packages']),
                'expiration_date': lot.expiration_date and fields.Datetime.context_timestamp(
                    self, lot.expiration_date).date(),
            })
        lines.sort(key=lambda line: (line['product'].display_name, line['presentation'].name or '', line['lot'].name or ''))
        weighed = [line for line in lines if line['uom']._has_common_reference(kg)]
        lots = move_lines.lot_id
        picking = move_lines.picking_id
        partner_name = picking.partner_id.name or ''
        note = ''
        if self.meat_box_label_custom:
            partner_name = self.meat_box_label_partner_name or ''
            note = self.meat_box_label_note or ''
        return {
            'picking': picking,
            'partner': picking.partner_id,
            'partner_name': partner_name,
            'note': note,
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

    # ------------------------------------------------------------------
    # Reprint of a damaged label from the factory screen
    # ------------------------------------------------------------------

    def _get_meat_stock_quants(self):
        self.ensure_one()
        return self.quant_ids.filtered(lambda q: q.location_id.usage == 'internal' and q.quantity > 0)

    def _get_meat_child_packages(self):
        """ Packages in the box, planned or current. """
        self.ensure_one()
        return self.search(['|', ('package_dest_id', '=', self.id), ('parent_package_id', '=', self.id)])

    def _get_meat_cutting_line(self):
        """ Weighing that made the package, while its stock is still the one
        weighed: its cut label can be printed again as it was. """
        self.ensure_one()
        line = self.env['meat.cutting.line'].search([('package_id', '=', self.id)], order='id desc', limit=1)
        quants = self._get_meat_stock_quants()
        product = line.output_product_id
        if not line or quants.product_id != product or set(quants.lot_id.mapped('name')) != {line.lot_name}:
            return self.env['meat.cutting.line']
        if product.uom_id.compare(sum(quants.mapped('quantity')), line.weight):
            return self.env['meat.cutting.line']
        return line

    @api.model
    def meat_relabel_search(self, text):
        """ Packages (pieces in stock) and boxes found by a scan of their label
        (GS1 or plain) or by a text typed: package, lot, crotal or product. """
        text = (text or '').strip()
        if not text:
            return []
        Quant = self.env['stock.quant']
        stock_domain = [('location_id.usage', '=', 'internal'), ('package_id', '!=', False), ('quantity', '>', 0)]
        gs1 = gs1_parse(text)
        if gs1:
            packages = self.search([('name', '=', gs1['00'])]) if '00' in gs1 else self.browse()
            quants = Quant.search(stock_domain + [('lot_id.name', '=', gs1['10'])]) if '10' in gs1 else Quant
            weight = next((value for ai, value in gs1.items() if ai.startswith('310')), None)
            if weight:
                # The piece of the scanned label among those of its lot
                kg = int(weight) / 10 ** int(next(ai for ai in gs1 if ai.startswith('310'))[3])
                same_weight = quants.filtered(lambda q: q.product_id.uom_id.compare(q.quantity, kg) == 0)
                quants = same_weight or quants
        else:
            packages = self.search([('name', 'ilike', text)], limit=40)
            quants = Quant.search(stock_domain + ['|', '|', '|',
                ('package_id.name', 'ilike', text),
                ('lot_id.name', 'ilike', text),
                ('lot_id.crotal_id.name', 'ilike', text),
                ('product_id.name', 'ilike', text),
            ], limit=200)
        packages = (packages | quants.package_id)[:40]
        return [package._get_meat_relabel_summary() for package in packages]

    def _get_meat_relabel_summary(self):
        self.ensure_one()
        quants = self._get_meat_stock_quants()
        is_box = bool(self._get_meat_child_packages())
        box_values = self._get_meat_box_label_values() if is_box else {}
        products = quants.product_id
        lots = quants.lot_id
        return {
            'id': self.id,
            'name': self.name,
            'is_box': is_box,
            'product_name': products.with_context(display_default_code=False).display_name
            if len(products) == 1 else '',
            'product_count': len(products),
            'lot_name': lots.name if len(lots) == 1 else '',
            'qty': sum(quants.mapped('quantity')) if len(products) == 1 else 0,
            'uom_name': products.uom_id.name if len(products) == 1 else '',
            'expiration_date': fields.Datetime.to_string(min(lots.filtered('expiration_date').mapped(
                'expiration_date'), default=False)) or '',
            'partner_name': box_values.get('partner') and box_values['partner'].name or '',
            'picking_name': box_values.get('picking') and box_values['picking'].name or '',
            'pieces': box_values.get('pieces', 0),
            'in_stock': bool(quants),
        }

    def get_meat_relabel_data(self):
        """ The package and the labels that can be printed again for it: the
        cut label as weighed (in each format), the label of its stock, and the
        label of its box. """
        self.ensure_one()
        formats = []
        line = self._get_meat_cutting_line()
        if line:
            reports = self.env['ir.actions.report'].search([('model', '=', 'meat.cutting.line')], order='name, id')
            # The format of its cutting first
            reports = line.session_id.label_report_id | reports
            formats += [{
                'key': f'line-{report.id}',
                'name': report.name,
                'paper': report.paperformat_id.name or '',
                'kind': 'line',
                'report_id': report.id,
                'model': 'meat.cutting.line',
                'res_ids': line.ids,
                'edit_model': 'meat.cutting.line',
                'edit_id': line.id,
            } for report in reports]
        quants = self._get_meat_stock_quants()
        if quants:
            report = self.env.ref('meat_cutting.action_report_meat_piece_label')
            formats.append({
                'key': 'stock',
                'name': report.name,
                'paper': report.paperformat_id.name or '',
                'kind': 'stock',
                'report_id': report.id,
                'model': 'stock.quant',
                'res_ids': quants.ids,
                'edit_model': 'stock.package',
                'edit_id': self.id,
            })
        # The box itself, or the box the piece is in
        box = self if self._get_meat_child_packages() else self._get_meat_box()
        if (box != self or box._get_meat_child_packages()) and box._get_meat_box_move_lines():
            report = self.env.ref('meat_cutting.action_report_meat_box_label')
            formats.append({
                'key': 'box',
                'name': report.name if box == self else f'{report.name} ({box.name})',
                'paper': report.paperformat_id.name or '',
                'kind': 'box',
                'report_id': report.id,
                'model': 'stock.package',
                'res_ids': box.ids,
                'edit_model': 'stock.package',
                'edit_id': box.id,
                'edit_kind': 'box',
            })
        return dict(self._get_meat_relabel_summary(), formats=formats)

    def _get_meat_label_quant(self):
        self.ensure_one()
        quant = self._get_meat_stock_quants()[:1]
        if not quant:
            raise UserError(self.env._("Package %s has no stock to label.", self.name))
        return quant

    def get_label_data(self):
        """ Values of the label edition dialog of the tablet screen, for the
        label of the stock of the package, or for its box label (context key
        meat_label_kind = 'box'). """
        self.ensure_one()
        if self.env.context.get('meat_label_kind') == 'box':
            return self._get_meat_box_label_data()
        quant = self._get_meat_label_quant()

        def to_json(values):
            values = {key: values[key] for key in LABEL_KEYS}
            return dict(values, slaughter_date=fields.Date.to_string(values['slaughter_date']) or '')

        defaults = quant._get_meat_label_default_values()
        return {
            'custom': self.meat_label_custom,
            'values': to_json(quant._get_meat_label_values()),
            'defaults': to_json(defaults),
            'lot_name': defaults['lot_name'],
            'package_name': self.name,
            'crotal_name': defaults['crotal'].name or '',
            'weight': sum(self._get_meat_stock_quants().mapped('quantity')),
            'uom_name': defaults['uom'].name,
        }

    def _get_meat_box_label_data(self):
        picking = self._get_meat_box_move_lines().picking_id
        defaults = {'partner_name': picking.partner_id.name or '', 'note': ''}
        values = defaults
        if self.meat_box_label_custom:
            values = {'partner_name': self.meat_box_label_partner_name or '', 'note': self.meat_box_label_note or ''}
        return {
            'custom': self.meat_box_label_custom,
            'values': values,
            'defaults': defaults,
            'lot_name': '',
            'package_name': self.name,
            'crotal_name': '',
            'weight': self._get_meat_box_label_values()['net_weight'],
            'uom_name': self.env.ref('uom.product_uom_kgm').name,
        }

    def action_save_label(self, values):
        self.ensure_one()
        if self.env.context.get('meat_label_kind') == 'box':
            self.write({
                'meat_box_label_custom': True,
                'meat_box_label_partner_name': values.get('partner_name') or False,
                'meat_box_label_note': values.get('note') or False,
            })
            return True
        self.write({
            'meat_label_custom': True,
            **{f'meat_label_{key}': values.get(key) or False for key in LABEL_KEYS},
        })
        return True

    def action_reset_label(self):
        if self.env.context.get('meat_label_kind') == 'box':
            self.write({
                'meat_box_label_custom': False,
                'meat_box_label_partner_name': False,
                'meat_box_label_note': False,
            })
            return True
        self.write({
            'meat_label_custom': False,
            **{f'meat_label_{key}': False for key in LABEL_KEYS},
        })
        return True
