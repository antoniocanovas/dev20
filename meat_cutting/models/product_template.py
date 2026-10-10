from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    frozen_product_id = fields.Many2one(
        'product.product', 'Frozen Product', check_company=True,
        domain="[('id', 'not in', product_variant_ids), ('uom_id', '=', uom_id)]",
        help="Same cut sold frozen, with its own price and expiration dates. The cutting screen produces it "
             "instead of this product when the cut is marked to freeze.")
    meat_piece = fields.Boolean(
        'Whole Pieces',
        help="Handled in whole pieces of variable weight. Each weighing of the cutting screen is one piece, put "
             "in its own package, and each carcass registered on receipt is one piece (its lot). A piece received "
             "or delivered counts as one piece whatever its weight.")
