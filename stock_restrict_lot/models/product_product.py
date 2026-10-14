# Copyright 2023 Michael Tietz (MT Software) <mtietz@mt-software.de>
# License LGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models
from odoo.fields import Domain


class ProductProduct(models.Model):
    _inherit = "product.product"

    # To be able to get the outgoing and incoming qty by the restrict_lot_id
    # _get_domain_locations injects restrict_lot_id into the move location domains.
    # _compute_quantities_dict passes lot_id=None to super() so that the standard
    # move_line_ids.lot_id filter is not added (it would exclude pending moves with
    # no move lines yet); our _get_domain_locations() handles the filtering instead.
    def _get_domain_locations(self):
        res = super()._get_domain_locations()
        lot_id = self.env.context.get("lot_id")
        if not lot_id:
            return res
        (
            domain_quant_loc,
            domain_move_in_loc,
            domain_move_out_loc,
            domain_move_in_loc_done,
            domain_move_out_loc_done,
        ) = res
        # Quants and done move lines have their own lot, pending moves only
        # the lot they are restricted to
        line_lot_domain = Domain("lot_id", "=", lot_id)
        move_lot_domain = Domain("restrict_lot_id", "=", lot_id)
        return (
            Domain(domain_quant_loc) & line_lot_domain,
            Domain(domain_move_in_loc) & move_lot_domain,
            Domain(domain_move_out_loc) & move_lot_domain,
            Domain(domain_move_in_loc_done) & line_lot_domain,
            Domain(domain_move_out_loc_done) & line_lot_domain,
        )

    def _compute_quantities_dict(
        self, lot_id, owner_id, package_id, from_date=False, to_date=False
    ):
        # A non-None lot_id adds a move_line_ids.lot_id filter that
        # excludes pending moves without lines yet. We put lot_id in context
        # so _get_domain_locations() handles the restrict_lot_id filtering,
        # and pass None to super() to skip that extra filter.
        if lot_id:
            self = self.with_context(lot_id=lot_id)
            lot_id = None
        return super()._compute_quantities_dict(
            lot_id, owner_id, package_id, from_date, to_date
        )
