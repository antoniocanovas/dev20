from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .purchase_order import UNBUILD_TYPES, normalize_plate
from .res_company import VEHICLE_TYPES
from .scrap_dismantle_line import DISMANTLE_RESULTS, PART_CONDITIONS


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_template = fields.Boolean(
        'Scrap Template',
        help="Products used as templates of the vehicle recycling, as the vehicles bought to be "
             "dismantled. The scrap entry of the touch screen offers them. When a purchase of "
             "vehicles is confirmed, each vehicle becomes a copy of its template.")
    scrap_template_id = fields.Many2one(
        'product.template', string="Vehicle Template", copy=False, index='btree_not_null',
        domain=[('is_template', '=', True)],
        help="Scrap template this vehicle was copied from when its purchase was confirmed. Set it "
             "on a vehicle created by hand to make it a vehicle.")
    scrap_lot_name = fields.Char(
        'License Plate', copy=False, index='btree_not_null',
        help="License plate of the vehicle, its serial number when it is received.")
    scrap_analytic_account_id = fields.Many2one(
        'account.analytic.account', string="Analytic Account", copy=False,
        help="Analytic account of the vehicle, named after its license plate, set on its purchase "
             "and its invoices.")
    scrap_location_id = fields.Many2one(
        'stock.location', string="Original Location", copy=False,
        help="Location created for the vehicle, named after its license plate, under the one of "
             "its kind of entry in the company, where it is received.")

    scrap_unbuild_type = fields.Selection(
        UNBUILD_TYPES, string="Scrap Type", copy=False, index='btree_not_null',
        help="Kind of product of the vehicle recycling: a vehicle or a part to dismantle, a "
             "subproduct, or a vehicle to repair and sell. A vehicle gets the one of its purchase. "
             "The CAT tab is shown when it is set.")

    # Legal deadlines of the vehicles to dismantle, from their discharge date, as in
    # scrap_unbuild (Odoo 17)
    discharge_date = fields.Date(
        'Discharge Date', copy=False,
        help="Date the vehicle to dismantle was received, set by its receipt; its legal deadlines "
             "count from it.")
    decontamination_limit_date = fields.Date(
        'Decontaminate By', copy=False, compute='_compute_scrap_limit_dates', store=True,
        help="Legal limit to decontaminate the vehicle: its discharge date plus the "
             "decontamination days of the company.")
    decontamination_date = fields.Date(
        'Decontaminated On', copy=False,
        help="Date the vehicle was decontaminated; empty while it is pending.")
    scrap_limit_date = fields.Date(
        'Dismantle By', copy=False, compute='_compute_scrap_limit_dates', store=True,
        help="Legal limit to dismantle the vehicle: its discharge date plus the dismantling days "
             "of the company.")
    scrap_date = fields.Date(
        'Dismantled On', copy=False,
        help="Date the vehicle was dismantled; empty while it is pending.")
    scrap_origin_id = fields.Many2one(
        'product.template', string="Origin", copy=False, index='btree_not_null',
        help="What a subproduct was dismantled from at first: the vehicle or, when it was "
             "dismantled from another subproduct, the origin of that one. Empty on what is bought, "
             "as the vehicles or an engine bought to dismantle, which are the origin of their "
             "subproducts.")
    scrap_origin_line_ids = fields.One2many(
        'scrap.dismantle.line', 'origin_id', string="All Parts",
        help="Parts and waste of the vehicle, or of the subproduct bought, and of all its "
             "subproducts, dismantled later.")
    scrap_dismantle_line_ids = fields.One2many(
        'scrap.dismantle.line', 'vehicle_id', string="Parts and Waste",
        help="Waste taken out of the vehicle while decontaminating it, and components of its bill "
             "of materials marked while dismantling it.")
    decontamination_days_left = fields.Integer(
        'Days to Decontaminate', compute='_compute_scrap_days_left',
        help="Days left until the decontamination limit; negative when it is late.")
    scrap_days_left = fields.Integer(
        'Days to Dismantle', compute='_compute_scrap_days_left',
        help="Days left until the dismantling limit; negative when it is late.")

    # Data of the vehicles and their parts, as in custom_product (Odoo 17)
    vehicle_model_id = fields.Many2one('fleet.vehicle.model', string='Make/Model')
    scrap_vehicle_brand_id = fields.Many2one(
        'fleet.vehicle.model.brand', string="Vehicle Brand", related='vehicle_model_id.brand_id',
        store=True, index='btree_not_null',
        help="Brand (manufacturer) of the vehicle of the product, from its make/model: the vehicles "
             "and their parts are found by it, as from the opportunities.")
    plate = fields.Char('Plate', copy=False)
    uses = fields.Text('Product Uses')
    references = fields.Text('References')
    ref_market = fields.Char(
        string='Visible Ref.',
        help="The reference written or stamped on the part.")
    ref_oem = fields.Char(
        string='OEM Ref.',
        help="The reference of the manufacturer of the vehicle.")
    # Kept by each variant: the one of the only variant, empty with several, as the internal
    # reference
    chassis = fields.Char(
        'Chassis', compute='_compute_chassis', inverse='_set_chassis', store=True,
        help="Chassis (VIN) of the vehicle or the accessory. With variants, each one has its own.")

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

    @api.depends('product_variant_ids.chassis')
    def _compute_chassis(self):
        for template in self:
            template.chassis = template.product_variant_ids.chassis if len(template.product_variant_ids) == 1 else False

    def _set_chassis(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.chassis = template.chassis

    @api.depends('discharge_date', 'scrap_unbuild_type', 'company_id.decontamination_days', 'company_id.scrap_days')
    def _compute_scrap_limit_dates(self):
        for template in self:
            company = template.company_id or self.env.company
            to_dismantle = template.scrap_unbuild_type == 'main' and template.discharge_date
            template.decontamination_limit_date = (
                to_dismantle and company.decontamination_days
                and template.discharge_date + timedelta(days=company.decontamination_days))
            template.scrap_limit_date = (
                to_dismantle and company.scrap_days
                and template.discharge_date + timedelta(days=company.scrap_days))

    @api.depends('decontamination_limit_date', 'scrap_limit_date')
    @api.depends_context('tz')
    def _compute_scrap_days_left(self):
        today = fields.Date.context_today(self)
        for template in self:
            template.decontamination_days_left = (
                (template.decontamination_limit_date - today).days if template.decontamination_limit_date else 0)
            template.scrap_days_left = (template.scrap_limit_date - today).days if template.scrap_limit_date else 0

    @api.constrains('discharge_date', 'decontamination_date', 'scrap_date')
    def _check_scrap_dates(self):
        for template in self:
            if template.decontamination_date and template.discharge_date and template.decontamination_date < template.discharge_date:
                raise ValidationError(self.env._(
                    "%s can't be decontaminated before its discharge date.", template.display_name))
            # A subproduct is dismantled without decontaminating it
            if template.scrap_date and not template.decontamination_date and template.scrap_unbuild_type == 'main':
                raise ValidationError(self.env._(
                    "%s must be decontaminated before it is dismantled.", template.display_name))
            if template.scrap_date and template.decontamination_date and template.scrap_date < template.decontamination_date:
                raise ValidationError(self.env._(
                    "%s can't be dismantled before it is decontaminated.", template.display_name))

    def action_scrap_decontaminated(self):
        """ Decontaminated today, the ones still pending. """
        self.filtered(lambda template: not template.decontamination_date)._scrap_write_cat_dates({
            'decontamination_date': fields.Date.context_today(self)})

    def action_scrap_dismantled(self):
        """ Dismantled today, the ones still pending. """
        self.filtered(lambda template: not template.scrap_date)._scrap_write_cat_dates({
            'scrap_date': fields.Date.context_today(self)})

    def _scrap_is_subproduct(self):
        """ Whether it is a subproduct to dismantle: a product of its own, made of a scrap
        template, as an engine dismantled from a vehicle or bought. It is dismantled as the
        vehicles, without decontaminating it nor legal deadlines. """
        self.ensure_one()
        return self.scrap_unbuild_type == 'subproduct' and bool(self.scrap_template_id) and not self.is_template

    def _scrap_check_can_dismantle(self):
        """ A vehicle received and decontaminated, or a subproduct dismantled from another
        product or bought and received, not dismantled yet. """
        self.ensure_one()
        if self._scrap_is_subproduct():
            if not self.active:
                raise UserError(self.env._("%s is archived.", self.display_name))
            if not self.scrap_origin_id and not self.discharge_date:
                raise UserError(self.env._("%s isn't received yet.", self.display_name))
        else:
            if self.scrap_unbuild_type != 'main' or not self.discharge_date:
                raise UserError(self.env._("%s isn't a vehicle to dismantle received.", self.display_name))
            if not self.decontamination_date:
                raise UserError(self.env._("%s must be decontaminated before it is dismantled.", self.display_name))
        if self.scrap_date:
            raise UserError(self.env._("%s is already dismantled.", self.display_name))

    def _scrap_dismantle_pending_lines(self):
        """ The components of the bills of materials of the vehicle still to dismantle. """
        self.ensure_one()
        return self.sudo().bom_ids.bom_line_ids.filtered(lambda line: line.product_qty > 0)

    def _scrap_dismantle(self, bom_line, quantity, result, condition=False, location=False):
        """ The operator marks `quantity` of a component of the bill of materials of the vehicle
        as dismantled, missing or discarded. It is decreased in the bill of materials, which so
        keeps what is still to dismantle. A dismantled part enters the stock of `location` (by
        default, the one of the vehicle), with its condition; a discarded one goes to the scrap
        location. A dismantled component that is a scrap template becomes, by unit, a product of
        its own, a copy of the template, as the vehicles bought; any other one just increases
        its stock. When nothing is left, the vehicle is dismantled today. A subproduct is
        dismantled the same way; the products made of its components keep its origin (or the
        subproduct itself, when it was bought) as theirs.

        :return: the parts marked (`scrap.dismantle.line`), one per product
        """
        self.ensure_one()
        if not self.env.user.has_group('stock.group_stock_user'):
            raise AccessError(self.env._("Only the inventory users can dismantle the vehicles."))
        self.check_access('read')
        bom_line = bom_line.sudo()
        self._scrap_check_can_dismantle()
        if bom_line.bom_id.product_tmpl_id != self:
            raise ValidationError(self.env._("The part isn't in the bill of materials of %s.", self.display_name))
        if result not in dict(DISMANTLE_RESULTS):
            raise ValidationError(self.env._("Invalid result."))
        uom = bom_line.uom_id
        if quantity <= 0 or uom.compare(quantity, bom_line.product_qty) > 0:
            raise UserError(self.env._(
                "%(quantity)s %(part)s can't be marked: %(left)s left.",
                quantity=quantity, part=bom_line.product_id.display_name, left=bom_line.product_qty))
        if result == 'dismantled':
            if condition not in dict(PART_CONDITIONS):
                raise UserError(self.env._("Set the condition of the dismantled part."))
            location = location or self.scrap_location_id
            company = self.company_id or self.env.company
            if not location or location.usage != 'internal' or location.company_id not in (company, self.env['res.company']):
                raise UserError(self.env._("Choose an internal location of the company for the dismantled part."))
        else:
            condition = False
            location = self.env['stock.location']
        company = self.company_id or self.env.company
        component = bom_line.product_id
        if result == 'dismantled' and component.is_template:
            # A scrap template (as an engine to dismantle later): each unit becomes a product
            # of its own, a copy of it, as the vehicles bought
            if uom.compare(quantity, round(quantity)) != 0:
                raise UserError(self.env._("%s is dismantled by whole units.", component.display_name))
            if component.product_tmpl_id.product_variant_count > 1:
                raise UserError(self.env._("The scrap template %s can't have variants.", component.display_name))
            products = self.env['product.product'].concat(
                self._scrap_copy_part_template(component.product_tmpl_id).product_variant_id
                for _index in range(round(quantity)))
            quantities = [(product, 1.0) for product in products]
        else:
            quantities = [(component, quantity)]
        lines = self.env['scrap.dismantle.line'].sudo().create([{
            'vehicle_id': self.id,
            'company_id': company.id,
            'stage': 'dismantling',
            'product_id': product.id,
            'bom_line_id': bom_line.id,
            'quantity': product_quantity,
            'uom_id': uom.id,
            'result': result,
            'condition': condition,
            'location_dest_id': location.id,
            'user_id': self.env.user.id,
        } for product, product_quantity in quantities])
        if result in ('dismantled', 'discarded'):
            for line in lines:
                line.move_id = self._scrap_dismantle_move(line)
        bom_line.product_qty -= quantity
        if not self._scrap_dismantle_pending_lines():
            self._scrap_write_cat_dates({'scrap_date': fields.Date.context_today(self)})
        return lines.sudo(False)

    def _scrap_decontaminate(self, product, quantity, result, location=False):
        """ The operator takes a waste of the company out of the vehicle while decontaminating
        it: `quantity` discarded, which enters the stock of `location` (by default, the waste
        zone of the company), or missing. It can be done as many times as needed, and corrected
        or removed, until the vehicle is marked as decontaminated.

        :return: the waste marked (`scrap.dismantle.line`)
        """
        location = self._scrap_check_waste(product, quantity, result, location)
        line = self.env['scrap.dismantle.line'].sudo().create({
            'vehicle_id': self.id,
            'company_id': (self.company_id or self.env.company).id,
            'stage': 'decontamination',
            'product_id': product.id,
            'quantity': quantity,
            'uom_id': product.uom_id.id,
            'result': result,
            'location_dest_id': location.id,
            'user_id': self.env.user.id,
        })
        if result == 'discarded':
            line.move_id = self._scrap_dismantle_move(line)
        return line.sudo(False)

    def _scrap_update_waste(self, line, quantity, result, location=False):
        """ Correct a waste marked, until the vehicle is decontaminated: its stock goes back and
        enters again with the new quantity, result and location. """
        line = line.sudo()
        if line.vehicle_id != self or line.stage != 'decontamination':
            raise ValidationError(self.env._("The waste isn't of %s.", self.display_name))
        location = self._scrap_check_waste(line.product_id, quantity, result, location)
        if line.move_id:
            self._scrap_reverse_dismantle_move(line)
        line.write({
            'quantity': quantity,
            'result': result,
            'location_dest_id': location.id,
            'move_id': False,
            'user_id': self.env.user.id,
        })
        if result == 'discarded':
            line.move_id = self._scrap_dismantle_move(line)
        return line.sudo(False)

    def _scrap_check_waste(self, product, quantity, result, location=False):
        """ A waste can be marked: the vehicle is received and isn't decontaminated yet, the
        product is a waste of the company and the location is internal.

        :return: where the waste enters the stock, if discarded
        """
        self.ensure_one()
        if not self.env.user.has_group('stock.group_stock_user'):
            raise AccessError(self.env._("Only the inventory users can decontaminate the vehicles."))
        self.check_access('read')
        company = self.company_id or self.env.company
        product = product.sudo()
        if self.scrap_unbuild_type != 'main' or not self.discharge_date:
            raise UserError(self.env._("%s isn't a vehicle to dismantle received.", self.display_name))
        if self.decontamination_date:
            raise UserError(self.env._("%s is already decontaminated.", self.display_name))
        if product not in company.scrap_waste_product_ids:
            raise ValidationError(self.env._("%s isn't a waste product of the company.", product.display_name))
        if result not in ('discarded', 'missing'):
            raise ValidationError(self.env._("Invalid result."))
        if quantity <= 0:
            raise UserError(self.env._("The quantity must be positive."))
        if result != 'discarded':
            return self.env['stock.location']
        location = location or company.scrap_waste_location_id
        if not location or location.usage != 'internal' or location.company_id not in (company, self.env['res.company']):
            raise UserError(self.env._("Choose an internal location of the company for the waste."))
        if product.tracking == 'serial' and product.uom_id.compare(quantity, round(quantity)) != 0:
            raise UserError(self.env._("%s is taken out by whole units.", product.display_name))
        return location

    def _scrap_undo_dismantle(self, line):
        """ Undo a part or a waste marked by mistake: its stock goes back (if it entered the
        stock, it must still be there, with its lot) and it is removed. A part dismantled made of
        a scrap template is archived, and its quantity is again to dismantle in the bill of
        materials: a vehicle dismantled isn't anymore. A waste is removed until the vehicle is
        decontaminated. """
        self.ensure_one()
        if not self.env.user.has_group('stock.group_stock_user'):
            raise AccessError(self.env._("Only the inventory users can dismantle the vehicles."))
        self.check_access('read')
        line = line.sudo()
        if line.vehicle_id != self:
            raise ValidationError(self.env._("The part isn't of %s.", self.display_name))
        if line.stage == 'decontamination':
            # Removed until the vehicle is decontaminated
            if self.decontamination_date:
                raise UserError(self.env._("%s is decontaminated: undo the decontamination first.", self.display_name))
            if line.move_id:
                self._scrap_reverse_dismantle_move(line)
            line.unlink()
            return
        bom_line = line.bom_line_id
        if not bom_line or not bom_line.bom_id.active:
            raise UserError(self.env._(
                "%s can't be undone: its line of the bill of materials doesn't exist anymore.", line.display_name))
        product = line.product_id
        made_of_template = product != bom_line.product_id and bool(product.scrap_template_id)
        if made_of_template and product.product_tmpl_id.with_context(active_test=False).scrap_dismantle_line_ids:
            raise UserError(self.env._(
                "%s has parts marked: undo its dismantling first.", product.display_name))
        if line.move_id:
            self._scrap_reverse_dismantle_move(line)
        if made_of_template:
            self.env['account.analytic.distribution.model'].sudo().search([('product_id', '=', product.id)]).unlink()
            product.product_tmpl_id.active = False
        bom_line.product_qty += line.quantity
        line.unlink()
        if self.scrap_date:
            self._scrap_write_cat_dates({'scrap_date': False})

    def _scrap_reverse_dismantle_move(self, line):
        """ The stock move of a part, back to where it came from. """
        move = line.move_id
        Quant = self.env['stock.quant'].sudo()
        if move.location_dest_id.usage == 'internal':
            for move_line in move.move_line_ids:
                available = Quant._get_available_quantity(
                    move_line.product_id, move_line.location_dest_id, lot_id=move_line.lot_id or None, strict=True)
                if move_line.product_id.uom_id.compare(move_line.quantity_product_uom, available) > 0:
                    raise UserError(self.env._(
                        "%(part)s can't be undone: it isn't in %(location)s anymore.",
                        part=line.display_name, location=move_line.location_dest_id.display_name))
        reverse = self.env['stock.move'].sudo().create({
            'product_id': move.product_id.id,
            'uom_id': move.uom_id.id,
            'product_uom_qty': move.product_uom_qty,
            'company_id': move.company_id.id,
            'state': 'confirmed',
            'location_id': move.location_dest_id.id,
            'location_dest_id': move.location_id.id,
            'origin': self.env._("Undone: %s", move.origin or ''),
            'origin_returned_move_id': move.id,
            'picked': True,
            'move_line_ids': [fields.Command.create({
                'product_id': move_line.product_id.id,
                'uom_id': move_line.uom_id.id,
                'quantity': move_line.quantity,
                'location_id': move_line.location_dest_id.id,
                'location_dest_id': move_line.location_id.id,
                'company_id': move_line.company_id.id,
                'lot_id': move_line.lot_id.id,
            }) for move_line in move.move_line_ids],
        })
        reverse._action_done()
        return reverse

    def _scrap_copy_part_template(self, template):
        """ A part dismantled from the vehicle that is a scrap template: a copy of it, a
        subproduct of the origin of the vehicle (the vehicle itself, or the engine bought, when
        they have none), named after it, with its make/model, its location and its analytic
        account, and the bills of materials of the template, to dismantle it later. A template
        to dismantle ('main') gives a subproduct: it isn't received, as the vehicles bought.
        Always saleable, although the template isn't. """
        company = self.company_id or self.env.company
        origin = self.scrap_origin_id or self
        unbuild_type = template.scrap_unbuild_type
        part = template.sudo().with_company(company).copy({
            'name': f"{template.name} {origin.default_code or origin.scrap_lot_name or origin.name}",
            'is_template': False,
            'default_code': False,
            'sale_ok': True,
            'scrap_template_id': template.id,
            'scrap_unbuild_type': 'subproduct' if unbuild_type in (False, 'main') else unbuild_type,
            'scrap_origin_id': origin.id,
            'scrap_location_id': origin.scrap_location_id.id,
            'scrap_analytic_account_id': origin.scrap_analytic_account_id.id,
            'company_id': company.id,
            'vehicle_model_id': (self.vehicle_model_id or template.vehicle_model_id).id,
        })
        part._scrap_copy_boms()
        if part.scrap_analytic_account_id:
            # Its sales go to the analytic account of the vehicle, as the ones of the vehicle
            self.env['account.analytic.distribution.model'].sudo().create({
                'product_id': part.product_variant_id.id,
                'analytic_distribution': {str(part.scrap_analytic_account_id.id): 100},
                'company_id': company.id,
            })
        return part.with_env(self.env)

    def _scrap_dismantle_move(self, line):
        """ The stock move of a part dismantled, or of a waste, from the production location
        into its destination, or of a part discarded while dismantling, into the scrap location.
        A part entering the stock tracked by lot or serial number gets new ones, after the
        reference of the vehicle. """
        company = line.company_id
        product = line.product_id.with_company(company)
        source = product.property_stock_production
        # Into its destination; a part discarded while dismantling, into the scrap location
        destination = line.location_dest_id or company.scrap_location_id
        entering = bool(line.location_dest_id)
        if not source or not destination:
            raise UserError(self.env._("The production and scrap locations of the company %s are missing.", company.name))
        Lot = self.env['stock.lot'].sudo()
        origin = self.scrap_origin_id
        prefix = (self.default_code or self.scrap_lot_name
                  or (origin and f"{origin.default_code or origin.scrap_lot_name or origin.id}-{self.id}")
                  or str(self.id))
        if product.tracking == 'serial' and entering:
            lots = Lot.create([{'name': f"{prefix}-{line.id}-{index + 1}", 'product_id': product.id, 'company_id': company.id}
                               for index in range(int(line.quantity))])
            quantities = [(lot, 1.0) for lot in lots]
        elif product.tracking == 'lot' and entering:
            lot = Lot.create({'name': f"{prefix}-{line.id}", 'product_id': product.id, 'company_id': company.id})
            quantities = [(lot, line.quantity)]
        else:
            quantities = [(Lot, line.quantity)]
        move = self.env['stock.move'].sudo().create({
            'product_id': product.id,
            'uom_id': line.uom_id.id,
            'product_uom_qty': line.quantity,
            'company_id': company.id,
            'state': 'confirmed',
            'location_id': source.id,
            'location_dest_id': destination.id,
            'origin': self.display_name,
            'is_scrap': not entering,
            'picked': True,
            'move_line_ids': [fields.Command.create({
                'product_id': product.id,
                'uom_id': line.uom_id.id,
                'quantity': quantity,
                'location_id': source.id,
                'location_dest_id': destination.id,
                'company_id': company.id,
                'lot_id': lot.id,
            }) for lot, quantity in quantities],
        })
        move._action_done()
        return move

    def action_scrap_complete_vehicle(self):
        """ A vehicle created by hand, or one that lacks them, gets the analytic account, the
        location and the analytic distribution it would have got from its purchase. """
        for template in self:
            template._scrap_check_vehicle()
            company = template.company_id or self.env.company
            plan = company._get_scrap_analytic_plan(template.scrap_unbuild_type)
            parent_location = company._get_scrap_location(template.scrap_unbuild_type)
            if not plan or not parent_location:
                raise UserError(self.env._(
                    "Set the analytic plan and the location of the vehicles of this kind of entry in "
                    "the CAT tab of the company %s.", company.name))
            if not template.company_id:
                # Its location and its analytic account are of a company
                template.company_id = company
            template._scrap_complete_vehicle(plan, parent_location)

    def _scrap_check_vehicle(self):
        self.ensure_one()
        if self.is_template or not self.scrap_template_id:
            raise UserError(self.env._(
                "Set the vehicle template of %s: only a vehicle gets the CAT data.", self.display_name))
        if self.scrap_unbuild_type not in VEHICLE_TYPES:
            raise UserError(self.env._(
                "Set the scrap type of %s: 'Vehículo o Parte para desguace' or 'Para compra/venta'.",
                self.display_name))
        if not self.scrap_lot_name:
            raise UserError(self.env._("Enter the license plate of %s.", self.display_name))
        if len(self.product_variant_ids) > 1:
            raise UserError(self.env._(
                "%s has variants: a vehicle can't have them.", self.display_name))
        if self._scrap_find_vehicles(self.scrap_lot_name, self.company_id or self.env.company) - self:
            raise UserError(self.env._(
                "There is already a vehicle with the license plate %s.", self.scrap_lot_name))

    def _scrap_complete_vehicle(self, plan, parent_location):
        """ The analytic account, in `plan`, and the location, under `parent_location`, both
        named after its license plate, the analytic distribution and the bills of materials of
        the vehicle, the ones it lacks. Also by users that can't create them, as when they
        confirm a purchase. """
        self.ensure_one()
        company = self.company_id
        vehicle = self.sudo()
        vals = {}
        if not vehicle.scrap_analytic_account_id:
            vals['scrap_analytic_account_id'] = self.env['account.analytic.account'].sudo().create({
                'name': vehicle.scrap_lot_name,
                'plan_id': plan.id,
                'company_id': company.id,
            }).id
        if not vehicle.scrap_location_id:
            vals['scrap_location_id'] = self.env['stock.location'].sudo().create({
                'name': vehicle.scrap_lot_name,
                'location_id': parent_location.id,
                'usage': 'internal',
                'company_id': company.id,
            }).id
        if vals:
            vehicle.write(vals)
        # Its invoices, and its sales, go to its analytic account
        product = vehicle.product_variant_id
        Distribution = self.env['account.analytic.distribution.model'].sudo()
        if not Distribution.search_count([('product_id', '=', product.id)], limit=1):
            Distribution.create({
                'product_id': product.id,
                'analytic_distribution': {str(vehicle.scrap_analytic_account_id.id): 100},
                'company_id': company.id,
            })
        vehicle._scrap_copy_boms()

    def _scrap_copy_boms(self):
        """ The bills of materials of its scrap template, with their operations, for a vehicle
        without any: how it is taken to pieces (steering wheel, wheels, engine...). The ones of
        another company are left out. """
        self.ensure_one()
        if self.bom_ids:
            return
        boms = self.scrap_template_id.bom_ids.filtered(
            lambda bom: not bom.company_id or bom.company_id == self.company_id)
        for bom in boms:
            bom.copy({
                'product_tmpl_id': self.id,
                'product_id': bom.product_id and self.product_variant_id.id,
            })

    def _scrap_write_cat_dates(self, vals):
        """ The warehouse users mark the vehicles as decontaminated or dismantled, although they
        can't change the products. """
        if not self.env.user.has_group('stock.group_stock_user'):
            raise AccessError(self.env._("Only the inventory users can mark the vehicles as done."))
        self.check_access('read')
        self.sudo().write(vals)

    @api.onchange('chassis')
    def _onchange_chassis(self):
        return self.env['product.product']._get_chassis_warning(self.chassis, self._origin.product_variant_ids)

    def _get_related_fields_variant_template(self):
        return [*super()._get_related_fields_variant_template(), 'chassis']

    def _scrap_find_vehicles(self, plate, company):
        """ Active vehicles with the license plate `plate`, of `company` or shared. """
        return self.search([
            ('scrap_template_id', '!=', False),
            ('scrap_lot_name', '=', plate),
            *self._check_company_domain(company),
        ])
