from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.scrap_base.models.purchase_order import normalize_plate

from .scrap_touch import is_record_id

# Vehicles shown in a list of the screen
VEHICLE_LIMIT = 100
# Locations offered for a dismantled part, and parts marked shown while dismantling
LOCATION_LIMIT = 50
PART_LIMIT = 50
# Stages of the legal deadlines of the vehicles to dismantle (see scrap_base): the date field
# of each one, its limit and the stage that must be done before
CAT_STAGES = {
    'decontamination': {
        'date': 'decontamination_date',
        'limit': 'decontamination_limit_date',
        'days_left': 'decontamination_days_left',
    },
    'scrap': {
        'date': 'scrap_date',
        'limit': 'scrap_limit_date',
        'days_left': 'scrap_days_left',
        'requires': 'decontamination_date',
    },
}
# Filters of the list of each kind of list
VEHICLE_FILTERS = {
    'decontamination': ('pending', 'late', 'done', 'all'),
    # Subproducts: the ones of their own made of a scrap template, as an engine, to dismantle
    'scrap': ('pending', 'late', 'done', 'all', 'subproduct'),
    # 'on_sale': the vehicles to repair and sell in stock, of the list "On sale" of the
    # purchase/sale entry
    'vehicles': ('in_stock', 'main', 'refurbish', 'all', 'on_sale'),
}


