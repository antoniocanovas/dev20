from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


class MeatCarcassRegister(models.TransientModel):
    _name = 'meat.carcass.register'
    _description = "Register Carcasses"

    picking_id = fields.Many2one('stock.picking', 'Receipt', required=True, readonly=True)
    company_id = fields.Many2one(related='picking_id.company_id')
    product_ids = fields.Many2many('product.product', compute='_compute_product_ids')
    default_product_id = fields.Many2one('product.product', compute='_compute_product_ids')
    # Data shared by the carcasses of a same slaughter batch
    partner_id = fields.Many2one('res.partner', 'Slaughterhouse', check_company=True)
    supplier_health_code = fields.Char('Supplier Health ID')
    slaughter_date = fields.Date('Slaughter Date', default=fields.Date.context_today)
    slaughter_order = fields.Char('Order', help="Slaughterhouse reference.")
    birth_country = fields.Char('Born In', help="Default of the carcasses.")
    reared_country = fields.Char('Reared In', help="Default of the carcasses.")
    halal = fields.Boolean(help="Default of the carcasses.")
    halal_certifier = fields.Char('Halal Certifier')
    halal_certificate = fields.Char('Halal Certificate')
    line_ids = fields.One2many('meat.carcass.register.line', 'register_id', 'Carcasses')

    @api.depends('picking_id')
    def _compute_product_ids(self):
        for register in self:
            moves = register.picking_id.move_ids.filtered(
                lambda m: m.state not in ('done', 'cancel') and m.product_id.tracking == 'lot')
            register.product_ids = moves.product_id
            register.default_product_id = len(moves.product_id) == 1 and moves.product_id

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """ The health ID of the slaughterhouse, as in its last crotal. """
        if self.partner_id:
            last_crotal = self.env['stock.crotal'].search([
                ('partner_id', '=', self.partner_id.id),
                ('supplier_health_code', '!=', False),
                ('company_id', '=', self.company_id.id),
            ], limit=1)
            self.supplier_health_code = last_crotal.supplier_health_code

    def action_confirm(self):
        """ Create the crotal and the lot (named after it) of each carcass, and
        receive it with its real weight. """
        self.ensure_one()
        picking = self.picking_id
        if picking.state in ('done', 'cancel'):
            raise UserError(self.env._("The receipt %s is already done or cancelled.", picking.display_name))
        if not self.line_ids:
            raise UserError(self.env._("Add at least one carcass."))
        names = self.line_ids.mapped('name')
        if duplicates := {name for name in names if names.count(name) > 1}:
            raise UserError(self.env._("The crotal %s is repeated.", ', '.join(sorted(duplicates))))

        move_line_vals = []
        moves = self.env['stock.move']
        for line in self.line_ids:
            move = picking.move_ids.filtered(
                lambda m: m.product_id == line.product_id and m.state not in ('done', 'cancel'))[:1]
            if not move:
                raise UserError(self.env._(
                    "The receipt %(picking)s does not receive %(product)s.",
                    picking=picking.display_name, product=line.product_id.display_name))
            if line.product_id.uom_id.compare(line.weight, 0) <= 0:
                raise UserError(self.env._("Enter the weight of the carcass %s.", line.name))
            lot = line._get_lot(line._get_crotal())
            moves |= move
            move_line_vals.append({
                'picking_id': picking.id,
                'move_id': move.id,
                'product_id': line.product_id.id,
                'lot_id': lot.id,
                'quantity': line.weight,
                'uom_id': line.product_id.uom_id.id,
                'location_id': move.location_id.id,
                'location_dest_id': move.location_dest_id.id,
            })
        # The lines reserved without lot are replaced by the carcasses
        moves.move_line_ids.filtered(lambda ml: not ml.lot_id and not ml.lot_name).unlink()
        self.env['stock.move.line'].create(move_line_vals)
        moves.picked = True
        return {'type': 'ir.actions.act_window_close'}


class MeatCarcassRegisterLine(models.TransientModel):
    _name = 'meat.carcass.register.line'
    _description = "Carcass to Register"

    register_id = fields.Many2one('meat.carcass.register', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', 'Product', required=True)
    name = fields.Char('Crotal', required=True)
    weight = fields.Float('Weight', digits='Product Unit', required=True)
    uom_id = fields.Many2one(related='product_id.uom_id')
    sex = fields.Selection([('male', 'Male'), ('female', 'Female')])
    breed = fields.Char()
    quality = fields.Char()
    birth_date = fields.Date()
    birth_country = fields.Char('Born In')
    reared_country = fields.Char('Reared In')
    halal = fields.Boolean()

    def _get_crotal(self):
        """ The crotal of the animal, created on receipt. One that was not
        received yet (no lots) is completed with the receipt data. """
        self.ensure_one()
        register = self.register_id
        company = register.company_id
        vals = {
            'product_id': self.product_id.id,
            'partner_id': register.partner_id.id,
            'supplier_health_code': register.supplier_health_code,
            'slaughter_date': register.slaughter_date,
            'slaughter_order': register.slaughter_order,
            'sex': self.sex,
            'breed': self.breed,
            'quality': self.quality,
            'birth_date': self.birth_date,
            'birth_country': self.birth_country,
            'reared_country': self.reared_country,
            'halal': self.halal,
            'halal_certifier': self.halal and register.halal_certifier,
            'halal_certificate': self.halal and register.halal_certificate,
        }
        crotal = self.env['stock.crotal'].search([('name', '=', self.name), ('company_id', '=', company.id)], limit=1)
        if not crotal:
            return crotal.create(dict(vals, name=self.name, company_id=company.id))
        if crotal.lot_ids:
            raise UserError(self.env._("The crotal %s has already been received.", self.name))
        crotal.write(vals)
        return crotal

    def _get_lot(self, crotal):
        """ The lot of the carcass is named after its crotal. It expires
        counting from the slaughter. """
        self.ensure_one()
        product = self.product_id
        company = self.register_id.company_id
        lot = self.env['stock.lot'].search([
            ('name', '=', crotal.name),
            ('product_id', '=', product.id),
            ('company_id', 'in', [company.id, False]),
        ], limit=1)
        vals = {'crotal_id': crotal.id}
        slaughter_date = self.register_id.slaughter_date
        if product.use_expiration_date and slaughter_date:
            vals['expiration_date'] = fields.Datetime.to_datetime(slaughter_date) + timedelta(
                days=product.expiration_time)
        if lot:
            lot.write(vals)
            return lot
        return lot.create(dict(vals, name=crotal.name, product_id=product.id, company_id=company.id))
