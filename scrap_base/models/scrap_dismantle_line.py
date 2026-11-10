from odoo import api, fields, models

DISMANTLE_RESULTS = [
    ('dismantled', 'Removed'),
    ('missing', 'Missing'),
    ('discarded', 'Discarded'),
]
PART_CONDITIONS = [
    ('excellent', 'Excellent'),
    ('good', 'Good'),
    ('half_life', 'Half Life'),
    ('functional', 'Functional'),
]


class ScrapDismantleLine(models.Model):
    """ A part or a waste of a vehicle, marked by the operator. Decontaminating it, a waste of
    the company (oil, fuel...): discarded, into the waste zone, or missing. Dismantling it, a
    component of its bill of materials: dismantled (it enters the stock of its location),
    missing (the vehicle hasn't it) or discarded (it goes to the scrap location). """
    _name = 'scrap.dismantle.line'
    _description = "Vehicle Part or Waste"
    _order = 'date desc, id desc'
    _check_company_auto = True

    vehicle_id = fields.Many2one(
        'product.template', string="Vehicle", required=True, index=True, ondelete='cascade',
        check_company=True)
    origin_id = fields.Many2one(
        'product.template', string="Origin", compute='_compute_origin_id',
        store=True, index=True,
        help="What the part comes from at first: the vehicle (or the subproduct bought) "
             "dismantled or, if it was dismantled from a subproduct, the origin of that one.")
    company_id = fields.Many2one('res.company', string="Company", required=True, index=True,
                                 default=lambda self: self.env.company)
    stage = fields.Selection(
        [('decontamination', 'Decontamination'), ('dismantling', 'Dismantling')], string="Stage",
        required=True, default='dismantling', index=True)
    product_id = fields.Many2one('product.product', string="Part", required=True, check_company=True)
    bom_line_id = fields.Many2one('mrp.bom.line', string="BoM Line", ondelete='set null')
    quantity = fields.Float("Quantity", digits='Product Unit', required=True, default=1.0)
    uom_id = fields.Many2one('uom.uom', string="Unit", required=True)
    result = fields.Selection(DISMANTLE_RESULTS, string="Result", required=True)
    condition = fields.Selection(
        PART_CONDITIONS, string="Condition",
        help="Condition of the dismantled part.")
    location_dest_id = fields.Many2one(
        'stock.location', string="Destination", check_company=True,
        help="Where the part dismantled, or the waste, enters the stock; by default, the location "
             "of the vehicle, or the waste zone of the company.")
    move_id = fields.Many2one('stock.move', string="Stock Move", readonly=True)
    date = fields.Datetime("Date", required=True, default=fields.Datetime.now)
    user_id = fields.Many2one('res.users', string="Operator", required=True,
                              default=lambda self: self.env.user)

    _quantity_positive = models.Constraint('CHECK (quantity > 0)', "The quantity must be positive.")

    @api.depends('vehicle_id.scrap_origin_id')
    def _compute_origin_id(self):
        for line in self:
            line.origin_id = line.vehicle_id.scrap_origin_id or line.vehicle_id

    @api.depends('product_id', 'result')
    def _compute_display_name(self):
        results = dict(self._fields['result']._description_selection(self.env))
        for line in self:
            line.display_name = f"{line.product_id.display_name} ({results.get(line.result, '')})"
