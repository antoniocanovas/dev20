from collections import defaultdict
from datetime import timedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.tools import float_round


class MeatCuttingSession(models.Model):
    _name = 'meat.cutting.session'
    _description = "Meat Cutting Session"
    _inherit = ['mail.thread']
    _order = 'id desc'

    MODES = [
        ('receipt', 'Receipts'),
        ('cutting', 'Cutting'),
        ('preparation', 'Preparation'),
        ('production', 'Production'),
    ]

    name = fields.Char('Reference', required=True, copy=False, readonly=True, default=lambda self: self.env._('New'))
    company_id = fields.Many2one('res.company', required=True, index=True, default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', 'Operator', default=lambda self: self.env.user)
    date = fields.Datetime(default=fields.Datetime.now, required=True)
    state = fields.Selection([
        ('draft', 'In Progress'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], default='draft', required=True, tracking=True)
    # receipt: cut a received lot (carcass) into pieces; cutting: second cut of
    # a package in stock; preparation: split a package into packages of the
    # same product with a presentation; production: make a product with a BoM
    # from weighed ingredient packages
    mode = fields.Selection(MODES, default='receipt', required=True, readonly=True)
    picking_id = fields.Many2one(
        'stock.picking', 'Receipt', check_company=True,
        domain="[('picking_type_code', '=', 'incoming'), ('state', '=', 'done')]")
    product_id = fields.Many2one(
        'product.product', 'Product', required=True, check_company=True,
        help="Product cut or prepared, or the product made in production.")
    lot_id = fields.Many2one(
        'stock.lot', 'Lot', check_company=True,
        domain="[('product_id', '=', product_id)]")
    tracking = fields.Selection(related='product_id.tracking')
    crotal_id = fields.Many2one(related='lot_id.crotal_id')
    package_id = fields.Many2one(
        'stock.package', 'Source Package', check_company=True,
        help="Package in stock that is cut or prepared.")
    bom_id = fields.Many2one(
        'mrp.bom', 'Bill of Materials', check_company=True,
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
    consumption_ids = fields.One2many('meat.cutting.consumption', 'session_id', 'Ingredients')
    total_weight = fields.Float('Total Weight', digits='Product Unit', compute='_compute_total_weight')
    consumed_qty = fields.Float(
        'Consumed Quantity', digits='Product Unit', copy=False, readonly=True,
        help="Quantity of the source product consumed when the session was validated.")
    unbuild_id = fields.Many2one('mrp.unbuild', 'Unbuild Order', readonly=True, copy=False)
    production_id = fields.Many2one('mrp.production', 'Manufacturing Order', readonly=True, copy=False)
    freeze = fields.Boolean(
        'Freeze', help="Default of the new cuts: produce their frozen product instead of the fresh one.")
    production_qty = fields.Float(
        'Quantity to Make', digits='Product Unit',
        help="Production: quantity planned, from which the quantity of each ingredient is recommended.")
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

    @api.constrains('state', 'lot_id', 'package_id', 'mode')
    def _check_single_draft_per_lot(self):
        """ A received lot (one animal) or a package is cut or prepared in a
        single session at a time. """
        for session in self.filtered(lambda s: s.state == 'draft'):
            if session.package_id:
                domain = [('package_id', '=', session.package_id.id)]
                message = self.env._("Package %(source)s is already being cut or prepared in %(session)s.")
                source = session.package_id.name
            elif session.mode == 'receipt' and session.lot_id:
                domain = [('lot_id', '=', session.lot_id.id), ('mode', '=', 'receipt')]
                message = self.env._("Lot %(source)s is already being cut in %(session)s.")
                source = session.lot_id.name
            else:
                continue
            other = self.search([('id', '!=', session.id), ('state', '=', 'draft'), *domain], limit=1)
            if other:
                raise ValidationError(message % {'source': source, 'session': other.name})

    @api.constrains('mode', 'bom_id', 'package_id')
    def _check_mode(self):
        for session in self:
            if session.mode in ('receipt', 'cutting', 'production') and not session.bom_id:
                raise ValidationError(self.env._("%s needs a bill of materials.", session.name))
            if session.mode in ('cutting', 'preparation') and not session.package_id:
                raise ValidationError(self.env._("%s needs a source package.", session.name))

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

    def action_view_production(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.production',
            'res_id': self.production_id.id,
            'view_mode': 'form',
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
        lot), then consume the source and produce the weighed cuts through an
        unbuild order, or make the product through a manufacturing order in
        production. Returns the screen values. """
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(self.env._("Only cutting sessions in progress can be validated."))
        if not self.line_ids:
            raise UserError(self.env._("Weigh at least one cut before validating."))
        if self.mode == 'production':
            self._validate_production()
            return self.get_cutting_screen_data()
        if self.tracking != 'none' and not self.lot_id:
            raise UserError(self.env._("Select the lot of %s before validating.", self.product_id.display_name))
        qty = self._get_default_consumed_qty()
        if self.uom_id.compare(qty, 0) <= 0:
            raise UserError(self.env._(
                "There is no stock of %(product)s left in %(location)s.",
                product=self.product_id.display_name, location=self.location_id.display_name,
            ))
        if self.mode == 'preparation' and self.uom_id.compare(qty, self._get_source_available_qty()) > 0:
            raise UserError(self.env._(
                "The prepared packages weigh more than package %(package)s (%(qty)s %(uom)s).",
                package=self.package_id.name, qty=self._get_source_available_qty(), uom=self.uom_id.name,
            ))
        self._ensure_crotal()
        lot_by_product = self._create_output_lots()
        unbuild = self.env['mrp.unbuild'].create(self._prepare_unbuild_vals(qty))
        unbuild._action_unbuild_cutting(lot_by_product)
        self.write({'consumed_qty': qty, 'unbuild_id': unbuild.id, 'state': 'done'})
        return self.get_cutting_screen_data()

    def action_add_line(self, bom_line_id, weight, presentation_id=False):
        """ Register a weighed cut from the tablet screen: a cut of the BoM,
        a prepared package (with its presentation) or the product made. """
        self.ensure_one()
        self._check_draft()
        if self.mode in ('receipt', 'cutting'):
            bom_line = self.env['mrp.bom.line'].browse(bom_line_id).exists()
            if not bom_line or bom_line.bom_id != self.bom_id:
                raise UserError(self.env._("This cut does not belong to the bill of materials of the session."))
            product = bom_line.product_id
        else:
            bom_line = self.env['mrp.bom.line']
            product = self.product_id
        self._check_weight(weight, product.uom_id)
        presentation = self.env['product.attribute.value'].browse(presentation_id)
        if presentation and presentation not in self._get_presentations(product):
            raise UserError(self.env._("%s is not a presentation of this product.", presentation.name))
        # A cut can be weighed several times: each weighing of a cut sold as
        # whole pieces is one piece, in its own package from the start so its
        # label already identifies it. Prepared packages and productions are
        # always packed.
        packed = product.meat_piece or self.mode in ('preparation', 'production')
        line = self.env['meat.cutting.line'].create({
            'session_id': self.id,
            'bom_line_id': bom_line.id,
            'product_id': product.id,
            'freeze': self.freeze and bool(product.frozen_product_id),
            'weight': weight,
            'presentation_id': presentation.id,
            'package_id': packed and self.env['stock.package'].create(
                self._prepare_piece_package_vals(presentation)).id,
        })
        return line.id

    def action_add_consumption(self, product_id, weight, package_id=False, lot_id=False, location_id=False):
        """ Production: weigh what is used of an ingredient package (or lot
        out of package). Without weight, all of it is used. """
        self.ensure_one()
        self._check_draft()
        if self.mode != 'production':
            raise UserError(self.env._("Ingredients are only weighed in production."))
        product = self.env['product.product'].browse(product_id)
        if product not in self._get_bom_lines().product_id:
            raise UserError(self.env._("%s is not an ingredient of this product.", product.display_name))
        package = self.env['stock.package'].browse(package_id)
        lot = self.env['stock.lot'].browse(lot_id)
        location = self.env['stock.location'].browse(location_id) or package.location_id or self.location_id
        available = self.env['stock.quant']._get_available_quantity(
            product, location, lot_id=lot or None, package_id=package or None, strict=True)
        available -= sum(self.consumption_ids.filtered(
            lambda c: (c.product_id, c.package_id, c.lot_id, c.location_id) == (product, package, lot, location)
        ).mapped('weight'))
        weight = weight or available
        self._check_weight(weight, product.uom_id)
        if product.uom_id.compare(weight, available) > 0:
            raise UserError(self.env._(
                "Only %(qty)s %(uom)s of %(product)s are left there.",
                qty=product.uom_id.round(available), uom=product.uom_id.name, product=product.display_name,
            ))
        return self.env['meat.cutting.consumption'].create({
            'session_id': self.id,
            'product_id': product.id,
            'package_id': package.id,
            'lot_id': lot.id,
            'location_id': location.id,
            'weight': weight,
        }).id

    def action_set_freeze(self, freeze):
        """ Default of the cuts weighed from now on. """
        self.ensure_one()
        self.freeze = freeze
        return True

    def action_set_production_qty(self, qty):
        """ Production: quantity to make, to recommend the ingredients. """
        self.ensure_one()
        self._check_draft()
        if self.mode != 'production':
            raise UserError(self.env._("The quantity to make is only set in production."))
        self._check_weight(qty, self.uom_id)
        self.production_qty = qty
        return True

    def _check_draft(self):
        if self.state != 'draft':
            raise UserError(self.env._("This cutting session is already closed."))

    @api.model
    def _check_weight(self, weight, uom):
        if uom.compare(weight or 0, 0) <= 0:
            raise UserError(self.env._("Enter a weight greater than zero."))

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
            ('mode', '=', 'receipt'),
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
        bom = bom or boms[:1]
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

    @api.model
    def get_cutting_families(self, mode):
        """ Product categories (families) with something to cut, prepare or
        make in this mode, with how many. """
        if mode == 'production':
            products = self._get_production_products()
        else:
            products = self._get_package_quants(mode).product_id
        counts = defaultdict(int)
        for product in products:
            counts[product.categ_id] += 1
        return [{
            'id': category.id,
            'name': category.name,
            'path': category.parent_id.complete_name or '',
            'count': counts[category],
        } for category in sorted(counts, key=lambda c: c.complete_name)]

    @api.model
    def get_cutting_packages(self, mode, category_id):
        """ Packages in stock of the family that can be cut (with a BoM) or
        prepared, the oldest expiration first. """
        quants = self._get_package_quants(mode).filtered(lambda q: q.product_id.categ_id.id == category_id)
        return self._get_package_values(quants, with_boms=mode == 'cutting')

    @api.model
    def get_production_products(self, category_id):
        """ Products of the family made from a BoM, with their BoMs. """
        products = self._get_production_products().filtered(lambda p: p.categ_id.id == category_id)
        return [{
            'id': product.id,
            'name': product.display_name,
            'uom_name': product.uom_id.name,
            'boms': [{
                'id': bom.id,
                'name': bom.code or bom.product_tmpl_id.name,
                'cut_count': len(bom.bom_line_ids.filtered(lambda bl: not bl._skip_bom_line(product))),
            } for bom in self._get_cutting_boms(product, 'production')],
        } for product in products.sorted('display_name')]

    @api.model
    def start_package_session(self, mode, package_id, product_id, bom_id=False):
        """ Resume the draft session of the package or open a new one, to cut
        it (second cut, with the given BoM or else the default one) or to
        prepare it. Returns the session id. """
        if mode not in ('cutting', 'preparation'):
            raise UserError(self.env._("Only packages are cut or prepared."))
        package = self.env['stock.package'].browse(package_id)
        product = self.env['product.product'].browse(product_id)
        quants = package.quant_ids.filtered(lambda q: q.product_id == product)
        if not quants:
            raise UserError(self.env._("Package %(package)s has no %(product)s.",
                                       package=package.name, product=product.display_name))
        session = self.search([
            ('state', '=', 'draft'),
            ('package_id', '=', package.id),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if session:
            if session.mode != mode:
                raise UserError(self.env._(
                    "Package %(package)s is already open in %(session)s.", package=package.name, session=session.name))
            if bom_id and session.bom_id.id != bom_id:
                if session.line_ids:
                    raise UserError(self.env._(
                        "%(session)s is already cutting this package with %(bom)s. Delete its weighed cuts "
                        "to change the cutting method.",
                        session=session.name, bom=session.bom_id.code or session.bom_id.display_name,
                    ))
                session.bom_id = bom_id
            return session.id
        bom = self.env['mrp.bom']
        if mode == 'cutting':
            boms = self._get_cutting_boms(product)
            if bom_id and bom_id not in boms.ids:
                raise UserError(self.env._("This bill of materials does not cut %s.", product.display_name))
            bom = boms.browse(bom_id) or boms[:1]
            if not bom:
                raise UserError(self.env._("%s has no bill of materials to cut it into pieces.", product.display_name))
        return self.create({
            'mode': mode,
            'product_id': product.id,
            'lot_id': quants.lot_id[:1].id,
            'package_id': package.id,
            'bom_id': bom.id,
            'location_id': package.location_id.id,
            'location_dest_id': package.location_id.id,
        }).id

    @api.model
    def start_production_session(self, product_id, bom_id=False):
        """ Resume the draft production of the product (with this BoM) or
        open a new one. Returns the session id. """
        product = self.env['product.product'].browse(product_id)
        boms = self._get_cutting_boms(product, 'production')
        if bom_id and bom_id not in boms.ids:
            raise UserError(self.env._("This bill of materials does not make %s.", product.display_name))
        bom = boms.browse(bom_id) or boms[:1]
        if not bom:
            raise UserError(self.env._("%s has no bill of materials.", product.display_name))
        session = self.search([
            ('state', '=', 'draft'),
            ('mode', '=', 'production'),
            ('product_id', '=', product.id),
            ('bom_id', '=', bom.id),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if session:
            return session.id
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        return self.create({
            'mode': 'production',
            'product_id': product.id,
            'bom_id': bom.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': warehouse.lot_stock_id.id,
        }).id

    def get_ingredient_packages(self, product_id):
        """ Production: stock of an ingredient, by package (or lot out of
        package), the closest expiration first. What the session already uses
        is deducted. """
        self.ensure_one()
        product = self.env['product.product'].browse(product_id)
        quants = self.env['stock.quant'].search([
            ('product_id', '=', product.id),
            ('location_id', 'child_of', self.location_id.id),
            ('quantity', '>', 0),
        ])
        values = self._get_package_values(quants)
        for value in values:
            used = sum(self.consumption_ids.filtered(
                lambda c: c.package_id.id == value['package_id'] and c.lot_id.id == value['lot_id']
                and c.location_id.id == value['location_id']
            ).mapped('weight'))
            value['qty'] -= used
        return [value for value in values if product.uom_id.compare(value['qty'], 0) > 0]

    def find_ingredient_packages(self, text):
        """ Production: stock of any ingredient of the recipe found by its
        package, lot or crotal, typed or scanned. A scanned label (GS1) is
        longer than the lot or package it carries: it matches when it
        contains it. """
        self.ensure_one()
        text = (text or '').strip().lower()
        if not text:
            return []

        def matches(name):
            name = (name or '').lower()
            return bool(name) and (text in name or name in text)

        return [
            value
            for product in self._get_bom_lines().product_id
            for value in self.get_ingredient_packages(product.id)
            if any(matches(value[key]) for key in ('package_name', 'lot_name', 'crotal_name'))
        ]

    def get_cutting_screen_data(self):
        self.ensure_one()
        bom_lines = self._get_bom_lines()
        lines_by_bom_line = self.line_ids.grouped('bom_line_id')
        lines_by_bom_line = defaultdict(lambda: self.env['meat.cutting.line'], lines_by_bom_line)
        crotal = self.crotal_id
        available_qty = self._get_source_available_qty() if self.mode != 'production' else 0
        components = [] if self.mode == 'preparation' else [{
            'bom_line_id': bom_line.id,
            'product_id': bom_line.product_id.id,
            'name': bom_line.product_id.display_name,
            'uom_name': bom_line.uom_id.name,
            'piece': bom_line.product_id.meat_piece,
            'weighed_count': len(lines_by_bom_line[bom_line]),
            'weighed_qty': sum(lines_by_bom_line[bom_line].mapped('weight')),
        } for bom_line in bom_lines]
        if self.mode == 'production':
            qty_by_product = defaultdict(float)
            for consumption in self.consumption_ids:
                qty_by_product[consumption.product_id] += consumption.weight
            for component in components:
                product = self.env['product.product'].browse(component['product_id'])
                bom_line = self.env['mrp.bom.line'].browse(component['bom_line_id'])
                component.update({
                    # Without the internal reference, to save room on the ingredient tiles
                    'name': product.with_context(display_default_code=False).display_name,
                    'weighed_count': len(self.consumption_ids.filtered(lambda c: c.product_id == product)),
                    'weighed_qty': qty_by_product[product],
                    'available_qty': self.env['stock.quant']._get_available_quantity(product, self.location_id),
                    'recommended_qty': self._get_recommended_qty(bom_line),
                })
        return {
            'id': self.id,
            'name': self.name,
            'state': self.state,
            'mode': self.mode,
            'product_name': self.product_id.display_name,
            'bom_name': self.bom_id.code or self.bom_id.product_tmpl_id.name or '',
            'lot_name': self.lot_id.name or '',
            'output_lot_name': self.output_lot_name or '',
            'package_name': self.package_id.name or '',
            'picking_name': self.picking_id.name or '',
            'crotal': {
                'name': crotal.name,
                'breed': crotal.breed or '',
                'sex': dict(crotal._fields['sex']._description_selection(self.env)).get(crotal.sex, ''),
                'slaughter_date': fields.Date.to_string(crotal.slaughter_date) or '',
                'birth_country': crotal.birth_country or '',
                'reared_country': crotal.reared_country or '',
                'halal': crotal.halal,
            } if crotal else False,
            'uom_name': self.uom_id.name,
            'available_qty': available_qty,
            'consumed_qty': self.consumed_qty if self.state == 'done' else self._get_default_consumed_qty(),
            'total_weight': self.total_weight,
            'components': components,
            'lines': self.line_ids._get_cutting_screen_values(),
            'consumptions': self.consumption_ids._get_cutting_screen_values(),
            'consumed_weight': sum(self.consumption_ids.mapped('weight')),
            'presentations': [{'id': value.id, 'name': value.name}
                              for value in self._get_presentations(self.product_id)],
            'expiration_date': fields.Datetime.to_string(self._get_production_expiration_date())
            if self.mode == 'production' else '',
            'production_qty': self.production_qty,
            'freeze': self.freeze,
            'can_freeze': bool(self._get_output_products().frozen_product_id),
            'label_report_id': self.label_report_id.id,
            'label_formats': self._get_label_formats(),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @api.model
    def _get_cutting_boms(self, product, meat_use='cutting'):
        """ BoMs that cut the product, one per cutting method, or that make
        it in production. """
        return self.env['mrp.bom'].search([
            *self._get_meat_bom_domain(meat_use),
            '|', ('product_id', '=', product.id),
            '&', ('product_id', '=', False), ('product_tmpl_id', '=', product.product_tmpl_id.id),
        ], order='sequence, product_id, id')

    @api.model
    def _get_meat_bom_domain(self, meat_use='cutting'):
        return [
            ('type', '=', 'normal'),
            ('meat_use', '=', meat_use),
            ('company_id', 'in', [self.env.company.id, False]),
        ]

    @api.model
    def _get_bom_products(self, products=None, meat_use='cutting'):
        """ Products (among the given ones) with a BoM of this use. """
        boms = self.env['mrp.bom'].search(self._get_meat_bom_domain(meat_use))
        bom_products = boms.product_id | boms.filtered(lambda b: not b.product_id).product_tmpl_id.product_variant_ids
        return bom_products if products is None else products & bom_products

    @api.model
    def _get_label_formats(self):
        reports = self.env['ir.actions.report'].search([('model', '=', 'meat.cutting.line')], order='name, id')
        return [{
            'id': report.id,
            'name': report.name,
            'paper': report.paperformat_id.name or '',
        } for report in reports]

    def _get_bom_lines(self):
        self.ensure_one()
        return self.bom_id.bom_line_ids.filtered(lambda bl: not bl._skip_bom_line(self.product_id))

    def _get_output_products(self):
        """ Products weighed in the session: the cuts of the BoM, or the
        product itself when prepared or made. """
        self.ensure_one()
        if self.mode in ('preparation', 'production'):
            return self.product_id
        return self._get_bom_lines().product_id

    def _get_recommended_qty(self, bom_line):
        """ Production: quantity of the ingredient (in the unit of the BoM
        line) for the quantity to make, by the ratios of the BoM. """
        self.ensure_one()
        bom = self.bom_id
        if not self.production_qty or not bom.product_qty:
            return 0.0
        factor = self.uom_id._compute_quantity(self.production_qty, bom.uom_id) / bom.product_qty
        # At the precision of the weighings
        return float_round(bom_line.product_qty * factor, precision_digits=self.env['decimal.precision'].precision_get(
            'Product Unit'))

    @api.model
    def _get_presentations(self, product):
        """ Presentations of the product: values of its attributes that do not
        create variants, chosen when the order is served. """
        lines = product.product_tmpl_id.attribute_line_ids.filtered(
            lambda l: l.attribute_id.create_variant == 'no_variant')
        return lines.value_ids

    @api.model
    def _get_package_quants(self, mode):
        """ Free stock in packages: of products with a BoM to cut them again,
        of any product to prepare them. """
        quants = self.env['stock.quant'].search([
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0),
            ('package_id', '!=', False),
            ('company_id', '=', self.env.company.id),
        ])
        quants = quants.filtered(lambda q: q.product_id.uom_id.compare(q.quantity - q.reserved_quantity, 0) > 0)
        if mode == 'cutting':
            products = self._get_bom_products(quants.product_id)
            quants = quants.filtered(lambda q: q.product_id in products)
        return quants

    @api.model
    def _get_production_products(self):
        return self._get_bom_products(meat_use='production').filtered(lambda p: p.is_storable and p.active)

    @api.model
    def _get_package_values(self, quants, with_boms=False):
        """ Stock grouped by package (or by lot and location out of package),
        the closest expiration first. """
        groups = defaultdict(lambda: self.env['stock.quant'])
        for quant in quants:
            groups[quant.product_id, quant.package_id, quant.lot_id, quant.location_id] |= quant
        result = []
        for (product, package, lot, location), group in groups.items():
            qty = sum(group.mapped('quantity')) - sum(group.mapped('reserved_quantity'))
            if product.uom_id.compare(qty, 0) <= 0:
                continue
            value = {
                'key': f'{product.id}-{package.id}-{lot.id}-{location.id}',
                'product_id': product.id,
                # The internal reference is shown on demand only
                'product_name': product.with_context(display_default_code=False).display_name,
                'default_code': product.default_code or '',
                'package_id': package.id,
                'package_name': package.name or '',
                'lot_id': lot.id,
                'lot_name': lot.name or '',
                'crotal_name': lot.crotal_id.name or '',
                'location_id': location.id,
                'location_name': location.display_name,
                'presentation': package.meat_presentation_id.name or '',
                'expiration_date': fields.Datetime.to_string(lot.expiration_date) or '',
                'qty': qty,
                'uom_name': product.uom_id.name,
            }
            if with_boms:
                value['boms'] = [{
                    'id': bom.id,
                    'name': bom.code or bom.product_tmpl_id.name,
                    'cut_count': len(bom.bom_line_ids.filtered(lambda bl: not bl._skip_bom_line(product))),
                } for bom in self._get_cutting_boms(product)]
            result.append(value)
        return sorted(result, key=lambda v: (not v['expiration_date'], v['expiration_date'], v['package_name']))

    @api.model
    def _get_cutting_quants(self, picking=None):
        # Packages are cut again in the cutting mode, not as received lots
        domain = Domain([
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0),
            ('package_id', '=', False),
            ('company_id', '=', self.env.company.id),
        ])
        if picking:
            lots = picking.move_line_ids.lot_id
            if lots:
                domain &= Domain('lot_id', 'in', lots.ids)
            else:
                domain &= Domain('product_id', 'in', picking.move_ids.product_id.ids)
        quants = self.env['stock.quant'].search(domain)
        products = self._get_bom_products(quants.product_id)
        return quants.filtered(lambda q: q.product_id in products)

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

    def _get_source_available_qty(self):
        self.ensure_one()
        return self.env['stock.quant']._get_available_quantity(
            self.product_id, self.location_id, lot_id=self.lot_id or None,
            package_id=self.package_id or None, strict=True)

    def _get_default_consumed_qty(self):
        """ A source lot is one animal (crotal) and a package is one piece:
        they are consumed entirely, the difference with the weighed cuts being
        the cutting loss. A prepared package only gives the weight of the new
        packages, the rest stays in it. Without lot, the weighed quantity is
        consumed when the units match, else one unit. """
        self.ensure_one()
        if self.mode == 'production':
            return sum(self.consumption_ids.mapped('weight'))
        if self.mode == 'preparation':
            return self.uom_id.round(self.total_weight)
        if self.package_id:
            return self._get_source_available_qty()
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
        products = self.line_ids.output_product_id
        if self.mode == 'production':
            # Made fresh, then the packages to freeze are frozen
            products |= self.product_id
        products = products.filtered(lambda p: p.tracking != 'none')
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
            if lines:
                vals['expiration_date'] = min(line._get_default_expiration_date() for line in lines)
            else:
                # Production all frozen: the fresh lot only lives until frozen
                vals['expiration_date'] = self._get_production_expiration_date() or fields.Datetime.now() + timedelta(
                    days=product.expiration_time)
        return vals

    def _get_unused_ingredients(self):
        """ Production: ingredients of the recipe without any weighing, even
        if not in the quantity recommended. """
        self.ensure_one()
        return self._get_bom_lines().product_id - self.consumption_ids.product_id

    def _get_production_expiration_date(self):
        """ A product made expires with its ingredient closest to expiry. """
        self.ensure_one()
        dates = self.consumption_ids.lot_id.filtered('expiration_date').mapped('expiration_date')
        return min(dates) if dates else False

    def _prepare_piece_package_vals(self, presentation=None):
        self.ensure_one()
        return {'meat_piece': True, 'meat_presentation_id': presentation.id if presentation else False}

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

    def _validate_production(self):
        """ Make the product through a manufacturing order consuming the weighed
        ingredients from their packages, in a new lot that expires with the
        ingredient closest to expiry, one package per weighing. The packages
        to freeze are then frozen, into the lot of the frozen product. """
        self.ensure_one()
        if not self.consumption_ids:
            raise UserError(self.env._("Weigh at least one ingredient before validating."))
        if missing := self._get_unused_ingredients():
            raise UserError(self.env._(
                "Use every ingredient of the recipe before validating. Not used: %s.",
                ", ".join(missing.mapped('display_name'))))
        for consumption in self.consumption_ids:
            available = self.env['stock.quant']._get_available_quantity(
                consumption.product_id, consumption.location_id, lot_id=consumption.lot_id or None,
                package_id=consumption.package_id or None, strict=True)
            used = sum(self.consumption_ids.filtered(lambda c: (c.product_id, c.package_id, c.lot_id, c.location_id) == (
                consumption.product_id, consumption.package_id, consumption.lot_id, consumption.location_id)).mapped('weight'))
            if consumption.product_id.uom_id.compare(used, available) > 0:
                raise UserError(self.env._(
                    "Only %(qty)s %(uom)s of %(product)s are left in %(source)s.",
                    qty=consumption.product_id.uom_id.round(available), uom=consumption.product_id.uom_id.name,
                    product=consumption.product_id.display_name,
                    source=consumption.package_id.name or consumption.lot_id.name or consumption.location_id.display_name,
                ))
        lot_by_product = self._create_output_lots()
        lot = lot_by_product.get(self.product_id, self.env['stock.lot'])
        qty = self.uom_id.round(self.total_weight)
        production = self.env['mrp.production'].create({
            'product_id': self.product_id.id,
            'bom_id': self.bom_id.id,
            'product_qty': qty,
            'uom_id': self.uom_id.id,
            'location_src_id': self.location_id.id,
            'location_dest_id': self.location_dest_id.id,
            'origin': self.name,
            'company_id': self.company_id.id,
        })
        production.action_confirm()
        production.write({'qty_producing': qty, 'lot_producing_ids': [Command.set(lot.ids)]})
        raw_moves = production.move_raw_ids
        finished_moves = production.move_finished_ids.filtered(lambda m: m.product_id == self.product_id)
        (raw_moves | finished_moves).move_line_ids.unlink()
        move_line_vals = []
        for consumption in self.consumption_ids:
            move = raw_moves.filtered(lambda m: m.product_id == consumption.product_id)[:1]
            move_line_vals.append({
                'move_id': move.id,
                'product_id': consumption.product_id.id,
                'uom_id': consumption.product_id.uom_id.id,
                'quantity': consumption.weight,
                'lot_id': consumption.lot_id.id,
                'package_id': consumption.package_id.id,
                'location_id': consumption.location_id.id,
                'location_dest_id': move.location_dest_id.id,
            })
        finished_move = finished_moves[:1]
        move_line_vals += [{
            'move_id': finished_move.id,
            'product_id': self.product_id.id,
            'uom_id': self.uom_id.id,
            'quantity': line.weight,
            'lot_id': lot.id,
            'result_package_id': line.package_id.id,
            'location_id': finished_move.location_id.id,
            'location_dest_id': finished_move.location_dest_id.id,
        } for line in self.line_ids]
        self.env['stock.move.line'].create(move_line_vals)
        # The finished moves are left unpicked: picked, they would count as
        # already produced and be emptied when marked as done
        raw_moves.picked = True
        res = production.with_context(
            skip_consumption=True, skip_expired=True, skip_redirection=True, skip_backorder=True,
        ).button_mark_done()
        if production.state != 'done':
            raise UserError(self.env._("The manufacturing order %s could not be done.", production.name))
        for line in self.line_ids.filtered('freeze'):
            quant = self.env['stock.quant'].search([
                ('product_id', '=', self.product_id.id),
                ('package_id', '=', line.package_id.id),
                ('lot_id', '=', lot.id),
                ('location_id', '=', self.location_dest_id.id),
                ('quantity', '>', 0),
            ], limit=1)
            quant._meat_freeze(lot_by_product.get(line.output_product_id, self.env['stock.lot']))
        self.write({'consumed_qty': self._get_default_consumed_qty(), 'production_id': production.id, 'state': 'done'})
        return res
