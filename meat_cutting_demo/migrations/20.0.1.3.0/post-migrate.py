from odoo import Command, api, SUPERUSER_ID

from odoo.addons.meat_cutting_demo import _create_demo_ingredients

# The demo data are not updated (noupdate): the families by species, fresh or
# frozen, and the new recipes are applied to the databases installed before
CATEGORY_NAMES = {
    'product_category_cut': "Vacuno fresco",
    'product_category_frozen': "Vacuno congelado",
    'product_category_elaborados': "Elaborado fresco",
}
PORK_PRODUCTS = [
    'jamon', 'paleta', 'lomo', 'solomillo', 'panceta', 'costillas', 'papada', 'chuletas', 'magro',
]
# Recipes for a batch of 100 kg
BOM_LINE_QTY = {
    'bom_line_longaniza_magro': 68.0,
    'bom_line_longaniza_panceta': 28.0,
    'bom_line_morcilla_papada': 40.0,
    'bom_line_morcilla_panceta': 20.0,
}
MADE_PRODUCTS = {
    'product_longaniza': 'product_longaniza_congelada',
    'product_morcilla': 'product_morcilla_congelada',
}


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})

    def ref(xmlid):
        return env.ref(f'meat_cutting_demo.{xmlid}', raise_if_not_found=False)

    for xmlid, name in CATEGORY_NAMES.items():
        if category := ref(xmlid):
            category.name = name
    pork, pork_frozen = ref('product_category_pork'), ref('product_category_pork_frozen')
    for name in PORK_PRODUCTS:
        if product := ref(f'product_cerdo_{name}'):
            product.categ_id = pork
        if product := ref(f'product_cerdo_{name}_congelado'):
            product.categ_id = pork_frozen
    if product := ref('product_cerdo_solomillo_vacio'):
        product.categ_id = pork
    for xmlid in ('bom_longaniza', 'bom_morcilla'):
        if bom := ref(xmlid):
            bom.product_qty = 100.0
    for xmlid, qty in BOM_LINE_QTY.items():
        if bom_line := ref(xmlid):
            bom_line.product_qty = qty
    presentations = ref('attribute_presentacion_ristra') | ref('attribute_presentacion_troceado') \
        | ref('attribute_presentacion_vacio')
    for xmlid, frozen_xmlid in MADE_PRODUCTS.items():
        product = ref(xmlid)
        if not product:
            continue
        product.frozen_product_id = ref(frozen_xmlid)
        if not product.attribute_line_ids:
            product.attribute_line_ids = [Command.create({
                'attribute_id': ref('attribute_presentacion').id,
                'value_ids': [Command.set(presentations.ids)],
            })]
    if not env['stock.quant'].search_count([('product_id', '=', ref('product_sal').id)], limit=1):
        _create_demo_ingredients(env)
