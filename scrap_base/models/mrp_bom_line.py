from odoo import fields, models


class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'

    scrap_added = fields.Boolean(
        "Added While Dismantling", copy=False, readonly=True,
        help="Part found while dismantling the vehicle, not foreseen in its bill of materials: "
             "added by the operator on the touch screen.")
    # On a vehicle, as its quantity, what is left: the share of the parts dismantled goes with
    # them, and the one of the parts discarded or missing, to the ones still to dismantle
    scrap_cost_share = fields.Float(
        "Scrap Cost Share (%)",
        help="Share of the cost of the vehicle given to this component when it is dismantled, "
             "divided between its quantity. The lines of a scrap template must add up to 100%. "
             "On a vehicle, the share still to dismantle.")
