from dateutil.relativedelta import relativedelta

from odoo import Command, fields

# Receipts: (supplier, [(lot, weight in kg)]), one lot per carcass
RECEIPTS = [
    ('meat_cutting_demo.partner_matadero_sur', [
        ('meat_cutting_demo.lot_cerdo_01', 94.6),
        ('meat_cutting_demo.lot_cerdo_02', 89.3),
        ('meat_cutting_demo.lot_cerdo_03', 91.8),
    ]),
    ('meat_cutting_demo.partner_carnes_sierra', [
        ('meat_cutting_demo.lot_ternera_01', 168.4),
        ('meat_cutting_demo.lot_ternera_02', 159.7),
    ]),
]

# Validated session: (lot, receipt index, {cut: [weights]}). The cuts sold as
# whole pieces are weighed piece by piece (two per carcass), each in its own
# package; the others in crates
DONE_SESSION = ('meat_cutting_demo.lot_cerdo_01', 0, {
    'meat_cutting_demo.product_cerdo_jamon': [11.62, 11.23],
    'meat_cutting_demo.product_cerdo_paleta': [7.18, 6.92],
    'meat_cutting_demo.product_cerdo_lomo': [4.88, 4.77],
    'meat_cutting_demo.product_cerdo_solomillo': [0.73],
    # The other tenderloin is vacuum packed when cut (product kept in stock)
    'meat_cutting_demo.product_cerdo_solomillo_vacio': [0.69],
    'meat_cutting_demo.product_cerdo_panceta': [5.71, 5.59],
    'meat_cutting_demo.product_cerdo_costillas': [3.80, 3.65],
    'meat_cutting_demo.product_cerdo_papada': [1.47, 1.43],
    'meat_cutting_demo.product_cerdo_magro': [5.10, 4.10],
})
# Cuts of the done session produced frozen
# (the bacon and the jowl are left fresh for the sausages)
FROZEN_CUTS = ['meat_cutting_demo.product_cerdo_costillas', 'meat_cutting_demo.product_cerdo_solomillo']
# Label of the done session edited before printing: (cut, texts)
EDITED_LABEL = ('meat_cutting_demo.product_cerdo_jamon', {
    'product_name': "Jamón fresco de cerdo Duroc",
    'note': "Apto para curación. Conservar entre 0 y 4 °C",
})
# Session in progress, partially weighed, freezing its cuts by default
DRAFT_SESSION = ('meat_cutting_demo.lot_ternera_01', 1, {
    'meat_cutting_demo.product_ternera_solomillo': [3.35],
    'meat_cutting_demo.product_ternera_lomo_alto': [8.60],
    'meat_cutting_demo.product_ternera_babilla': [8.15],
})
# Fresh piece frozen afterwards, from the stock: (cut, weight)
FROZEN_LATER = ('meat_cutting_demo.product_cerdo_paleta', 7.18)
# Stock of the ingredients that are not cuts: (product, lot, kg, days to expiry).
# Two lots of onion, to see the one closest to expiry proposed first
INGREDIENTS = [
    ('meat_cutting_demo.product_sal', 'SAL-2609', 25.0, 600),
    ('meat_cutting_demo.product_pimenton', 'PIM-2608', 5.0, 300),
    ('meat_cutting_demo.product_pimienta', 'PNE-2607', 2.0, 280),
    ('meat_cutting_demo.product_ajo', 'AJO-2610', 3.0, 20),
    ('meat_cutting_demo.product_cebolla', 'CEB-2610A', 8.0, 4),
    ('meat_cutting_demo.product_cebolla', 'CEB-2610B', 10.0, 9),
]


