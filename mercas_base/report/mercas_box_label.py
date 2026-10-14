from odoo import api, models

#: print_format -> (columns, rows, page padding), same grids and paddings
#: as the standard product labels (product.report_productlabel).
_SHEET_LAYOUTS = {
    "2x7xprice": (2, 7, "padding: 14mm 3mm"),
    "4x7xprice": (4, 7, "padding: 14mm 3mm"),
    "4x12": (4, 12, "padding: 20mm 8mm"),
    "4x12xprice": (4, 12, "padding: 20mm 8mm"),
}


class ReportMercasBoxLabel(models.AbstractModel):
    """One label per box: product, lot (with its barcode), expiration and
    origin. Fed by mercas.label.print.wizard with
    ``data = {'print_format': ..., 'labels': [[product_id, lot_id, qty], ...]}``."""

    _name = "report.mercas_base.report_mercas_box_label"
    _description = "Mercas Box Label"

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        print_format = data.get("print_format") or "4x12"
        Product = self.env["product.product"].with_context(display_default_code=False)
        Lot = self.env["stock.lot"]
        has_expiration = "expiration_date" in Lot._fields

        labels = []
        for product_id, lot_id, qty in data.get("labels") or []:
            product = Product.browse(product_id)
            lot = Lot.browse(lot_id) if lot_id else Lot
            origin = ", ".join(
                name for name in (lot.origin_state_id.name, lot.origin_country_id.name) if name
            )
            label = {
                "product": product,
                "lot": lot,
                "expiration": lot.expiration_date if has_expiration and lot else False,
                "origin": origin,
                # The lot is what gets scanned in the warehouse; a box
                # without a lot falls back to the product's own barcode.
                "barcode": lot.name or product.barcode or "",
            }
            labels.extend([label] * max(int(qty), 0))

        values = {
            "labels": labels,
            "print_format": print_format,
            "with_price": "xprice" in print_format,
            "company": self.env.company,
        }
        if print_format in _SHEET_LAYOUTS:
            columns, rows, padding = _SHEET_LAYOUTS[print_format]
            per_page = columns * rows
            pages = []
            for start in range(0, len(labels), per_page):
                chunk = labels[start:start + per_page]
                chunk += [None] * (per_page - len(chunk))
                pages.append([chunk[r * columns:(r + 1) * columns] for r in range(rows)])
            values.update({"pages": pages, "padding_page": padding})
        return values


class ReportMercasBoxLabelDymo(models.AbstractModel):
    _name = "report.mercas_base.report_mercas_box_label_dymo"
    _inherit = "report.mercas_base.report_mercas_box_label"
    _description = "Mercas Box Label (Dymo)"
