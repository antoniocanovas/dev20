from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..tools import gs1_barcode_text, gs1_barcode_value, gs1_item_parts

# Texts of the label that can be edited before printing (stored as label_<key>)
LABEL_KEYS = ('product_name', 'birth_country', 'reared_country', 'slaughter_date', 'origin', 'supplier', 'note')


class MeatCuttingLine(models.Model):
    _name = 'meat.cutting.line'
    _description = "Meat Cutting Line"
    _order = 'id desc'

    session_id = fields.Many2one('meat.cutting.session', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='session_id.company_id', store=True)
    state = fields.Selection(related='session_id.state')
    bom_line_id = fields.Many2one('mrp.bom.line', 'BoM Line', ondelete='set null')
    product_id = fields.Many2one('product.product', 'Cut', required=True)
    freeze = fields.Boolean('Freeze', help="Produce the frozen product of the cut instead of the fresh one.")
    can_freeze = fields.Boolean(compute='_compute_can_freeze')
    # Only follows the line, not later changes of the product configuration
    output_product_id = fields.Many2one(
        'product.product', 'Produced Product', compute='_compute_output_product_id', store=True)
    weight = fields.Float('Weight', digits='Product Unit', required=True)
    uom_id = fields.Many2one(related='output_product_id.uom_id')
    lot_name = fields.Char(related='session_id.output_lot_name', string='Lot')
    # One package per weighed piece of the cuts sold as whole pieces
    package_id = fields.Many2one('stock.package', 'Piece', readonly=True, copy=False)
    source_product_id = fields.Many2one(related='session_id.product_id', string='Source Product')
    user_id = fields.Many2one('res.users', 'Operator', default=lambda self: self.env.user)
    date = fields.Datetime(default=fields.Datetime.now, required=True)
    # Label texts edited before printing; the crotal and the line are left untouched
    label_custom = fields.Boolean('Edited Label', copy=False)
    label_product_name = fields.Char('Label Product', copy=False)
    label_birth_country = fields.Char('Label Born In', copy=False)
    label_reared_country = fields.Char('Label Reared In', copy=False)
    label_slaughter_date = fields.Date('Label Slaughter Date', copy=False)
    label_origin = fields.Char('Label Origin', copy=False)
    label_supplier = fields.Char('Label Supplier', copy=False)
    label_note = fields.Char('Label Note', copy=False)

    _weight_positive = models.Constraint(
        'CHECK (weight > 0)',
        "The weight must be positive.",
    )

    @api.depends('product_id')
    def _compute_can_freeze(self):
        for line in self:
            line.can_freeze = bool(line.product_id.frozen_product_id)

    @api.depends('product_id', 'freeze')
    def _compute_output_product_id(self):
        for line in self:
            if line.freeze and line.product_id.frozen_product_id:
                line.output_product_id = line.product_id.frozen_product_id
            else:
                line.output_product_id = line.product_id

    @api.constrains('freeze', 'product_id')
    def _check_freeze(self):
        for line in self:
            if line.freeze and not line.product_id.frozen_product_id:
                raise ValidationError(self.env._("%s has no frozen product.", line.product_id.display_name))

    def action_set_freeze(self, freeze):
        """ Produce the frozen (or fresh) product. A label product name left
        as the default follows the new product. """
        for line in self:
            if line.session_id.state != 'draft':
                raise UserError(self.env._("This cutting session is already closed."))
            old_name = line.output_product_id.name
            line.freeze = freeze
            if line.label_custom and line.label_product_name == old_name:
                line.label_product_name = line.output_product_id.name
        return True

    @api.ondelete(at_uninstall=False)
    def _unlink_except_done(self):
        if any(line.session_id.state == 'done' for line in self):
            raise UserError(self.env._("You cannot delete lines of a validated cutting session."))

    def unlink(self):
        packages = self.package_id
        res = super().unlink()
        # The package of a deleted piece was never filled
        packages.filtered(lambda p: not p.quant_ids).unlink()
        return res

    def _get_label_default_values(self):
        """ Label texts taken from the cut, its session and the crotal. """
        self.ensure_one()
        crotal = self.session_id.crotal_id
        return {
            'product_name': self.output_product_id.name or '',
            'birth_country': crotal.birth_country or '',
            'reared_country': crotal.reared_country or '',
            'slaughter_date': crotal.slaughter_date or False,
            'origin': self.source_product_id.name or '',
            'supplier': self.session_id.picking_id.partner_id.name or '',
            'note': '',
        }

    def _get_label_values(self):
        """ Texts printed on the label: the edited ones once the label was
        edited (an emptied text is not printed), else the defaults. """
        self.ensure_one()
        if not self.label_custom:
            return self._get_label_default_values()
        return {key: self[f'label_{key}'] or False for key in LABEL_KEYS}

    def get_label_data(self):
        """ Values of the label edition dialog of the tablet screen. """
        self.ensure_one()

        def to_json(values):
            return dict(values, slaughter_date=fields.Date.to_string(values['slaughter_date']) or '')

        return {
            'custom': self.label_custom,
            'values': to_json(self._get_label_values()),
            'defaults': to_json(self._get_label_default_values()),
            # Not editable: they carry the traceability of the cut
            'lot_name': self.lot_name or '',
            'package_name': self.package_id.name or '',
            'crotal_name': self.session_id.crotal_id.name or '',
            'weight': self.weight,
            'uom_name': self.uom_id.name,
        }

    def action_save_label(self, values):
        self.ensure_one()
        self.write({
            'label_custom': True,
            **{f'label_{key}': values.get(key) or False for key in LABEL_KEYS},
        })
        return True

    def action_reset_label(self):
        self.write({
            'label_custom': False,
            **{f'label_{key}': False for key in LABEL_KEYS},
        })
        return True

    def _get_default_expiration_date(self):
        """ The shelf life of a cut starts when it is weighed. """
        self.ensure_one()
        product = self.output_product_id
        if not product.use_expiration_date:
            return False
        return self.date + timedelta(days=product.expiration_time)

    def _get_output_lot(self):
        self.ensure_one()
        if not self.lot_name:
            return self.env['stock.lot']
        return self.env['stock.lot'].search([
            ('product_id', '=', self.output_product_id.id),
            ('name', '=', self.lot_name),
            ('company_id', 'in', [self.company_id.id, False]),
        ], limit=1)

    def _get_label_dates(self):
        """ Production (cutting) and expiration dates printed on the label, in
        the user's timezone. Once the lot of the cut exists, its expiration
        date prevails (it may have been corrected on the lot). """
        self.ensure_one()
        expiration = False
        if self.output_product_id.use_expiration_date:
            expiration = self._get_output_lot().expiration_date or self._get_default_expiration_date()
        return {
            'production_date': fields.Datetime.context_timestamp(self, self.date).date(),
            'expiration_date': expiration and fields.Datetime.context_timestamp(self, expiration).date(),
        }

    def _get_label_gs1_parts(self):
        """ GS1 elements of the label, when the product has a GTIN. """
        self.ensure_one()
        is_kg = self.uom_id == self.env.ref('uom.product_uom_kgm', raise_if_not_found=False)
        return gs1_item_parts(
            self.output_product_id.barcode,
            weight_kg=self.weight if is_kg else None,
            expiration_date=self._get_label_dates()['expiration_date'],
            lot_name=self.lot_name,
        )

    def _get_label_barcode_value(self):
        """ GS1-128 data (starting with FNC1) when the product has a GTIN,
        else a plain Code 128 of the lot. """
        self.ensure_one()
        parts = self._get_label_gs1_parts()
        if parts:
            return gs1_barcode_value(parts)
        return self.lot_name or self.output_product_id.barcode or ''

    def _get_label_barcode_text(self):
        self.ensure_one()
        parts = self._get_label_gs1_parts()
        if parts:
            return gs1_barcode_text(parts)
        return self._get_label_barcode_value()

    def _get_cutting_screen_values(self):
        return [{
            'id': line.id,
            'product_name': line.output_product_id.display_name,
            'freeze': line.freeze,
            'can_freeze': line.can_freeze,
            'weight': line.weight,
            'uom_name': line.uom_id.name,
            'lot_name': line.lot_name or '',
            'package_name': line.package_id.name or '',
            'date': fields.Datetime.to_string(line.date),
            'label_custom': line.label_custom,
        } for line in self]
