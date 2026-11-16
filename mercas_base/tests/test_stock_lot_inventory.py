from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestStockLotInventory(TransactionCase):
    """Inventory of a lot from its form: the counted quantity becomes the
    on-hand quantity through a standard inventory adjustment."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create({
            "name": "Inventory Product",
            "type": "consu",
            "is_storable": True,
            "tracking": "lot",
            "uom_id": cls.env.ref("uom.product_uom_kgm").id,
        })
        cls.lot = cls.env["stock.lot"].create({
            "name": "INV-1",
            "product_id": cls.product.id,
            "company_id": cls.env.company.id,
        })
        cls.stock = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        ).lot_stock_id
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.stock, 100.0, lot_id=cls.lot
        )
        cls.user = new_test_user(
            cls.env, login="lot_inventory_user",
            groups="stock.group_stock_user,stock.group_production_lot",
        )

    def _count(self, qty):
        lot = self.lot.with_user(self.user)
        action = lot.action_open_inventory()
        wizard = self.env[action["res_model"]].with_user(self.user).with_context(
            action["context"]
        ).create({})
        self.assertEqual(wizard.location_id, self.stock)
        self.assertEqual(wizard.current_qty, self.lot.product_qty)
        wizard.counted_qty = qty
        wizard.action_apply()
        self.lot.invalidate_recordset()

    def test_inventory_down_counts_as_scrap(self):
        self._count(80.0)
        self.assertEqual(self.lot.product_qty, 80.0)
        self.assertEqual(self.lot.scrap_kg, 20.0)
        move = self.lot.stock_move_line_ids.filtered(
            lambda ml: ml.location_dest_id.usage == "inventory"
        ).move_id
        self.assertTrue(move.is_inventory)
        self.assertIn("INV-1", move.reference)

    def test_inventory_up_and_unchanged(self):
        self._count(80.0)
        self._count(90.0)
        self.assertEqual(self.lot.product_qty, 90.0)
        self.assertEqual(self.lot.scrap_kg, 10.0, "The gain offsets part of the loss")
        moves = self.lot.stock_move_line_ids
        self._count(90.0)
        self.lot.invalidate_recordset()
        self.assertEqual(self.lot.stock_move_line_ids, moves, "Same count: no move")

    def test_inventory_lot_without_stock(self):
        self._count(0.0)
        self.assertEqual(self.lot.product_qty, 0.0)
        self._count(15.0)
        self.assertEqual(self.lot.product_qty, 15.0)

    def test_negative_count_refused(self):
        with self.assertRaises(UserError):
            self.lot._mercas_apply_inventory(-1.0, self.stock)