def _create_demo_operations(env):
    """ Stock operations cannot be declared in XML: receive the carcasses
    through validated receipts, then cut one of them and leave another cutting
    session in progress. """
    warehouse = env['stock.warehouse'].search([('company_id', '=', env.company.id)], limit=1)
    stock_location = warehouse.lot_stock_id
    supplier_location = env.ref('stock.stock_location_suppliers')
    kg = env.ref('uom.product_uom_kgm')

    receipts = env['stock.picking']
    for partner_xmlid, lines in RECEIPTS:
        lots = [(env.ref(lot_xmlid), weight) for lot_xmlid, weight in lines]
        receipt = env['stock.picking'].create({
            'picking_type_id': warehouse.in_type_id.id,
            'partner_id': env.ref(partner_xmlid).id,
            'location_id': supplier_location.id,
            'location_dest_id': stock_location.id,
            'move_ids': [Command.create({
                'product_id': lot.product_id.id,
                'product_uom_qty': weight,
                'uom_id': kg.id,
                'location_id': supplier_location.id,
                'location_dest_id': stock_location.id,
            }) for lot, weight in lots],
        })
        receipt.action_confirm()
        # The moves of a same product are merged: one move line per lot
        receipt.move_line_ids.unlink()
        env['stock.move.line'].create([{
            'picking_id': receipt.id,
            'move_id': receipt.move_ids.filtered(lambda m: m.product_id == lot.product_id).id,
            'product_id': lot.product_id.id,
            'lot_id': lot.id,
            'quantity': weight,
            'uom_id': kg.id,
            'location_id': supplier_location.id,
            'location_dest_id': stock_location.id,
        } for lot, weight in lots])
        receipt.move_ids.picked = True
        receipt.button_validate()
        receipts |= receipt

    Session = env['meat.cutting.session']
    for lot_xmlid, receipt_index, weights in (DONE_SESSION, DRAFT_SESSION):
        lot = env.ref(lot_xmlid)
        session = Session.browse(Session.start_cutting_session(lot.product_id.id, lot.id, receipts[receipt_index].id))
        line_by_product = {line.product_id: line for line in session.bom_id.bom_line_ids}
        if lot_xmlid == DRAFT_SESSION[0]:
            session.action_set_freeze(True)
        for product_xmlid, piece_weights in weights.items():
            for weight in piece_weights:
                session.action_add_line(line_by_product[env.ref(product_xmlid)].id, weight)
        if lot_xmlid == DONE_SESSION[0]:
            frozen_products = env['product.product'].browse([env.ref(xmlid).id for xmlid in FROZEN_CUTS])
            session.line_ids.filtered(lambda l: l.product_id in frozen_products).action_set_freeze(True)
            session.action_validate()
            product_xmlid, texts = EDITED_LABEL
            line = session.line_ids.filtered(lambda l: l.product_id == env.ref(product_xmlid))[-1]
            line.action_save_label(dict(line._get_label_values(), **texts))
        else:
            session.label_report_id = env.ref('meat_cutting_demo.action_report_label_compact')

    _create_demo_sales(env)
    _freeze_demo_stock(env)
    _create_demo_purchases(env)
    _create_demo_ingredients(env)


def _create_demo_ingredients(env):
    """ Stock of salt, spices and onion for the productions, in lots that
    expire. """
    warehouse = env['stock.warehouse'].search([('company_id', '=', env.company.id)], limit=1)
    now = fields.Datetime.now()
    for product_xmlid, lot_name, quantity, days in INGREDIENTS:
        product = env.ref(product_xmlid)
        lot = env['stock.lot'].create({
            'product_id': product.id,
            'name': lot_name,
            'company_id': env.company.id,
            'expiration_date': now + relativedelta(days=days),
        })
        env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': product.id,
            'location_id': warehouse.lot_stock_id.id,
            'lot_id': lot.id,
            'inventory_quantity': quantity,
        }).action_apply_inventory()


def _find_piece(env, product_xmlid, weight):
    """ Quant of the piece of this weight in stock. """
    quants = env['stock.quant'].search([
        ('product_id', '=', env.ref(product_xmlid).id),
        ('location_id.usage', '=', 'internal'),
        ('quantity', '>', 0),
    ])
    return quants.filtered(lambda q: q.uom_id.compare(q.quantity, weight) == 0)[:1]


