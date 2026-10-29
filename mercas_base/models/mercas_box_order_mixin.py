from odoo import models


class MercasBoxOrderMixin(models.AbstractModel):
    """PRODUCTOS/Envases sections and one box line per product line with
    boxes, the same for sales and purchases: each order says which field
    links a box line to its product line and which one holds its quantity."""

    _name = "mercas.box.order.mixin"
    _description = "Order with Box Lines"

    _mercas_box_link_field = None
    _mercas_box_qty_field = None
    _mercas_section_vals = {}

    def _mercas_product_lines(self):
        link = self._mercas_box_link_field
        return self.order_line.filtered(lambda l: not l.display_type and not l[link])

    def _mercas_box_lines_by_parent(self):
        link = self._mercas_box_link_field
        return {bl[link].id: bl for bl in self.order_line.filtered(lambda l: l[link])}

    def _mercas_section(self, name):
        """The section called `name`, created at the start if missing."""
        section = self.order_line.filtered(
            lambda l: l.display_type == "line_section" and l.name == name
        )[:1]
        return section or self.order_line.create({
            "order_id": self.id,
            "display_type": "line_section",
            "name": name,
            "sequence": 0,
            **self._mercas_section_vals,
        })

    def _mercas_prepare_box_lines(self):
        """Add PRODUCTOS/Envases sections, create/refresh one box line per
        product line with box_qty > 0, and re-sequence every line so it
        stays inside the section it belongs to. Runs again after confirm
        (from line create/write) so lines added later are grouped too,
        instead of trailing after Envases where the UI appends new rows."""
        product_lines = self._mercas_product_lines()
        has_productos = self.order_line.filtered(
            lambda l: l.display_type == "line_section" and l.name == "PRODUCTOS"
        )
        box_lines_needed = product_lines.filtered(
            lambda l: l.box_qty > 0 and l.box_product_id
        )
        if not product_lines or (not box_lines_needed and not has_productos):
            return

        productos_section = self._mercas_section("PRODUCTOS")
        envases_section = self._mercas_section("Envases")

        existing_by_parent = self._mercas_box_lines_by_parent()
        for line in box_lines_needed:
            vals = {
                "product_id": line.box_product_id.id,
                self._mercas_box_qty_field: line.box_qty,
            }
            if line.id in existing_by_parent:
                existing_by_parent[line.id].write(vals)
            else:
                self.order_line.create({
                    **vals,
                    "order_id": self.id,
                    self._mercas_box_link_field: line.id,
                })

        self._mercas_reorder_box_sections(productos_section, envases_section)

    def _mercas_reorder_box_sections(self, productos_section, envases_section):
        """Renumber sequence so every line sits inside its section: PRODUCTOS,
        then all product lines (keeping their current relative order), then
        Envases, then all box lines (following their parent line's order)."""
        product_lines = self._mercas_product_lines().sorted(key=lambda l: (l.sequence, l.id))
        box_lines_by_parent = self._mercas_box_lines_by_parent()

        seq = 0
        productos_section.sequence = seq
        for line in product_lines:
            seq += 10
            line.sequence = seq

        seq += 10
        envases_section.sequence = seq

        for line in product_lines:
            box_line = box_lines_by_parent.get(line.id)
            if box_line:
                seq += 10
                box_line.sequence = seq
