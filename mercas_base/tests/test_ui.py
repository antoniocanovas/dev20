from odoo import Command
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestMercasBaseUi(HttpCase):

    def test_sale_order_widgets(self):
        """The widgets of the sale order lines: date of the last change of the
        quantity, and the stock popover with the lots of sale_order_lot_selection."""
        self.env.ref("base.group_user").sudo()._apply_group(self.env.ref("stock.group_production_lot"))
        product = self.env["product.product"].create({
            "name": "Smoke Pear",
            "type": "consu",
            "is_storable": True,
            "tracking": "lot",
        })
        lot = self.env["stock.lot"].create({"name": "SMOKE-LOT", "product_id": product.id})
        self.env["stock.quant"]._update_available_quantity(
            product, self.env.ref("stock.stock_location_stock"), 50, lot_id=lot)
        partner = self.env["res.partner"].create({"name": "Smoke Customer"})
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "order_line": [Command.create({"product_id": product.id, "product_uom_qty": 5})],
        })
        self.start_tour(
            f"/odoo/action-sale.action_quotations_with_onboarding/{order.id}",
            "mercas_base_sale_order_tour", login="admin",
        )