class ScrapTouch(models.AbstractModel):
    """ Decontamination, dismantling and vehicles on the touch screen: lists of vehicles, as the
    lists of purchases, and the summary of each one, where it is marked as done. """
    _inherit = 'scrap.touch'

    @api.model
    def get_screen_data(self):
        data = super().get_screen_data()
        user = self.env.user
        data.update({
            'can_purchase': user.has_group('purchase.group_purchase_user'),
            'can_cat': user.has_group('stock.group_stock_user'),
            'cat_counts': self.get_cat_counts() if user.has_group('stock.group_stock_user') else {},
        })
        return data

    @api.model
    def get_cat_counts(self):
        """ Vehicles pending and late in each stage, shown in the main menu. """
        Template = self.env['product.template']
        return {
            stage: {
                'pending': Template.search_count(self._get_vehicle_domain(stage, 'pending')),
                'late': Template.search_count(self._get_vehicle_domain(stage, 'late')),
            } for stage in CAT_STAGES
        }

    @api.model
    def get_vehicles(self, query='', state_filter='pending', stage='decontamination'):
        """ Vehicles of a list of the screen.

        :param str stage: 'decontamination' or 'scrap' (dismantling), the received vehicles to
            dismantle, the nearest limit first; or 'vehicles', all of them, the last ones first
        :param str state_filter: of 'decontamination' and 'scrap', 'pending', 'late', 'done' or
            'all'; of 'scrap' also 'subproduct', the subproducts to dismantle; of 'vehicles', 'in_stock', 'on_sale' (to repair and sell, in stock), 'main' (to dismantle), 'refurbish' (to repair and
            sell) or 'all'
        :param str query: license plate, name, internal reference, chassis or make/model
        """
        self._check_vehicle_filter(stage, state_filter)
        domain = self._get_vehicle_domain(stage, state_filter)
        query = query.strip() if isinstance(query, str) else ''
        if query:
            plate = normalize_plate(query) or query
            # A subproduct, also by its vehicle
            domain += ['|', '|', '|', '|', '|', '|', ('scrap_lot_name', 'ilike', plate), ('name', 'ilike', query),
                       ('default_code', 'ilike', query), ('chassis', 'ilike', query),
                       ('vehicle_model_id', 'ilike', query),
                       ('scrap_origin_id.scrap_lot_name', 'ilike', plate),
                       ('scrap_origin_id.default_code', 'ilike', query)]
        vehicles = self.env['product.template'].search(
            domain, limit=VEHICLE_LIMIT, order=self._get_vehicle_order(stage, state_filter))
        return [self._get_vehicle_data(vehicle) for vehicle in vehicles]

    @api.model
    def get_vehicle(self, template_id):
        """ Summary of a vehicle: its data, its deadlines and its purchase. """
        return self._get_vehicle_summary(self._get_vehicle(template_id))

    @api.model
    def mark_vehicle(self, template_id, stage, date=False):
        """ Mark a vehicle as decontaminated or dismantled, today or on `date` (not later than
        today). """
        vehicle = self._get_vehicle(template_id)
        stage_info = self._get_stage(stage)
        today = fields.Date.context_today(self)
        if date:
            try:
                date = fields.Date.to_date(date)
            except (TypeError, ValueError):
                raise ValidationError(self.env._("Invalid date.")) from None
            if date > today:
                raise UserError(self.env._("The date can't be later than today."))
        if vehicle._scrap_is_subproduct():
            # Only dismantled, without decontaminating it, once it can be
            if stage != 'scrap':
                raise UserError(self.env._("%s is a subproduct: it is only dismantled.", vehicle.display_name))
            vehicle._scrap_check_can_dismantle()
        elif vehicle.scrap_unbuild_type != 'main' or not vehicle.discharge_date:
            raise UserError(self.env._("%s isn't a vehicle to dismantle received.", vehicle.display_name))
        elif stage_info.get('requires') and not vehicle[stage_info['requires']]:
            raise UserError(self.env._("%s must be decontaminated before it is dismantled.", vehicle.display_name))
        if vehicle[stage_info['date']]:
            raise UserError(self.env._("%s is already done.", vehicle.display_name))
        vehicle._scrap_write_cat_dates({stage_info['date']: date or today})
        return self._get_vehicle_summary(vehicle)

    @api.model
    def unmark_vehicle(self, template_id, stage):
        """ Undo a decontamination or a dismantling marked by mistake. """
        vehicle = self._get_vehicle(template_id)
        stage_info = self._get_stage(stage)
        if stage == 'decontamination' and vehicle.scrap_date:
            raise UserError(self.env._("%s is dismantled: undo the dismantling first.", vehicle.display_name))
        vehicle._scrap_write_cat_dates({stage_info['date']: False})
        return self._get_vehicle_summary(vehicle)

    @api.model
    def get_dismantle(self, template_id):
        """ The dismantling of a vehicle: the components of its bills of materials still to
        dismantle and the parts already marked. """
        return self._get_dismantle_data(self._get_vehicle(template_id))

    @api.model
    def get_dismantle_locations(self, template_id, query=''):
        """ Internal locations of the company of the vehicle, where a dismantled part can enter
        the stock: its own location first. """
        vehicle = self._get_vehicle(template_id)
        company = vehicle.company_id or self.env.company
        domain = [('usage', '=', 'internal'), ('company_id', 'in', (company.id, False))]
        query = query.strip() if isinstance(query, str) else ''
        if query:
            domain.append(('complete_name', 'ilike', query))
        locations = self.env['stock.location'].search(domain, limit=LOCATION_LIMIT, order='complete_name, id')
        own = vehicle.scrap_location_id.sudo()
        if own and own in locations:
            locations = own | (locations - own)
        return [{'id': location.id, 'name': location.complete_name} for location in locations]

    @api.model
    def dismantle_part(self, template_id, bom_line_id, quantity, result, condition=False, location_id=False):
        """ Mark `quantity` of a component of the vehicle as dismantled (with its condition,
        into `location_id`), missing or discarded. """
        vehicle = self._get_vehicle(template_id)
        if not is_record_id(bom_line_id) or (location_id and not is_record_id(location_id)):
            raise ValidationError(self.env._("Invalid part."))
        if isinstance(quantity, bool) or not isinstance(quantity, (int, float)):
            raise ValidationError(self.env._("Invalid quantity."))
        bom_line = self.env['mrp.bom.line'].sudo().browse(bom_line_id).exists()
        if not bom_line:
            raise UserError(self.env._("The part isn't in the bill of materials of %s anymore.", vehicle.display_name))
        location = self.env['stock.location'].browse(location_id) if location_id else False
        if location:
            location = location.exists()
            location.check_access('read')
        vehicle._scrap_dismantle(bom_line, quantity, result, condition, location)
        return self._get_dismantle_data(vehicle)

    @api.model
    def get_decontamination(self, template_id):
        """ The decontamination of a vehicle: the waste products of the company, to take out as
        many times as needed, and the waste already marked. """
        return self._get_dismantle_data(self._get_vehicle(template_id), 'decontamination')

    @api.model
    def decontaminate_part(self, template_id, product_id, quantity, result, location_id=False):
        """ Mark `quantity` of a waste of the vehicle as discarded (into `location_id`) or
        missing. """
        vehicle = self._get_vehicle(template_id)
        if not is_record_id(product_id) or (location_id and not is_record_id(location_id)):
            raise ValidationError(self.env._("Invalid part."))
        if isinstance(quantity, bool) or not isinstance(quantity, (int, float)):
            raise ValidationError(self.env._("Invalid quantity."))
        product = self.env['product.product'].browse(product_id).exists()
        if not product:
            raise UserError(self.env._("The product doesn't exist anymore."))
        location = self.env['stock.location'].browse(location_id) if location_id else False
        if location:
            location = location.exists()
            location.check_access('read')
        vehicle._scrap_decontaminate(product, quantity, result, location)
        return self._get_dismantle_data(vehicle, 'decontamination')

    @api.model
    def update_decontamination_part(self, template_id, part_id, quantity, result, location_id=False):
        """ Correct a waste marked, until the vehicle is decontaminated. """
        vehicle = self._get_vehicle(template_id)
        if not is_record_id(part_id) or (location_id and not is_record_id(location_id)):
            raise ValidationError(self.env._("Invalid part."))
        if isinstance(quantity, bool) or not isinstance(quantity, (int, float)):
            raise ValidationError(self.env._("Invalid quantity."))
        part = self.env['scrap.dismantle.line'].sudo().browse(part_id).exists()
        if not part:
            raise UserError(self.env._("The part was already undone."))
        location = self.env['stock.location'].browse(location_id) if location_id else False
        if location:
            location = location.exists()
            location.check_access('read')
        vehicle._scrap_update_waste(part, quantity, result, location)
        return self._get_dismantle_data(vehicle, 'decontamination')

    @api.model
    def undo_dismantle_part(self, template_id, part_id):
        """ Undo a part marked by mistake: it is again to dismantle. """
        vehicle = self._get_vehicle(template_id)
        if not is_record_id(part_id):
            raise ValidationError(self.env._("Invalid part."))
        part = self.env['scrap.dismantle.line'].sudo().browse(part_id).exists()
        if not part:
            raise UserError(self.env._("The part was already undone."))
        stage = part.stage
        vehicle._scrap_undo_dismantle(part)
        return self._get_dismantle_data(vehicle, stage)

    # ------------------------------------------------------------------

    def _get_dismantle_data(self, vehicle, stage='dismantling'):
        """ The screen of the decontamination or the dismantling of a vehicle: what can be
        marked (the waste products of the company, or the components left of its bills of
        materials), where it enters the stock by default and what was marked. """
        company = vehicle.company_id or self.env.company
        if stage == 'decontamination':
            location = company.sudo().scrap_waste_location_id
            pending = [{
                'id': product.id,
                'product': product.display_name,
                'product_id': product.id,
                'quantity': 0,
                'uom': product.uom_id.name,
                'operation': '',
                'image_unique': str(product.write_date) if product.image_128 else False,
            } for product in company.sudo().scrap_waste_product_ids]
        else:
            location = vehicle.scrap_location_id.sudo()
            pending = [{
                'id': line.id,
                'product': line.product_id.display_name,
                'product_id': line.product_id.id,
                'quantity': line.product_qty,
                'uom': line.uom_id.name,
                'operation': line.operation_id.name or '',
                'image_unique': str(line.product_id.write_date) if line.product_id.image_128 else False,
            } for line in vehicle._scrap_dismantle_pending_lines()]
        Line = self.env['scrap.dismantle.line']
        results = dict(Line._fields['result']._description_selection(self.env))
        conditions = dict(Line._fields['condition']._description_selection(self.env))
        # The last ones first; of a vehicle, also the ones of its subproducts, dismantled later
        own = vehicle.sudo()
        lines = own.scrap_dismantle_line_ids if own.scrap_origin_id else own.scrap_origin_line_ids
        parts = lines.filtered(lambda part: part.stage == stage).sorted(
            lambda part: (part.date, part.id), reverse=True)[:PART_LIMIT]
        return dict(
            self._get_vehicle_summary(vehicle),
            stage=stage,
            location_id=location.id,
            location_name=location.complete_name or '',
            pending=pending,
            parts=[{
                'id': part.id,
                'product': part.product_id.display_name,
                'product_id': part.product_id.id,
                'quantity': part.quantity,
                'uom': part.uom_id.name,
                'result': part.result,
                'result_label': results.get(part.result, ''),
                'condition_label': conditions.get(part.condition, ''),
                'location': part.location_dest_id.complete_name or '',
                'location_id': part.location_dest_id.id,
                'date': fields.Datetime.to_string(part.date),
                'user': part.user_id.name,
                # Of a subproduct: undone dismantling it
                'source': part.vehicle_id.display_name if part.vehicle_id != own else '',
                # A waste, corrected or removed until the vehicle is decontaminated
                'can_undo': part.vehicle_id == own and (
                    not vehicle.decontamination_date if stage == 'decontamination' else bool(part.bom_line_id.bom_id.active)),
            } for part in parts],
        )

    def _get_stage(self, stage):
        if stage not in CAT_STAGES:
            raise ValidationError(self.env._("Invalid stage."))
        return CAT_STAGES[stage]

    def _check_vehicle_filter(self, stage, state_filter):
        if state_filter not in VEHICLE_FILTERS.get(stage, ()):
            raise ValidationError(self.env._("Invalid filter."))

    def _get_vehicle_domain(self, stage, state_filter):
        company_domain = self.env['product.template']._check_company_domain(self.env.company)
        if stage == 'vehicles':
            domain = [('scrap_template_id', '!=', False), *company_domain]
            if state_filter == 'in_stock':
                domain.append(('qty_available', '>', 0))
            elif state_filter == 'on_sale':
                domain += [('scrap_unbuild_type', '=', 'refurbish'), ('qty_available', '>', 0)]
            elif state_filter in ('main', 'refurbish'):
                domain.append(('scrap_unbuild_type', '=', state_filter))
            return domain
        if stage == 'scrap' and state_filter == 'subproduct':
            # With something to dismantle: made of a scrap template with bills of materials,
            # dismantled from another product or bought and received
            return [('scrap_unbuild_type', '=', 'subproduct'), ('scrap_template_id', '!=', False),
                    ('is_template', '=', False), ('bom_ids', '!=', False),
                    '|', ('scrap_origin_id', '!=', False), ('discharge_date', '!=', False), *company_domain]
        stage_info = self._get_stage(stage)
        domain = [('scrap_unbuild_type', '=', 'main'), ('discharge_date', '!=', False), *company_domain]
        pending = [(stage_info['date'], '=', False)]
        if stage_info.get('requires'):
            pending.append((stage_info['requires'], '!=', False))
        if state_filter == 'pending':
            domain += pending
        elif state_filter == 'late':
            domain += [*pending, (stage_info['limit'], '<', fields.Date.context_today(self))]
        elif state_filter == 'done':
            domain.append((stage_info['date'], '!=', False))
        return domain

    def _get_vehicle_order(self, stage, state_filter):
        if stage == 'vehicles':
            return 'create_date desc, id desc'
        if stage == 'scrap' and state_filter == 'subproduct':
            # The ones to dismantle first
            return 'scrap_date desc nulls first, create_date desc, id desc'
        stage_info = self._get_stage(stage)
        if state_filter == 'done':
            return f"{stage_info['date']} desc, id desc"
        return f"{stage_info['limit']} asc nulls last, discharge_date asc, id"

    def _get_vehicle(self, template_id):
        if not is_record_id(template_id):
            raise ValidationError(self.env._("Invalid vehicle."))
        vehicle = self.env['product.template'].browse(template_id).exists()
        if not vehicle or not vehicle.scrap_template_id:
            raise ValidationError(self.env._("The vehicle doesn't exist anymore."))
        vehicle.check_access('read')
        return vehicle

    def _get_vehicle_data(self, vehicle):
        unbuild_types = dict(vehicle._fields['scrap_unbuild_type']._description_selection(self.env))
        return {
            'id': vehicle.id,
            'name': vehicle.display_name,
            'plate': vehicle.scrap_lot_name or '',
            'ref': vehicle.default_code or '',
            'model': vehicle.vehicle_model_id.display_name or '',
            'unbuild_type': vehicle.scrap_unbuild_type or False,
            'unbuild_type_label': unbuild_types.get(vehicle.scrap_unbuild_type, ''),
            'is_subproduct': vehicle._scrap_is_subproduct(),
            # What a subproduct was dismantled from at first: a vehicle or a subproduct bought
            'origin': vehicle.scrap_origin_id.display_name or '',
            'origin_plate': vehicle.scrap_origin_id.scrap_lot_name or '',
            'discharge_date': fields.Date.to_string(vehicle.discharge_date) or False,
            'decontamination_limit_date': fields.Date.to_string(vehicle.decontamination_limit_date) or False,
            'decontamination_date': fields.Date.to_string(vehicle.decontamination_date) or False,
            'decontamination_days_left': vehicle.decontamination_days_left,
            'scrap_limit_date': fields.Date.to_string(vehicle.scrap_limit_date) or False,
            'scrap_date': fields.Date.to_string(vehicle.scrap_date) or False,
            'scrap_days_left': vehicle.scrap_days_left,
            'qty_available': vehicle.qty_available,
            'product_id': vehicle.product_variant_id.id,
            # Changes with the image, so that the browser cache is refreshed
            'image_unique': str(vehicle.write_date) if vehicle.image_128 else False,
        }

    def _get_vehicle_summary(self, vehicle):
        """ The data of a vehicle, with the details of its summary. """
        product = vehicle.product_variant_id
        line = self.env['purchase.order.line'].search(
            [('product_id', '=', product.id), ('state', '=', 'purchase')], limit=1, order='id desc')
        return dict(
            self._get_vehicle_data(vehicle),
            model_name=vehicle._name,
            template=vehicle.scrap_template_id.display_name,
            chassis=vehicle.chassis or '',
            location=vehicle.scrap_location_id.sudo().display_name or '',
            purchase=line.order_id.name or '',
            partner=line.order_id.partner_id.display_name or '',
            pending_parts=len(vehicle._scrap_dismantle_pending_lines()),
            dismantled_parts=len(vehicle.sudo().scrap_dismantle_line_ids.filtered(lambda part: part.stage == 'dismantling')),
            waste_parts=len(vehicle.sudo().scrap_dismantle_line_ids.filtered(lambda part: part.stage == 'decontamination')),
            waste_products=len((vehicle.company_id or self.env.company).sudo().scrap_waste_product_ids),
            boms=[{
                'name': bom.code or bom.display_name,
                'components': len(bom.bom_line_ids),
                'operations': len(bom.operation_ids),
            } for bom in vehicle.sudo().bom_ids],
        )
