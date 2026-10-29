from odoo import api, fields, models
from odoo.exceptions import UserError

# Transport data of the DeCA copied from the last delivery of the customer
CARRIER_FIELDS = ('carrier_contact_id', 'tractor_license_plate', 'trailer_license_plate')


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    mercas_deca_missing = fields.Text(
        compute='_compute_mercas_deca_missing',
        help="Data still missing to print the DeCA.")

    @api.depends('carrier_contact_id.vat', 'tractor_license_plate', 'partner_id.vat', 'deca_weight')
    def _compute_mercas_deca_missing(self):
        for picking in self:
            try:
                picking._check_deca_required_fields()
                picking.mercas_deca_missing = False
            except UserError as error:
                picking.mercas_deca_missing = error.args[0]

    @api.model_create_multi
    def create(self, vals_list):
        pickings = super().create(vals_list)
        for picking, vals in zip(pickings, vals_list):
            if picking.picking_type_code == 'outgoing' and not any(vals.get(name) for name in CARRIER_FIELDS):
                picking._mercas_set_default_carrier()
        return pickings

    def _mercas_set_default_carrier(self):
        """ The carrier of the DeCA proposed by the company (`mercas_default_carrier`): the one
        of the last delivery of the customer, with its licence plates, or the customer. """
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        mode = self.company_id.mercas_default_carrier
        if not partner or mode == 'none':
            return
        if mode == 'customer':
            self.carrier_contact_id = partner
            return
        last = self.search([
            ('id', '!=', self.id),
            ('partner_id', 'child_of', partner.id),
            ('picking_type_code', '=', 'outgoing'),
            ('company_id', '=', self.company_id.id),
            ('carrier_contact_id', '!=', False),
            ('state', '!=', 'cancel'),
        ], order='id desc', limit=1)
        if last:
            self.write({name: last[name].id if name == 'carrier_contact_id' else last[name]
                        for name in CARRIER_FIELDS})

    def _mercas_prepare_deca(self):
        """ Before the DeCA dialog: the carrier proposed, if none was set yet, and the weight of
        the moves made before l10n_es_deca_oca was installed, which it doesn't compute. """
        self.ensure_one()
        if not any(self[name] for name in CARRIER_FIELDS):
            self._mercas_set_default_carrier()
        if not self.deca_weight:
            self.env.add_to_compute(self.move_ids._fields['deca_weight'], self.move_ids)
            self.env.add_to_compute(self._fields['deca_weight'], self)
            self.flush_recordset(['deca_weight'])

    def action_mercas_print_deca(self):
        """ Print the DeCA from its dialog, which closes once downloaded. """
        self.ensure_one()
        self._check_deca_required_fields()
        action = self.env.ref('l10n_es_deca_oca.action_report_deca').report_action(self)
        action['close_on_report_download'] = True
        return action
