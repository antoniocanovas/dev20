from odoo import api, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _is_invoiced_in_product_uom(self):
        """ Lines ordered in a packaging of the product (e.g. whole pieces of
        an estimated weight) and invoiced on delivery are invoiced in the unit
        of the product (kg), with the real quantity delivered: converting it
        back into packagings would round it and hide the weight. """
        self.ensure_one()
        return (
            not self.display_type
            and self.product_id.type != 'combo'
            and self.invoice_policy == 'delivery'
            and self.qty_delivered_method == 'stock_move'
            and self.product_uom_id != self.product_id.uom_id
        )

    def _get_qty_delivered_in_product_uom(self):
        """ Delivered quantity in the unit of the product, without rounding. """
        self.ensure_one()
        product_uom = self.product_id.uom_id
        outgoing_moves, incoming_moves = self._get_outgoing_incoming_moves()
        quantity = sum(
            move.uom_id._compute_quantity(move.quantity, product_uom, round=False)
            for move in outgoing_moves if move.state == 'done'
        )
        quantity -= sum(
            move.uom_id._compute_quantity(move.quantity, product_uom, round=False)
            for move in incoming_moves
            if move.state == 'done' and (move.origin_returned_move_id or move.location_id._is_outgoing())
        )
        return quantity

    def _get_qty_invoiced_in_product_uom(self):
        self.ensure_one()
        product_uom = self.product_id.uom_id
        quantity = 0.0
        for invoice_line in self._get_invoice_lines():
            if invoice_line.move_id.state == 'cancel' or not self._affects_qty_invoiced(invoice_line):
                continue
            invoice_qty = invoice_line.product_uom_id._compute_quantity(invoice_line.quantity, product_uom, round=False)
            if invoice_line.move_id.move_type == 'out_invoice':
                quantity += invoice_qty
            elif invoice_line.move_id.move_type == 'out_refund':
                quantity -= invoice_qty
        return quantity

    def _get_qty_to_invoice_in_product_uom(self):
        self.ensure_one()
        return self.product_id.uom_id.round(
            self._get_qty_delivered_in_product_uom() - self._get_qty_invoiced_in_product_uom())

    @api.depends('move_ids.state', 'move_ids.quantity')
    def _compute_qty_to_invoice(self):
        super()._compute_qty_to_invoice()
        for line in self:
            if line.state != 'sale' or not line._is_invoiced_in_product_uom():
                continue
            # Delivered and invoiced quantities converted into the packaging
            # are rounded: compare them in the unit of the product
            quantity = line._get_qty_to_invoice_in_product_uom()
            line.qty_to_invoice = line.product_id.uom_id._compute_quantity(
                quantity, line.product_uom_id, round=False)

    def _prepare_invoice_line(self, **optional_values):
        res = super()._prepare_invoice_line(**optional_values)
        if self._is_invoiced_in_product_uom() and res.get('display_type') == 'product':
            product_uom = self.product_id.uom_id
            res.update({
                'product_uom_id': product_uom.id,
                'quantity': self._get_qty_to_invoice_in_product_uom(),
                # The price of a packaging is the price of its estimated weight
                'price_unit': self.product_uom_id._compute_price(self.price_unit, product_uom),
            })
        return res