# Quotation: (product, uom, quantity, presentation)
QUOTATION = [
    ('meat_cutting_demo.product_cerdo_lomo', 'meat_cutting_demo.uom_pieza_cerdo_lomo', 1,
     'meat_cutting_demo.attribute_presentacion_fileteado'),
    ('meat_cutting_demo.product_cerdo_jamon', 'meat_cutting_demo.uom_pieza_cerdo_jamon', 2,
     'meat_cutting_demo.attribute_presentacion_entera'),
    ('meat_cutting_demo.product_cerdo_chuletas', 'uom.product_uom_kgm', 3, False),
]
# Delivered order, boxed: (product, uom, pieces ordered, weight of the piece delivered)
DELIVERED_ORDER = [
    ('meat_cutting_demo.product_cerdo_lomo', 'meat_cutting_demo.uom_pieza_cerdo_lomo', 1, 4.88),
    # Lighter than estimated: the piece is complete anyway, no backorder
    ('meat_cutting_demo.product_cerdo_paleta', 'meat_cutting_demo.uom_pieza_cerdo_paleta', 1, 6.92),
    ('meat_cutting_demo.product_cerdo_solomillo_vacio', 'meat_cutting_demo.uom_pieza_cerdo_solomillo', 1, 0.69),
]


def _prepare_sale_line_vals(env, product_xmlid, uom_xmlid, quantity, presentation_xmlid=False):
    product = env.ref(product_xmlid)
    vals = {
        'product_id': product.id,
        'product_uom_id': env.ref(uom_xmlid).id,
        'product_uom_qty': quantity,
    }
    if presentation_xmlid:
        presentation = product.attribute_line_ids.product_template_value_ids.filtered(
            lambda ptav: ptav.product_attribute_value_id == env.ref(presentation_xmlid))
        vals['product_no_variant_attribute_value_ids'] = [Command.set(presentation.ids)]
    return vals


def _create_demo_sales(env):
    """ Sell whole pieces: the customer orders pieces of the "Pieza completa"
    packaging; the warehouse picks the pieces (packages), boxes them and the
    real weight is invoiced at the price per kg. """
    env['res.config.settings'].create({'group_uom': True}).execute()
    customer = env.ref('meat_cutting_demo.partner_carniceria_plaza')
    SaleOrder = env['sale.order']
    SaleOrder.create({
        'partner_id': customer.id,
        'order_line': [Command.create(_prepare_sale_line_vals(env, *line)) for line in QUOTATION],
    })
    order = SaleOrder.create({
        'partner_id': customer.id,
        'order_line': [Command.create(_prepare_sale_line_vals(env, *line[:3])) for line in DELIVERED_ORDER],
    })
    order.action_confirm()
    delivery = order.picking_ids
    for product_xmlid, _uom_xmlid, _quantity, weight in DELIVERED_ORDER:
        piece = _find_piece(env, product_xmlid, weight)
        move = delivery.move_ids.filtered(lambda m: m.product_id == piece.product_id)
        move.move_line_ids.unlink()
        env['stock.move.line'].create({
            'move_id': move.id,
            'picking_id': delivery.id,
            'product_id': piece.product_id.id,
            'uom_id': piece.uom_id.id,
            'quantity': piece.quantity,
            'lot_id': piece.lot_id.id,
            'package_id': piece.package_id.id,
            'result_package_id': piece.package_id.id,
            'location_id': piece.location_id.id,
            'location_dest_id': move.location_dest_id.id,
        })
    delivery.move_ids.picked = True
    # All the pieces in one shipping box
    delivery.move_line_ids.with_context(force_move_lines=True).action_put_in_pack(
        package_type_id=env.ref('meat_cutting_demo.package_type_caja').id)
    delivery.with_context(skip_sms=True).button_validate()


def _freeze_demo_stock(env):
    """ A fresh piece in stock, frozen afterwards. """
    _find_piece(env, *FROZEN_LATER).action_meat_freeze()


