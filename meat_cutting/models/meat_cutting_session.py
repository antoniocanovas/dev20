from collections import defaultdict

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain


class MeatCuttingSession(models.Model):
    _name = 'meat.cutting.session'
    _description = "Meat Cutting Session"
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char('Reference', required=True, copy=False, readonly=True, default=lambda self: self.env._('New'))
    company_id = fields.Many2one('res.company', required=True, index=True, default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', 'Operator', default=lambda self: self.env.user)
    date = fields.Datetime(default=fields.Datetime.now, required=True)
    state = fields.Selection([
        ('draft', 'In Progress'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], default='draft', required=True, tracking=True)
    picking_id = fields.Many2one(
        'stock.picking', 'Receipt', check_company=True,
        domain="[('picking_type_code', '=', 'incoming'), ('state', '=', 'done')]")
    product_id = fields.Many2one(
        'product.product', 'Source Product', required=True, check_company=True)
    lot_id = fields.Many2one(
        'stock.lot', 'Lot', check_company=True,
        domain="[('product_id', '=', product_id)]")
    tracking = fields.Selection(related='product_id.tracking')
    crotal_id = fields.Many2one(related='lot_id.crotal_id')
    bom_id = fields.Many2one(
        'mrp.bom', 'Bill of Materials', required=True, check_company=True,
        domain="[('type', '=', 'normal'), '|', ('product_id', '=', product_id), "
               "'&', ('product_id', '=', False), ('product_tmpl_id.product_variant_ids', '=', product_id)]")
    location_id = fields.Many2one(
        'stock.location', 'Source Location', required=True, check_company=True,
        domain="[('usage', '=', 'internal')]")
    location_dest_id = fields.Many2one(
        'stock.location', 'Destination Location', required=True, check_company=True,
        domain="[('usage', '=', 'internal')]")
    uom_id = fields.Many2one(related='product_id.uom_id')
    output_lot_name = fields.Char('Cuts Lot', compute='_compute_output_lot_name')
    line_ids = fields.One2many('meat.cutting.line', 'session_id', 'Cuts')
    total_weight = fields.Float('Total Weight', digits='Product Unit', compute='_compute_total_weight')
    consumed_qty = fields.Float(
        'Consumed Quantity', digits='Product Unit', copy=False, readonly=True,
        help="Quantity of the source product consumed when the session was validated.")
    unbuild_id = fields.Many2one('mrp.unbuild', 'Unbuild Order', readonly=True, copy=False)
    freeze = fields.Boolean(
        'Freeze', help="Default of the new cuts: produce their frozen product instead of the fresh one.")
    label_report_id = fields.Many2one(
        'ir.actions.report', 'Label Format', domain=[('model', '=', 'meat.cutting.line')],
        default=lambda self: self._default_label_report())

    @api.model
    def _default_label_report(self):
        """ The format last used by the operator (the printer keeps its labels
        roll between cuttings), else the standard label. """
        last_session = self.search([
            ('user_id', '=', self.env.uid),
            ('label_report_id', '!=', False),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        return last_session.label_report_id or self.env.ref(
            'meat_cutting.action_report_meat_cutting_label', raise_if_not_found=False)

    @api.depends('lot_id.name', 'name')
    def _compute_output_lot_name(self):
        for session in self:
            session.output_lot_name = session.lot_id.name or session.name

    @api.depends('line_ids.weight')
    def _compute_total_weight(self):
        for session in self:
            session.total_weight = sum(session.line_ids.mapped('weight'))

    @api.constrains('state', 'lot_id')
    def _check_single_draft_per_lot(self):
        for session in self.filtered(lambda s: s.state == 'draft' and s.lot_id):
            other = self.search([
                ('id', '!=', session.id),
                ('state', '=', 'draft'),
                ('lot_id', '=', session.lot_id.id),
            ], limit=1)
            if other:
                raise ValidationError(self.env._(
                    "Lot %(lot)s is already being cut in %(session)s.", lot=session.lot_id.name, session=other.name))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == self.env._('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('meat.cutting.session') or self.env._('New')
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_done(self):
        if 'done' in self.mapped('state'):
            raise UserError(self.env._("You cannot delete a validated cutting session."))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_open_cutting_screen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'meat_cutting_screen',
            'name': self.name,
            'context': {'meat_cutting_session_id': self.id},
        }

    def action_view_unbuild(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.unbuild',
            'res_id': self.unbuild_id.id,
            'view_mode': 'form',
        }

    def action_cancel(self):
        if 'done' in self.mapped('state'):
            raise UserError(self.env._("You cannot cancel a validated cutting session."))
        self.write({'state': 'cancel'})

    def action_validate(self):
        """ Create the lots of the cuts (linked to the crotal of the source
        lot), then consume the whole source lot and produce the weighed cuts
        through an unbuild order. Returns the screen values. """
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(self.env._("Only cutting sessions in progress can be validated."))
        if not self.line_ids:
            raise UserError(self.env._("Weigh at least one cut before validating."))
        if self.tracking != 'none' and not self.lot_id:
            raise UserError(self.env._("Select the lot of %s before validating.", self.product_id.display_name))
        qty = self._get_default_consumed_qty()
        if self.uom_id.compare(qty, 0) <= 0:
            raise UserError(self.env._(
                "There is no stock of %(product)s left in %(location)s.",
                product=self.product_id.display_name, location=self.location_id.display_name,
            ))
        self._ensure_crotal()
        lot_by_product = self._create_output_lots()
        unbuild = self.env['mrp.unbuild'].create(self._prepare_unbuild_vals(qty))
        unbuild._action_unbuild_cutting(lot_by_product)
        self.write({'consumed_qty': qty, 'unbuild_id': unbuild.id, 'state': 'done'})
        return self.get_cutting_screen_data()

    def action_add_line(self, bom_line_id, weight):
        """ Register a weighed cut from the tablet screen. """
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(self.env._("This cutting session is already closed."))
        bom_line = self.env['mrp.bom.line'].browse(bom_line_id).exists()
        if not bom_line or bom_line.bom_id != self.bom_id:
            raise UserError(self.env._("This cut does not belong to the bill of materials of the session."))
        if bom_line.uom_id.compare(weight or 0, 0) <= 0:
            raise UserError(self.env._("Enter a weight greater than zero."))
        # A cut can be weighed several times: each weighing of a cut sold as
        # whole pieces is one piece, in its own package from the start so its
        # label already identifies it
        product = bom_line.product_id
        line = self.env['meat.cutting.line'].create({
            'session_id': self.id,
            'bom_line_id': bom_line.id,
            'product_id': product.id,
            'freeze': self.freeze and bool(product.frozen_product_id),
            'weight': weight,
            'package_id': product.meat_piece and self.env['stock.package'].create(
                self._prepare_piece_package_vals()).id,
        })
        return line.id

    def action_set_freeze(self, freeze):
        """ Default of the cuts weighed from now on. """
        self.ensure_one()
        self.freeze = freeze
        return True

    def action_set_label_report(self, report_id):
        self.ensure_one()
        report = self.env['ir.actions.report'].browse(report_id).exists()
        if not report or report.model != 'meat.cutting.line':
            raise UserError(self.env._("This report is not a label format of the cuts."))
        self.label_report_id = report
        return True

    # ------------------------------------------------------------------
    # Tablet screen
    # ------------------------------------------------------------------

    @api.model
    def get_cutting_pickings(self):
        """ Done receipts whose lots still have stock of a product with a BoM,
        i.e. receipts that were not fully cut yet. """
        lots = self._get_cutting_quants().lot_id
        if not lots:
            return []
        move_lines = self.env['stock.move.line'].search([
            ('lot_id', 'in', lots.ids),
            ('picking_code', '=', 'incoming'),
            ('state', '=', 'done'),
        ])
        lines_by_picking = move_lines.grouped('picking_id')
        pickings = move_lines.picking_id.sorted(lambda p: p.date_done or p.create_date, reverse=True)
        return [{
            'id': picking.id,
            'name': picking.name,
            'partner_name': picking.partner_id.display_name or '',
            'date': fields.Datetime.to_string(picking.date_done),
            # Products, lots and crotals still to cut, for the search of the screen
            'search_terms': [
                term for line in lines_by_picking[picking]
                for term in (line.product_id.display_name, line.lot_id.name, line.lot_id.crotal_id.name)
                if term
            ],
        } for picking in pickings]

    @api.model
    def get_cutting_products(self, picking_id=False):
        """ Products that can be cut: in stock and with a BoM. When a receipt is
        given, only its products and lots are proposed. """
        picking = self.env['stock.picking'].browse(picking_id)
        quants = self._get_cutting_quants(picking)
        qty_by_product = defaultdict(float)
        qty_by_lot = defaultdict(float)
        for quant in quants:
            available = quant.quantity - quant.reserved_quantity
            qty_by_product[quant.product_id] += available
            if quant.lot_id:
                qty_by_lot[quant.product_id, quant.lot_id] += available
        result = []
        for product in quants.product_id.sorted('display_name'):
            if product.uom_id.compare(qty_by_product[product], 0) <= 0:
                continue
            lots = [
                {'id': lot.id, 'name': lot.name, 'crotal_name': lot.crotal_id.name or '', 'qty': qty}
                for (lot_product, lot), qty in qty_by_lot.items()
                if lot_product == product and product.uom_id.compare(qty, 0) > 0
            ]
            result.append({
                'id': product.id,
                'name': product.display_name,
                'tracking': product.tracking,
                'boms': [{
                    'id': bom.id,
                    'name': bom.code or bom.product_tmpl_id.name,
                    'cut_count': len(bom.bom_line_ids.filtered(lambda bl: not bl._skip_bom_line(product))),
                } for bom in self._get_cutting_boms(product)],
                'uom_name': product.uom_id.name,
                'qty': qty_by_product[product],
                'lots': sorted(lots, key=lambda lot: lot['name']),
            })
        return result

    @api.model
    def start_cutting_session(self, product_id, lot_id=False, picking_id=False, bom_id=False):
        """ Resume the draft session of this product/lot/receipt or open a new
        one, cut with the given BoM (cutting method) or else the default one.
        Returns the session id. """
        product = self.env['product.product'].browse(product_id)
        lot = self.env['stock.lot'].browse(lot_id)
        if product.tracking != 'none' and not lot:
            raise UserError(self.env._("Select the lot of %s.", product.display_name))
        boms = self._get_cutting_boms(product)
        if bom_id and bom_id not in boms.ids:
            raise UserError(self.env._("This bill of materials does not cut %s.", product.display_name))
        bom = self.env['mrp.bom'].browse(bom_id)
        domain = Domain([
            ('state', '=', 'draft'),
            ('product_id', '=', product.id),
            ('lot_id', '=', lot.id),
            ('company_id', '=', self.env.company.id),
        ])
        if not lot:
            domain &= Domain('picking_id', '=', picking_id)
        # A lot is one animal: its session is resumed whatever the receipt
        # chosen (or not) on the screen
        session = self.search(domain, limit=1)
        if session:
            if picking_id and not session.picking_id:
                session.picking_id = picking_id
            if bom and session.bom_id != bom:
                # A lot is one animal: it is cut once, with a single method
                if session.line_ids:
                    raise UserError(self.env._(
                        "%(session)s is already cutting this lot with %(bom)s. Delete its weighed cuts "
                        "to change the cutting method.",
                        session=session.name, bom=session.bom_id.code or session.bom_id.display_name,
                    ))
                session.bom_id = bom
            return session.id
        bom = bom or self.env['mrp.bom']._bom_find(product, company_id=self.env.company.id, bom_type='normal')[product]
        if not bom:
            raise UserError(self.env._("%s has no bill of materials to cut it into pieces.", product.display_name))
        location = self._get_cutting_source_location(product, lot)
        return self.create({
            'product_id': product.id,
            'lot_id': lot.id,
            'picking_id': picking_id,
            'bom_id': bom.id,
            'location_id': location.id,
            'location_dest_id': location.id,
        }).id

    def get_cutting_screen_data(self):
        self.ensure_one()
        bom_lines = self.bom_id.bom_line_ids.filtered(lambda bl: not bl._skip_bom_line(self.product_id))
        lines_by_bom_line = self.line_ids.grouped('bom_line_id')
        lines_by_bom_line = defaultdict(lambda: self.env['meat.cutting.line'], lines_by_bom_line)
        crotal = self.crotal_id
        return {
            'id': self.id,
            'name': self.name,
            'state': self.state,
            'product_name': self.product_id.display_name,
            'bom_name': self.bom_id.code or self.bom_id.product_tmpl_id.name,
            'lot_name': self.lot_id.name or '',
            'picking_name': self.picking_id.name or '',
            'crotal': crotal and {
                'name': crotal.name,
                'breed': crotal.breed or '',
                'sex': dict(crotal._fields['sex']._description_selection(self.env)).get(crotal.sex, ''),
                'slaughter_date': fields.Date.to_string(crotal.slaughter_date) or '',
                'birth_country': crotal.birth_country or '',
                'reared_country': crotal.reared_country or '',
                'halal': crotal.halal,
            },
            'uom_name': self.uom_id.name,
            'available_qty': self.env['stock.quant']._get_available_quantity(
                self.product_id, self.location_id, lot_id=self.lot_id or None, strict=True),
            'consumed_qty': self.consumed_qty if self.state == 'done' else self._get_default_consumed_qty(),
            'total_weight': self.total_weight,
            'components': [{
                'bom_line_id': bom_line.id,
                'product_id': bom_line.product_id.id,
                'name': bom_line.product_id.display_name,
                'uom_name': bom_line.uom_id.name,
                'piece': bom_line.product_id.meat_piece,
                'weighed_count': len(lines_by_bom_line[bom_line]),
                'weighed_qty': sum(lines_by_bom_line[bom_line].mapped('weight')),
            } for bom_line in bom_lines],
            'lines': self.line_ids._get_cutting_screen_values(),
            'freeze': self.freeze,
            'can_freeze': bool(bom_lines.product_id.frozen_product_id),
            'label_report_id': self.label_report_id.id,
            'label_formats': self._get_label_formats(),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @api.model
    def _get_cutting_boms(self, product):
        """ BoMs that cut the product, one per cutting method. """
        return self.env['mrp.bom'].search([
            ('type', '=', 'normal'),
            ('company_id', 'in', [self.env.company.id, False]),
            '|', ('product_id', '=', product.id),
            '&', ('product_id', '=', False), ('product_tmpl_id', '=', product.product_tmpl_id.id),
        ], order='sequence, product_id, id')

    @api.model
    def _get_label_formats(self):
        reports = self.env['ir.actions.report'].search([('model', '=', 'meat.cutting.line')], order='name, id')
        return [{
            'id': report.id,
            'name': report.name,
            'paper': report.paperformat_id.name or '',
        } for report in reports]

    @api.model
    def _get_cutting_quants(self, picking=None):
        domain = Domain([
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0),
            ('company_id', '=', self.env.company.id),
        ])
        if picking:
            lots = picking.move_line_ids.lot_id
            if lots:
                domain &= Domain('lot_id', 'in', lots.ids)
            else:
                domain &= Domain('product_id', 'in', picking.move_ids.product_id.ids)
        quants = self.env['stock.quant'].search(domain)
        bom_by_product = self.env['mrp.bom']._bom_find(
            quants.product_id, company_id=self.env.company.id, bom_type='normal')
        return quants.filtered(lambda q: bom_by_product[q.product_id])

    @api.model
    def _get_cutting_source_location(self, product, lot):
        """ Internal location holding most of the product (or lot) stock. """
        domain = Domain([
            ('product_id', '=', product.id),
            ('location_id.usage', '=', 'internal'),
            ('company_id', '=', self.env.company.id),
        ])
        if lot:
            domain &= Domain('lot_id', '=', lot.id)
        groups = self.env['stock.quant']._read_group(
            domain, ['location_id'], ['quantity:sum'], order='quantity:sum desc', limit=1)
        if groups:
            return groups[0][0]
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        return warehouse.lot_stock_id

    def _get_default_consumed_qty(self):
        """ A source lot is one animal (crotal): it is consumed entirely, the
        difference with the weighed cuts being the cutting loss. Without lot,
        the weighed quantity is consumed when the units match, else one unit. """
        self.ensure_one()
        if self.lot_id:
            return self.env['stock.quant']._get_available_quantity(
                self.product_id, self.location_id, lot_id=self.lot_id, strict=True)
        if self.line_ids and all(line.uom_id == self.uom_id for line in self.line_ids):
            return self.uom_id.round(self.total_weight)
        return 1.0

    def _ensure_crotal(self):
        """ The source lot must carry its crotal so the cuts inherit it; when
        the receipt did not set one, it is created from the lot. """
        self.ensure_one()
        if not self.lot_id or self.lot_id.crotal_id:
            return
        crotal = self.env['stock.crotal'].search([
            ('name', '=', self.lot_id.name),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        self.lot_id.crotal_id = crotal or self.env['stock.crotal'].create({
            'name': self.lot_id.name,
            'product_id': self.product_id.id,
            'partner_id': self.picking_id.partner_id.id,
            'company_id': self.company_id.id,
        })

    def _create_output_lots(self):
        """ One lot per tracked cut, named after the source lot and linked to
        its crotal. Returns a dict {product: lot}. """
        self.ensure_one()
        products = self.line_ids.output_product_id.filtered(lambda p: p.tracking != 'none')
        if not products:
            return {}
        Lot = self.env['stock.lot']
        existing_lots = Lot.search([
            ('product_id', 'in', products.ids),
            ('name', '=', self.output_lot_name),
            ('company_id', 'in', [self.company_id.id, False]),
        ])
        lot_by_product = {lot.product_id: lot for lot in existing_lots}
        crotal = self.lot_id.crotal_id
        existing_lots.filtered(lambda lot: not lot.crotal_id).crotal_id = crotal
        new_lots = Lot.create([
            self._prepare_output_lot_vals(product, crotal)
            for product in products if product not in lot_by_product
        ])
        lot_by_product.update({lot.product_id: lot for lot in new_lots})
        return lot_by_product

    def _prepare_output_lot_vals(self, product, crotal):
        vals = {
            'product_id': product.id,
            'name': self.output_lot_name,
            'company_id': self.company_id.id,
            'crotal_id': crotal.id,
        }
        if product.use_expiration_date:
            # From the weighing, not the validation: the same date as the label
            lines = self.line_ids.filtered(lambda l: l.output_product_id == product)
            vals['expiration_date'] = min(line._get_default_expiration_date() for line in lines)
        return vals

    def _prepare_piece_package_vals(self):
        self.ensure_one()
        return {'meat_piece': True}

    def _prepare_unbuild_vals(self, qty):
        self.ensure_one()
        return {
            'product_id': self.product_id.id,
            'bom_id': self.bom_id.id,
            'product_qty': qty,
            'uom_id': self.uom_id.id,
            'lot_ids': [Command.set(self.lot_id.ids)],
            'location_id': self.location_id.id,
            'location_dest_id': self.location_dest_id.id,
            'company_id': self.company_id.id,
            'cutting_session_id': self.id,
        }
