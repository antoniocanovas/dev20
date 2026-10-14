from odoo import models
from odoo.fields import Domain


class AiTool(models.Model):
    """Deterministic built-in report tools: plain read_group aggregations with
    real figures (amount_total / quantity), instead of relying on the LLM to
    compute totals from a raw record dump — which it cannot do reliably,
    since search_records never even exposes financial fields to it.

    All ORM access below goes through ``self._user_model(model_name)``
    (``self.env[model_name].with_user(<effective uid>)``, defined below —
    odoo_mcp_manager used to provide it but dropped it upstream) instead of
    ``.sudo()`` — the
    report is built with the real access rights and record rules of
    whoever is asking (``mcp_user_id`` in context when set, e.g. the real
    Discuss author or an authenticated MCP client, otherwise
    ``self.env.uid``), never with elevated/bot privileges. A user without
    read access to sale.order/purchase.order/account.move/stock.move (or
    to the specific records matched by a multi-company record rule) gets a
    real AccessError instead of silently seeing figures they aren't
    supposed to see."""

    _inherit = 'ai.tool'

    def _execute_builtin(self, parameters):
        handler = {
            'sales_report': self._builtin_sales_report,
            'purchase_report': self._builtin_purchase_report,
            'invoice_report': self._builtin_invoice_report,
            'stock_report': self._builtin_stock_report,
            'box_stock_report': self._builtin_box_stock_report,
            'lot_report': self._builtin_lot_report,
            'stock_lookup': self._builtin_stock_lookup,
            'partner_info': self._builtin_partner_info,
        }.get(self.name)
        if handler:
            return handler(parameters)
        return super()._execute_builtin(parameters)

    def _user_model(self, model_name):
        """*model_name* bound to the user the tool acts for: ``mcp_user_id``
        in context on MCP/bot routes (whose env is the Public/superuser
        one), otherwise the current user -- so every report enforces that
        user's ACLs and record rules."""
        uid = self.env.context.get('mcp_user_id') or self.env.uid
        return self.env[model_name].with_user(uid)

    # ── Shared helpers ──────────────────────────────────────────────────────

    def _partner_domain(self, name, partner_field='partner_id'):
        value = (name or '').strip()
        if not value:
            return []
        partner = self._user_model('res.partner').search([('name', 'ilike', value)], limit=1)
        if partner:
            return [(partner_field, '=', partner.id)]
        return [(f'{partner_field}.name', 'ilike', value)]

    def _singularize_es(self, term):
        """Best-effort Spanish singularization, word by word.

        ilike is a plain substring match, so a plural query ('manzanas') would
        otherwise only match product names themselves stored in plural — it
        would miss both `MANZANA` and `MANZANA ROJA`. Stripping a trailing
        "s"/"es" turns the query into a stem that matches singular names too.
        """
        words = []
        for word in term.split():
            lower = word.lower()
            if len(word) > 3 and lower.endswith('es'):
                word = word[:-2]
            elif len(word) > 3 and lower.endswith('s'):
                word = word[:-1]
            words.append(word)
        return ' '.join(words)

    def _product_name_domain(self, term, name_field='product_id.name',
                              code_field='product_id.default_code'):
        """Domain matching *term* against a product name/code, word by word.

        A single ilike on the whole phrase requires an unbroken run of words
        with no connector in between: "tomate pera" never matches "Tomate
        DE pera" (the "de" breaks the substring), and neither would a
        single run-together word like "tomatepera". Requiring each
        significant word (short connectors like "de"/"el" dropped) to
        independently match somewhere in the name fixes the connector-word
        case. The raw term is still matched as a straight substring against
        the product code, which is not natural-language text.
        """
        stem = self._singularize_es(term)
        words = [w for w in stem.split() if len(w) > 2] or [stem or term]
        name_domain = Domain.AND([[(name_field, 'ilike', w)] for w in words])
        # Domain objects iterate back into the old-style polish-notation
        # list, which every call site still concatenates with `domain +=`.
        return list(Domain.OR([name_domain, [(code_field, 'ilike', term)]]))

    def _date_domain(self, parameters, field):
        domain = []
        date_from = (parameters.get('date_from') or '').strip()
        date_to = (parameters.get('date_to') or '').strip()
        if date_from:
            domain.append((field, '>=', date_from))
        if date_to:
            domain.append((field, '<=', date_to))
        return domain

    def _read_group_amount(
        self, records, domain, date_field, group_by, partner_field, amount_field='amount_total'
    ):
        """Group *records* by partner and/or day, summing *amount_field*."""
        groupby_fields = []
        if group_by in ('customer', 'customer_day'):
            groupby_fields.append(partner_field)
        if group_by in ('day', 'customer_day'):
            groupby_fields.append(f'{date_field}:day')

        data = records.formatted_read_group(
            domain, groupby=groupby_fields, aggregates=[f'{amount_field}:sum', '__count']
        )
        rows = []
        grand_amount = 0.0
        count = 0
        for row in data:
            amount = round(row.get(f'{amount_field}:sum') or 0.0, 2)
            n = row.get('__count', 0)
            grand_amount += amount
            count += n
            entry = {'count': n, 'amount': amount}
            partner = row.get(partner_field)
            if partner:
                entry['partner'] = partner[1]
                entry['partner_id'] = partner[0]
            day = row.get(f'{date_field}:day')
            if day:
                entry['day'] = day[1]
            rows.append(entry)
        return rows, round(grand_amount, 2), count

    def _line_product_detail(self, model_name, domain, group_by, qty_field, date_path,
                              amount_field='price_subtotal', uom_field='product_uom_id'):
        """Product(+lot)-level breakdown shared by sales/purchases/invoicing
        detail modes: which products, how much of each (with UoM), and — per
        the business requirement that any product/quantity detail must carry
        its lot with original vs. current stock — which lot(s), how much was
        originally in that lot and how much is left right now.

        *qty_field* differs per line model (sale.order.line: product_uom_qty,
        purchase.order.line: product_qty, account.move.line: quantity — they
        are NOT interchangeable), and so does *uom_field* (purchase.order.line:
        uom_id). *date_path* is the read_group path to the line's document date
        (e.g. 'order_id.date_order', 'move_id.invoice_date').
        """
        groupby_fields = ['product_id', uom_field, 'lot_id']
        if group_by == 'product_day':
            groupby_fields.append(f'{date_path}:day')

        data = self._user_model(model_name).formatted_read_group(
            domain, groupby=groupby_fields,
            aggregates=[f'{qty_field}:sum', f'{amount_field}:sum', '__count'],
        )
        rows = []
        grand_amount = 0.0
        count = 0
        lot_ids = set()
        for row in data:
            qty = round(row.get(f'{qty_field}:sum') or 0.0, 2)
            amount = round(row.get(f'{amount_field}:sum') or 0.0, 2)
            n = row.get('__count', 0)
            grand_amount += amount
            count += n
            # Weighted average price/unit for the group -- exact per-line
            # price when a row is a single line, average price paid/charged
            # for that product over the period when several lines were
            # summed together (group_by=product / product_day).
            unit_price = round(amount / qty, 4) if qty else 0.0
            entry = {'count': n, 'amount': amount, 'qty': qty, 'unit_price': unit_price}
            if row.get('product_id'):
                entry['product'] = row['product_id'][1]
                entry['product_id'] = row['product_id'][0]
            if row.get(uom_field):
                entry['uom'] = row[uom_field][1]
            day = row.get(f'{date_path}:day')
            if day:
                entry['day'] = day[1]
            if row.get('lot_id'):
                entry['lot_id'] = row['lot_id'][0]
                entry['lot'] = row['lot_id'][1]
                lot_ids.add(row['lot_id'][0])
            rows.append(entry)

        if lot_ids:
            lots = self._user_model('stock.lot').browse(list(lot_ids))
            lot_info = {lot.id: (lot.purchase_kg, lot.product_qty) for lot in lots}
            for entry in rows:
                if entry.get('lot_id') in lot_info:
                    entry['lot_original'], entry['lot_stock'] = lot_info[entry['lot_id']]

        return {
            'rows': rows, 'grand_amount': round(grand_amount, 2), 'count': count,
            'currency': self.env.company.currency_id.symbol,
            'product_detail': True,
        }

    # ── Ventas ──────────────────────────────────────────────────────────────

    def _builtin_sales_report(self, parameters):
        group_by = (parameters.get('group_by') or 'customer').strip().lower()
        if group_by in ('product', 'product_day'):
            return self._builtin_sales_product_detail(parameters, group_by)
        domain = self._partner_domain(parameters.get('customer')) + \
            self._date_domain(parameters, 'date_order')
        rows, grand_amount, count = self._read_group_amount(
            self._user_model('sale.order'), domain, 'date_order', group_by, 'partner_id'
        )
        return {
            'rows': rows, 'grand_amount': grand_amount, 'count': count,
            'currency': self.env.company.currency_id.symbol,
        }

    def _builtin_sales_product_detail(self, parameters, group_by):
        domain = [('state', 'in', ('sale', 'done')), ('display_type', '=', False)]
        domain += self._partner_domain(parameters.get('customer'), partner_field='order_partner_id')
        product = (parameters.get('product') or '').strip()
        if product:
            domain += self._product_name_domain(product)
        date_from = (parameters.get('date_from') or '').strip()
        date_to = (parameters.get('date_to') or '').strip()
        if date_from:
            domain.append(('order_id.date_order', '>=', date_from))
        if date_to:
            domain.append(('order_id.date_order', '<=', date_to))
        return self._line_product_detail(
            'sale.order.line', domain, group_by,
            qty_field='product_uom_qty', date_path='order_id.date_order',
        )

    # ── Compras ─────────────────────────────────────────────────────────────

    def _builtin_purchase_report(self, parameters):
        group_by = (parameters.get('group_by') or 'customer').strip().lower()
        # "customer"/"day"/"total" aggregate on purchase.order (order-level
        # totals, count = number of orders) -- unchanged, already covers "how
        # much have we spent with X". "product"/"product_day" need line-level
        # detail (which products, how much of each) that purchase.order alone
        # can't answer -- it has no product_id. Kept as a separate path so the
        # existing customer/day behaviour (and what "count" means there)
        # never changes.
        if group_by in ('product', 'product_day'):
            return self._builtin_purchase_product_detail(parameters, group_by)
        domain = self._partner_domain(parameters.get('vendor')) + \
            self._date_domain(parameters, 'date_order')
        rows, grand_amount, count = self._read_group_amount(
            self._user_model('purchase.order'), domain, 'date_order', group_by, 'partner_id'
        )
        return {
            'rows': rows, 'grand_amount': grand_amount, 'count': count,
            'currency': self.env.company.currency_id.symbol,
        }

    def _builtin_purchase_product_detail(self, parameters, group_by):
        """Per-product(+lot) breakdown of what was bought from a vendor —
        'compras' on its own only ever gave an order-level total, never
        which products (or which lot each purchase fed)."""
        domain = [('state', 'in', ('purchase', 'done')), ('display_type', '=', False)]
        domain += self._partner_domain(parameters.get('vendor'), partner_field='partner_id')
        product = (parameters.get('product') or '').strip()
        if product:
            domain += self._product_name_domain(product)
        date_from = (parameters.get('date_from') or '').strip()
        date_to = (parameters.get('date_to') or '').strip()
        if date_from:
            domain.append(('order_id.date_order', '>=', date_from))
        if date_to:
            domain.append(('order_id.date_order', '<=', date_to))
        return self._line_product_detail(
            'purchase.order.line', domain, group_by,
            qty_field='product_qty', date_path='order_id.date_order', uom_field='uom_id',
        )

    # ── Invoicing ────────────────────────────────────────────────────────────

    _INVOICE_TYPES = {
        'customer': ['out_invoice', 'out_refund'],
        'vendor': ['in_invoice', 'in_refund'],
        'all': ['out_invoice', 'out_refund', 'in_invoice', 'in_refund'],
    }
    _PAYMENT_STATE_ES = {
        'not_paid': 'sin pagar', 'in_payment': 'en proceso de pago',
        'paid': 'pagada', 'partial': 'pago parcial', 'reversed': 'anulada',
        'invoicing_legacy': 'legado',
    }

    def _builtin_invoice_report(self, parameters):
        group_by = (parameters.get('group_by') or 'customer').strip().lower()
        if group_by in ('product', 'product_day'):
            return self._builtin_invoice_product_detail(parameters, group_by)
        if group_by == 'detail':
            return self._builtin_invoice_detail(parameters)

        move_type = (parameters.get('move_type') or 'all').strip().lower()
        pending = bool(parameters.get('pending'))
        domain = [
            ('move_type', 'in', self._INVOICE_TYPES.get(move_type, self._INVOICE_TYPES['all'])),
            ('state', '=', 'posted'),
        ]
        if pending:
            # payment_state == 'reversed' means a credit note cancelled the
            # bill; nothing is actually owed on it either.
            domain.append(('payment_state', 'not in', ('paid', 'in_payment', 'reversed')))
        domain += self._partner_domain(parameters.get('partner')) + \
            self._date_domain(parameters, 'invoice_date')
        # "pendiente" cares about what's still owed (amount_residual), not the
        # original total — a partially-paid bill would otherwise overstate the debt.
        amount_field = 'amount_residual' if pending else 'amount_total'
        rows, grand_amount, count = self._read_group_amount(
            self._user_model('account.move'), domain, 'invoice_date', group_by, 'partner_id',
            amount_field=amount_field,
        )
        return {
            'rows': rows, 'grand_amount': grand_amount, 'count': count,
            'currency': self.env.company.currency_id.symbol,
            'pending': pending,
        }

    def _builtin_invoice_product_detail(self, parameters, group_by):
        """Per-product(+lot) breakdown of invoice lines — 'facturacion' on
        its own only ever gave a per-invoice/customer total, never which
        products were actually billed."""
        move_type = (parameters.get('move_type') or 'all').strip().lower()
        domain = [
            ('move_id.move_type', 'in', self._INVOICE_TYPES.get(move_type, self._INVOICE_TYPES['all'])),
            ('move_id.state', '=', 'posted'),
            # account.move.line uses explicit display_type values ('product',
            # 'tax', 'payment_term'...) unlike sale/purchase order lines,
            # where a regular line is display_type=False -- filtering on
            # False here would silently exclude every real product line.
            ('display_type', '=', 'product'),
            ('product_id', '!=', False),
        ]
        domain += self._partner_domain(parameters.get('partner'))
        product = (parameters.get('product') or '').strip()
        if product:
            domain += self._product_name_domain(product)
        date_from = (parameters.get('date_from') or '').strip()
        date_to = (parameters.get('date_to') or '').strip()
        if date_from:
            domain.append(('move_id.invoice_date', '>=', date_from))
        if date_to:
            domain.append(('move_id.invoice_date', '<=', date_to))
        result = self._line_product_detail(
            'account.move.line', domain, group_by,
            qty_field='quantity', date_path='move_id.invoice_date',
        )
        result['move_type'] = move_type
        return result

    def _builtin_invoice_detail(self, parameters):
        """Individual invoices with their own state/payment_state — 'estado
        de facturas'. The aggregate path above only ever gives one summed
        total, never which specific invoices are behind it or what state
        each one is in."""
        move_type = (parameters.get('move_type') or 'all').strip().lower()
        domain = [
            ('move_type', 'in', self._INVOICE_TYPES.get(move_type, self._INVOICE_TYPES['all'])),
            ('state', '=', 'posted'),
        ]
        domain += self._partner_domain(parameters.get('partner')) + \
            self._date_domain(parameters, 'invoice_date')
        moves = self._user_model('account.move').search(
            domain, order='invoice_date desc, id desc', limit=20
        )
        rows = [{
            'id': m.id,
            'name': m.name,
            'partner': m.partner_id.name,
            'partner_id': m.partner_id.id,
            'date': m.invoice_date.strftime('%Y-%m-%d') if m.invoice_date else '',
            'total': m.amount_total,
            'residual': m.amount_residual,
            'payment_state': self._PAYMENT_STATE_ES.get(m.payment_state, m.payment_state),
        } for m in moves]
        return {
            'rows': rows, 'currency': self.env.company.currency_id.symbol,
            'invoice_detail': True,
        }

    # ── Stock ───────────────────────────────────────────────────────────────

    _STOCK_DIRECTIONS = {'in': 'incoming', 'incoming': 'incoming',
                          'out': 'outgoing', 'outgoing': 'outgoing',
                          'internal': 'internal'}

    def _builtin_stock_report(self, parameters):
        stock_move = self._user_model('stock.move')
        domain = [('state', '=', 'done')]

        product = (parameters.get('product') or '').strip()
        matched_products = self.env['product.product']
        if product:
            matched_products = self._user_model('product.product').search(
                self._product_name_domain(product, name_field='name', code_field='default_code')
            )
            domain += self._product_name_domain(product)
        if parameters.get('only_boxes'):
            domain.append(('product_id.is_box', '=', True))

        direction = self._STOCK_DIRECTIONS.get((parameters.get('direction') or '').strip().lower())
        if direction:
            domain.append(('picking_type_id.code', '=', direction))

        domain += self._date_domain(parameters, 'date')

        group_by = (parameters.get('group_by') or 'product').strip().lower()
        groupby_fields = []
        if group_by in ('product', 'product_day'):
            groupby_fields.append('product_id')
        if group_by in ('day', 'product_day'):
            groupby_fields.append('date:day')

        data = stock_move.formatted_read_group(
            domain, groupby=groupby_fields, aggregates=['quantity:sum', '__count']
        )
        rows = []
        grand_qty = 0.0
        count = 0
        for row in data:
            qty = round(row.get('quantity:sum') or 0.0, 2)
            n = row.get('__count', 0)
            grand_qty += qty
            count += n
            entry = {'count': n, 'qty': qty}
            if row.get('product_id'):
                entry['product'] = row['product_id'][1]
                entry['product_id'] = row['product_id'][0]
            day = row.get('date:day')
            if day:
                entry['day'] = day[1]
            rows.append(entry)

        uom = matched_products[:1].uom_id.name if matched_products else ''

        result = {'rows': rows, 'grand_qty': round(grand_qty, 2), 'count': count, 'uom': uom}

        # Desglose por lote (proveedor + caducidad): solo cuando la pregunta apunta a
        # un producto concreto -- no a "cajas" (only_boxes) ni a un listado general --
        # y sobre existencias actuales (stock.quant), no sobre los movimientos del
        # rango de fechas consultado, que es lo que agregan `rows` arriba.
        if matched_products and not parameters.get('only_boxes'):
            result['lots'] = self._stock_lots_detail(matched_products)

        return result

    def _stock_lots_detail(self, products, limit=15):
        """On-hand lots for *products*: lot, supplier, expiration, original
        purchased quantity (`purchase_kg`) and current stock quantity —
        soonest to expire first (FEFO criterion)."""
        quants = self._user_model('stock.quant').search([
            ('product_id', 'in', products.ids),
            ('location_id.usage', '=', 'internal'),
            ('lot_id', '!=', False),
            ('quantity', '>', 0),
        ])
        by_lot = {}
        for quant in quants:
            lot = quant.lot_id
            entry = by_lot.setdefault(lot.id, {
                'lot': lot.name,
                'lot_id': lot.id,
                'product_id': lot.product_id.id,
                'supplier': lot.partner_id.name or '',
                'partner_id': lot.partner_id.id,
                'expiration': (
                    lot.expiration_date.strftime('%Y-%m-%d') if lot.expiration_date else ''
                ),
                'original': lot.purchase_kg,
                'qty': 0.0,
            })
            entry['qty'] += quant.quantity
        lots = sorted(
            by_lot.values(), key=lambda entry: entry['expiration'] or '9999-99-99'
        )
        for entry in lots:
            entry['qty'] = round(entry['qty'], 2)
        return lots[:limit]

    # ── Cajas en cliente/proveedor ───────────────────────────────────────────

    def _builtin_box_stock_report(self, parameters):
        partner_name = (parameters.get('partner') or '').strip()
        if not partner_name:
            return {'found': False, 'searched': ''}
        partner = self._user_model('res.partner').search(
            [('name', 'ilike', partner_name)], limit=1
        )
        if not partner:
            return {'found': False, 'searched': partner_name}
        return {
            'found': True, 'partner': partner.name, 'partner_id': partner.id,
            'box_qty': partner.mercas_box_qty,
        }

    # ── Contacto: datos generales de un cliente/proveedor/contacto ─────────

    def _builtin_partner_info(self, parameters):
        """Business-card info for a client/vendor/contact: phone, address,
        province, VAT (NIF) and the related company when the match is an
        individual contact (parent_id), not a company itself."""
        name = (parameters.get('partner') or '').strip()
        if not name:
            return {'found': False, 'searched': ''}
        partner = self._user_model('res.partner').search(
            [('name', 'ilike', name)], limit=1
        )
        if not partner:
            return {'found': False, 'searched': name}
        return {
            'found': True,
            'id': partner.id,
            'name': partner.name,
            'phone': partner.phone or '',
            'street': partner.street or '',
            'street2': partner.street2 or '',
            'city': partner.city or '',
            'zip': partner.zip or '',
            'state': partner.state_id.name if partner.state_id else '',
            'country': partner.country_id.name if partner.country_id else '',
            'vat': partner.vat or '',
            'parent_id': partner.parent_id.id if partner.parent_id else None,
            'parent_name': partner.parent_id.name if partner.parent_id else '',
        }

    # ── Existencias puntuales (a fecha de hoy, no un rango de movimientos) ──────

    def _builtin_stock_lookup(self, parameters):
        product = (parameters.get('product') or '').strip()
        if not product:
            # "stock actual" sin nombrar producto -> listado general, no un
            # "no encontrado" (no se buscaba nada en concreto que no aparezca).
            return self._builtin_stock_lookup_general()
        products = self._user_model('product.product').search(
            self._product_name_domain(product, name_field='name', code_field='default_code'),
            limit=20,
        )
        if not products:
            return {'found': False, 'searched': product}
        rows = [
            {
                'id': p.id, 'name': p.name, 'qty': p.qty_available, 'uom': p.uom_id.name,
                'variant': self._product_variant_label(p),
            }
            for p in products
        ]
        # Siempre con desglose por lote (cantidad original comprada vs. lo que
        # queda ahora) -- no solo el total agregado del producto.
        return {
            'found': True, 'searched': product, 'rows': rows,
            'lots': self._stock_lots_detail(products),
        }

    @staticmethod
    def _product_variant_label(product):
        """Combination label ("Grande", "Grande, Rojo"...) for *product*, but
        only when its template actually has more than one variant -- a
        single-variant product never needs to spell that out, even if its
        attributes technically produced one (e.g. a single-value line)."""
        if product.product_tmpl_id.product_variant_count <= 1:
            return ''
        return product.product_template_attribute_value_ids._get_combination_name()

    def _builtin_stock_lookup_general(self, limit=20):
        """There's no product to search by name, so it can't be narrowed
        down by domain -- a reasonable batch of candidates with stock is
        fetched and sorted/trimmed in Python (qty_available isn't a stored
        field, not reliable for 'order' in the search itself). No lot
        breakdown here on purpose: with up to `limit` products, a lot
        breakdown for each one would bury the general overview being
        requested -- that's what asking about a specific product is for."""
        candidates = self._user_model('product.product').search(
            [('qty_available', '>', 0)], limit=200
        )
        products = candidates.sorted('qty_available', reverse=True)[:limit]
        rows = [
            {
                'id': p.id, 'name': p.name, 'qty': p.qty_available, 'uom': p.uom_id.name,
                'variant': self._product_variant_label(p),
            }
            for p in products
        ]
        return {'found': True, 'rows': rows, 'general': True}

    # ── Lote: ficha completa + trazabilidad de venta ────────────────────────────

    _LOT_DETAIL_FIELDS = [
        'name', 'product_id', 'partner_id', 'origin_country_id', 'origin_state_id',
        'product_qty', 'expiration_date',
    ]

    #: Lots currently in stock with no lot/product name given ("todos los
    #: lotes en stock") -- capped so the reply stays readable.
    _LOT_LIST_LIMIT = 30

    def _builtin_lot_report(self, parameters):
        """Lot ficha (where it's from, how much is on hand, when it came in,
        expiry, who it's been sold to) — or, with no lot/product given, the
        same ficha for every lot currently in stock. Never includes billing/
        invoicing figures (regime, invoiced, pending) — that belongs to
        the internal back-office, not to a business question about a lot.
        Box/crate products (product_id.is_box) are never real goods lots and
        are always excluded."""
        lot_name = (parameters.get('lot') or '').strip()
        product_name = (parameters.get('product') or '').strip()
        not_box = [('product_id.is_box', '=', False)]

        if not lot_name and not product_name:
            lots = self._user_model('stock.lot').search(
                not_box + [('product_qty', '>', 0)],
                order='expiration_date', limit=self._LOT_LIST_LIMIT,
            )
            if not lots:
                return {'found': False, 'searched': ''}
            return {'found': True, 'details': self._lot_details(lots)}

        product_alternatives = []
        if lot_name:
            # The classifier sometimes puts a whole product phrase into "lot"
            # instead of "product" (e.g. "lote tomate pera" reads as if
            # "tomate pera" were the lot code) — an exact match on a name
            # that isn't a real lot code always misses, so also try it as a
            # product name.
            product_alternatives.append(
                self._product_name_domain(lot_name, code_field='product_id.default_code')
            )
        if product_name:
            product_alternatives.append(
                self._product_name_domain(product_name, code_field='product_id.default_code')
            )
        # A lot asked for by its exact code is shown even if already empty
        # (its history is the point); matched by product name, only lots
        # still on hand -- otherwise "stock tomates" lists every old,
        # depleted lot of that product.
        by_product = Domain.AND([Domain.OR(product_alternatives), [('product_qty', '>', 0)]])
        alternatives = [by_product]
        if lot_name:
            alternatives.append([('name', '=', lot_name)])
        domain = list(Domain.AND([Domain.OR(alternatives), not_box]))

        lots = self._user_model('stock.lot').search(
            domain, order='expiration_date', limit=self._LOT_LIST_LIMIT,
        )
        if not lots:
            return {'found': False, 'searched': lot_name or product_name}
        return {'found': True, 'details': self._lot_details(lots)}

    def _lot_details(self, lots):
        """Read *lots* into the plain business ficha shape, each with its own
        embedded 'entry' date (first physical reception) and 'sales' trace —
        never a shared trace list, so a multi-lot listing doesn't mix up
        which sale belongs to which lot."""
        entry_dates = self._lot_entry_dates(lots.ids)
        sale_lines = self._user_model('sale.order.line').search([
            ('lot_id', 'in', lots.ids),
        ])
        sales_by_lot = {}
        for line in sale_lines:
            sales_by_lot.setdefault(line.lot_id.id, []).append({
                'partner': line.order_partner_id.name,
                'partner_id': line.order_partner_id.id,
                'qty': line.product_uom_qty,
                'uom': line.product_uom_id.name,
                'order': line.order_id.name,
                'order_id': line.order_id.id,
                'date': (
                    line.order_id.date_order.strftime('%Y-%m-%d')
                    if line.order_id.date_order else ''
                ),
            })

        # One read() for the whole batch instead of one per lot -- matters
        # now that "todos los lotes en stock" can return up to
        # _LOT_LIST_LIMIT lots in a single call.
        data_by_id = {row['id']: row for row in lots.read(self._LOT_DETAIL_FIELDS)}

        details = []
        for lot in lots:
            data = data_by_id[lot.id]
            data['uom'] = lot.product_id.uom_id.name
            data['entry'] = entry_dates.get(lot.id, '')
            data['sales'] = sales_by_lot.get(lot.id, [])
            details.append(data)
        return details

    def _lot_entry_dates(self, lot_ids):
        """First physical reception date (supplier -> internal, done) per
        lot — the same 'received' criterion as stock.lot.received_kg, just
        keeping the earliest move date instead of summing quantities."""
        data = self._user_model('stock.move.line').formatted_read_group(
            [
                ('lot_id', 'in', lot_ids), ('state', '=', 'done'),
                ('location_id.usage', '=', 'supplier'),
                ('location_dest_id.usage', '=', 'internal'),
            ],
            groupby=['lot_id'], aggregates=['date:min'],
        )
        return {
            row['lot_id'][0]: row['date:min'].strftime('%Y-%m-%d')
            for row in data if row.get('lot_id') and row.get('date:min')
        }
