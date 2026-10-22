from odoo import api, fields, models
from odoo.tools import SQL


class PurchaseBillUnion(models.Model):
    _inherit = "purchase.bill.union"
    _rec_names_search = ("name", "reference", "mercas_receipts")

    mercas_receipts = fields.Char(
        string="Receipts",
        readonly=True,
        help="Receipts of the purchase order, with the supplier's delivery note.",
    )

    @property
    def _table_sql(self):
        # The receipts (not cancelled) of each purchase order, as
        # "WH/IN/00001 (supplier delivery note), ..."; none for the bills
        return SQL(
            """(
                SELECT bill_union.*,
                       (SELECT string_agg(
                                   picking.name || COALESCE(' (' || NULLIF(picking.supplier_ref, '') || ')', ''),
                                   ', ' ORDER BY picking.id)
                          FROM stock_picking picking
                          JOIN stock_picking_type picking_type ON picking_type.id = picking.picking_type_id
                         WHERE picking_type.code = 'incoming'
                           AND picking.state != 'cancel'
                           AND picking.id IN (
                               SELECT move.picking_id
                                 FROM stock_move move
                                 JOIN purchase_order_line line ON line.id = move.purchase_line_id
                                WHERE line.order_id = bill_union.purchase_order_id
                           )
                       ) AS mercas_receipts
                  FROM %s bill_union
            )""",
            super()._table_sql,
            to_flush=[
                self.env[model]._fields[fname]
                for model, fnames in (
                    ("stock.picking", ("name", "supplier_ref", "state", "picking_type_id")),
                    ("stock.picking.type", ("code",)),
                    ("stock.move", ("picking_id", "purchase_line_id")),
                    ("purchase.order.line", ("order_id",)),
                )
                for fname in fnames
            ],
        )

    @api.depends("mercas_receipts")
    def _compute_display_name(self):
        super()._compute_display_name()
        for doc in self.filtered("mercas_receipts"):
            # The receipts go with the date, under the reference in the dropdown
            separator = " · " if self.env.context.get("formatted_display_name") else " - "
            doc.display_name = f"{doc.display_name}{separator}{doc.mercas_receipts}"
