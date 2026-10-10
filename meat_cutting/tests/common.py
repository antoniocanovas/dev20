from odoo import Command


def create_cutting_data(cls):
    """ A lot tracked carcass with two cutting BoMs, received through a done receipt. """
    env = cls.env
    cls.uom_kg = env.ref('uom.product_uom_kgm')
    warehouse = env['stock.warehouse'].search([('company_id', '=', env.company.id)], limit=1)
    cls.stock_location = warehouse.lot_stock_id
    supplier_location = env.ref('stock.stock_location_suppliers')
    product_vals = {'type': 'consu', 'is_storable': True, 'tracking': 'lot', 'uom_id': cls.uom_kg.id}
    cls.carcass, cls.loin, cls.ribs = env['product.product'].create([
        dict(product_vals, name='Pork Carcass'),
        dict(product_vals, name='Pork Loin', barcode='8412345678905'),
        dict(product_vals, name='Pork Ribs'),
    ])
    cls.frozen_loin = env['product.product'].create(
        dict(product_vals, name='Frozen Pork Loin', barcode='8412345678912'))
    cls.loin.frozen_product_id = cls.frozen_loin
    cls.bom, cls.bom_chops = env['mrp.bom'].create([{
        'code': 'Standard',
        'sequence': 1,
        'product_tmpl_id': cls.carcass.product_tmpl_id.id,
        'product_qty': 1.0,
        'uom_id': cls.uom_kg.id,
        'type': 'normal',
        'bom_line_ids': [
            Command.create({'product_id': cls.loin.id, 'product_qty': 0.2}),
            Command.create({'product_id': cls.ribs.id, 'product_qty': 0.1}),
        ],
    }, {
        # Second cutting method of the same carcass
        'code': 'Chops',
        'sequence': 2,
        'product_tmpl_id': cls.carcass.product_tmpl_id.id,
        'product_qty': 1.0,
        'uom_id': cls.uom_kg.id,
        'type': 'normal',
        'bom_line_ids': [
            Command.create({'product_id': cls.ribs.id, 'product_qty': 0.3}),
        ],
    }])
    cls.receipt = env['stock.picking'].create({
        'picking_type_id': warehouse.in_type_id.id,
        'location_id': supplier_location.id,
        'location_dest_id': cls.stock_location.id,
        'move_ids': [Command.create({
            'product_id': cls.carcass.id,
            'product_uom_qty': 100,
            'uom_id': cls.uom_kg.id,
            'location_id': supplier_location.id,
            'location_dest_id': cls.stock_location.id,
        })],
    })
    cls.receipt.action_confirm()
    cls.receipt.move_ids.move_line_ids.write({'lot_name': 'L001', 'quantity': 100})
    cls.receipt.move_ids.picked = True
    cls.receipt.button_validate()
    cls.lot = cls.receipt.move_line_ids.lot_id
