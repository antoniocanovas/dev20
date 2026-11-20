from odoo import fields, models


class StockPackageType(models.Model):
    _inherit = "stock.package.type"

    mercas_is_pallet = fields.Boolean(
        string="Pallet",
        help="Package type of the pallets of a sale: the boxes of its lines "
             "are spread over pallets of these types, and the packing list "
             "shows each pallet as a package.",
    )
    mercas_box_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Box Product",
        domain=[("is_box", "=", True)],
        help="Returnable container of this pallet type: each pallet of a sale "
             "adds one unit of this product to the sale, as the boxes do, so "
             "it counts in the box balance of the customer. Leave it empty "
             "for single-use pallets. The tare of the boxes is the weight of "
             "their box product.",
    )
