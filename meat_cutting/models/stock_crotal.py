from odoo import api, fields, models


class StockCrotal(models.Model):
    _name = 'stock.crotal'
    _description = "Crotal"
    _inherit = ['mail.thread']
    _order = 'slaughter_date desc, id desc'

    name = fields.Char('Crotal', required=True, tracking=True, help="Unique identifier of the source animal.")
    company_id = fields.Many2one('res.company', required=True, index=True, default=lambda self: self.env.company)
    product_id = fields.Many2one('product.product', 'Product', check_company=True)
    slaughter_date = fields.Date('Slaughter Date')
    slaughter_order = fields.Char('Order', help="Slaughterhouse reference.")
    quality = fields.Char()
    birth_date = fields.Date()
    partner_id = fields.Many2one('res.partner', 'Supplier', check_company=True)
    supplier_health_code = fields.Char('Supplier Health ID')
    supplier_city = fields.Char(
        'City', compute='_compute_supplier_data', store=True, readonly=False)
    supplier_vat = fields.Char(
        'Tax ID', compute='_compute_supplier_data', store=True, readonly=False)
    sex = fields.Selection([('male', 'Male'), ('female', 'Female')])
    halal = fields.Boolean(tracking=True, help="The animal was slaughtered following the halal rite.")
    halal_certifier = fields.Char('Halal Certifier')
    halal_certificate = fields.Char('Halal Certificate')
    label = fields.Char()
    breed = fields.Char()
    notes = fields.Char('Observations')
    birth_country = fields.Char('Born In')
    reared_country = fields.Char('Reared In')
    lot_ids = fields.One2many('stock.lot', 'crotal_id', 'Lots')
    lot_count = fields.Integer(compute='_compute_lot_count')

    _name_company_uniq = models.Constraint(
        'UNIQUE (name, company_id)',
        "The crotal must be unique per company.",
    )

    @api.depends('partner_id')
    def _compute_supplier_data(self):
        for crotal in self:
            crotal.supplier_city = crotal.partner_id.city
            crotal.supplier_vat = crotal.partner_id.vat

    @api.depends('lot_ids')
    def _compute_lot_count(self):
        for crotal in self:
            crotal.lot_count = len(crotal.lot_ids)

    def action_view_lots(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('stock.action_production_lot_form')
        action['domain'] = [('crotal_id', '=', self.id)]
        action['context'] = {'default_crotal_id': self.id}
        return action