# Purchase orders of carcasses: (supplier, product, packaging, carcasses ordered,
# data of the slaughter batch or False to leave it to receive, carcasses received
# as (crotal, weight, data of the animal)). The data of the batch are the defaults
# of the animals (countries, halal).
PURCHASES = [
    ('meat_cutting_demo.partner_matadero_sur', 'meat_cutting_demo.product_canal_cerdo',
     'meat_cutting_demo.uom_canal_cerdo', 3, {
         'supplier_health_code': 'ES 10.04512/MU CE',
         'slaughter_order': 'SAC-2026-4502',
         'slaughter_days': 1,
         'birth_country': 'España',
         'reared_country': 'España',
     }, [
         # Lighter than estimated (268.9 kg for 270 kg): received without backorder
         ('ES300125400121', 92.4, {'sex': 'male', 'breed': 'Duroc', 'quality': 'E', 'months': 7}),
         ('ES300125400122', 87.9, {'sex': 'female', 'breed': 'Duroc x Large White', 'quality': 'U', 'months': 7}),
         ('ES300125400123', 88.6, {'sex': 'male', 'breed': 'Duroc', 'quality': 'U', 'months': 6}),
     ]),
    # Halal batch with an animal born in France, which is not halal
    ('meat_cutting_demo.partner_carnes_sierra', 'meat_cutting_demo.product_canal_ternera',
     'meat_cutting_demo.uom_canal_ternera', 2, {
         'supplier_health_code': 'ES 10.02231/AV CE',
         'slaughter_order': 'SAC-2026-1203',
         'slaughter_days': 2,
         'birth_country': 'España',
         'reared_country': 'España',
         'halal': True,
         'halal_certifier': 'Certificadora Halal Demo',
         'halal_certificate': 'HAL-2026-0451',
     }, [
         ('ES050812345702', 163.2, {'sex': 'male', 'breed': 'Avileña-Negra Ibérica', 'quality': 'R3', 'months': 11}),
         ('FR4403123456', 151.8, {
             'sex': 'female', 'breed': 'Limusina', 'quality': 'U2', 'months': 10,
             'birth_country': 'Francia', 'reared_country': 'Francia, España', 'halal': False,
         }),
     ]),
    # Confirmed, to register the carcasses when they arrive
    ('meat_cutting_demo.partner_matadero_sur', 'meat_cutting_demo.product_canal_cerdo',
     'meat_cutting_demo.uom_canal_cerdo', 2, False, []),
]


def _create_demo_purchases(env):
    """ Buy carcasses by number: the receipt registers each one with its crotal
    and real weight, which is billed at the price per kg. """
    today = fields.Date.context_today(env['purchase.order'])
    for partner_xmlid, product_xmlid, uom_xmlid, quantity, batch, carcasses in PURCHASES:
        product = env.ref(product_xmlid)
        order = env['purchase.order'].create({
            'partner_id': env.ref(partner_xmlid).id,
            'order_line': [Command.create({'product_id': product.id, 'product_qty': quantity})],
        })
        # As in the interface: the price of the vendor (per kg) is converted
        # when the unit changes
        order.order_line.uom_id = env.ref(uom_xmlid)
        order.button_confirm()
        if not batch:
            continue
        batch = dict(batch)
        slaughter_date = today - relativedelta(days=batch.pop('slaughter_days'))
        receipt = order.picking_ids
        action = receipt.action_register_carcasses()
        env['meat.carcass.register'].with_context(action['context']).create(dict(
            batch,
            slaughter_date=slaughter_date,
            line_ids=[Command.create({
                'product_id': product.id,
                'name': name,
                'weight': weight,
                'sex': animal['sex'],
                'breed': animal['breed'],
                'quality': animal['quality'],
                'birth_date': today - relativedelta(months=animal['months']),
                'birth_country': animal.get('birth_country', batch['birth_country']),
                'reared_country': animal.get('reared_country', batch['reared_country']),
                'halal': animal.get('halal', batch.get('halal', False)),
            }) for name, weight, animal in carcasses],
        )).action_confirm()
        # Left to bill: the bill shows the real weight received
        receipt.button_validate()
