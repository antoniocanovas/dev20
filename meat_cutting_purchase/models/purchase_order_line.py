from odoo import api, models


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def _is_invoiced_in_product_uom(self):
        """ Lines ordered in a packaging of the product (e.g. carcasses of an
        estimated weight) and invoiced on receipt are invoiced in the unit of
        the product (kg), with the real quantity received: converting it back
        into packagings would round it and hide the weight. """
        self.ensure_one()
        return (
            not self.display_type
            and not self.is_downpayment
            and self.product_id.purchase_method == 'receive'
            and self.qty_received_method == 'stock_moves'
            and self.uom_id != self.product_id.uom_id
        )

    def _get_qty_received_in_product_uom(self):
        """ Received quantity in the unit of the product, without rounding. """
        self.ensure_one()
        product_uom = self.product_id.uom_id
        quantity = 0.0
        for move in self._get_po_line_moves():
            if move.state != 'done':
                continue
            move_quantity = move.uom_id._compute_quantity(move.quantity, product_uom, round=False)
            if move._is_purchase_return():
                if not move.origin_returned_move_id or move.to_refund:
                    quantity -= move_quantity
            elif (
                move.origin_returned_move_id and move.origin_returned_move_id._is_purchase_return()
                and not move.to_refund
            ) or not move._should_count_for_quantity_received():
                continue
            else:
                quantity += move_quantity
        return quantity

    def _get_qty_invoiced_in_product_uom(self):
        self.ensure_one()
        product_uom = self.product_id.uom_id
        quantity = 0.0
        for invoice_line in self._get_invoice_lines():
            if invoice_line.move_id.state == 'cancel' and invoice_line.move_id.payment_state != 'invoicing_legacy':
                continue
            invoice_qty = invoice_line.product_uom_id._compute_quantity(invoice_line.quantity, product_uom, round=False)
            if invoice_line.move_id.move_type == 'in_invoice':
                quantity += invoice_qty
            elif invoice_line.move_id.move_type == 'in_refund':
                quantity -= invoice_qty
        return quantity

    def _get_qty_to_invoice_in_product_uom(self):
        self.ensure_one()
        return self.product_id.uom_id.round(
            self._get_qty_received_in_product_uom() - self._get_qty_invoiced_in_product_uom())

    @api.depends('move_ids.state', 'move_ids.quantity')
    def _compute_qty_invoiced(self):
        super()._compute_qty_invoiced()
        for line in self:
            if line.order_id.state != 'purchase' or not line._is_invoiced_in_product_uom():
                continue
            # Received and invoiced quantities converted into the packaging
            # are rounded: compare them in the unit of the product
            quantity = line._get_qty_to_invoice_in_product_uom()
            line.qty_to_invoice = line.product_id.uom_id._compute_quantity(quantity, line.uom_id, round=False)

    def _prepare_account_move_line(self, move=False):
        res = super()._prepare_account_move_line(move=move)
        if self._is_invoiced_in_product_uom() and res.get('display_type') == 'product':
            product_uom = self.product_id.uom_id
            quantity = self._get_qty_to_invoice_in_product_uom()
            res.update({
                'product_uom_id': product_uom.id,
                'quantity': -quantity if move and move.move_type == 'in_refund' else quantity,
                # The price of a packaging is the price of its estimated weight
                'price_unit': self.uom_id._compute_price(res['price_unit'], product_uom),
            })
            if 'balance' in res:
                total_excluded = self.tax_ids.with_context(round=False, round_base=False).compute_all(
                    self.uom_id._compute_price(self.price_unit_discounted, product_uom),
                    currency=self.order_id.currency_id,
                    quantity=quantity,
                    product=self.product_id,
                )['total_excluded']
                res['balance'] = self.currency_id._convert(total_excluded, self.company_id.currency_id, round=False)
        return res
