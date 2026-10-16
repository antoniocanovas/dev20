# Datos de prueba para albaranes-ia en el Odoo 20 de pruebas.
# Ejecutar con: odoo shell -d odoo --no-http < datos_prueba.py
# Idempotente: si ya existen el usuario, el cliente o los pedidos, los reutiliza.
# Escribe la API key nueva (solo si la genera) en /tmp/albaranes_ia_apikey.
import os
from datetime import timedelta
from odoo import fields

Lang = env['res.lang'].with_context(active_test=False)
es = Lang.search([('code', '=', 'es_ES')])
if not es.active:
    env['base.language.install'].create({'lang_ids': [(6, 0, es.ids)], 'overwrite': False}).lang_install()
    print('Idioma es_ES instalado')

# Usuario de integración (solo para la API JSON-2)
Users = env['res.users'].with_context(active_test=False)
user = Users.search([('login', '=', 'integracion.albaranes')])
if not user:
    groups = [env.ref(x).id for x in (
        'base.group_user', 'stock.group_stock_manager',
        'sales_team.group_sale_manager', 'account.group_account_invoice')]
    user = Users.create({
        'name': 'Integración albaranes IA', 'login': 'integracion.albaranes',
        'lang': 'es_ES', 'group_ids': [(6, 0, groups)]})
    print('Usuario creado', user.id)
if not env['res.users.apikeys'].sudo().search([('user_id', '=', user.id), ('name', '=', 'albaranes-ia')]):
    key = env['res.users.apikeys'].with_user(user)._generate(  # ámbito 'rpc': en Odoo 20 JSON-2 no acepta claves sin ámbito
        'rpc', 'albaranes-ia', fields.Datetime.now() + timedelta(days=90))  # caduca: obligatorio salvo admin
    with open('/tmp/albaranes_ia_apikey', 'w') as f:
        f.write(key)
    os.chmod('/tmp/albaranes_ia_apikey', 0o600)
    print('API key generada')

# Cliente en español
Partner = env['res.partner']
cliente = Partner.search([('name', '=', 'Supermercados Prueba IA')], limit=1)
if not cliente:
    cliente = Partner.create({
        'name': 'Supermercados Prueba IA', 'is_company': True, 'lang': 'es_ES',
        'street': 'Calle Mayor 1', 'city': 'Murcia', 'zip': '30001',
        'country_id': env.ref('base.es').id})

# Productos almacenables con stock
wh = env['stock.warehouse'].search([('company_id', '=', env.company.id)], limit=1)
nombres = ['Large Cabinet', 'Office Chair', 'Storage Box', 'Desk Pad', 'Pedal Bin', 'Conference Chair']
productos = env['product.product']
for nombre in nombres:
    productos |= env['product.product'].search([('name', '=', nombre), ('is_storable', '=', True)], limit=1)
for p in productos:
    if p.with_context(warehouse_id=wh.id).qty_available < 100:
        env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': p.id, 'location_id': wh.lot_stock_id.id,
            'inventory_quantity': 200}).action_apply_inventory()
print('Productos:', ', '.join(productos.mapped('display_name')))

cantidades = [12, 5, 24, 3, 8, 10]

def pedido(ref, n, validar):
    so = env['sale.order'].search([('client_order_ref', '=', ref)], limit=1)
    if not so:
        so = env['sale.order'].create({
            'partner_id': cliente.id, 'client_order_ref': ref,
            'order_line': [(0, 0, {'product_id': p.id, 'product_uom_qty': q})
                           for p, q in list(zip(productos, cantidades))[:n]]})
        so.action_confirm()
    pick = so.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')[:1]
    if validar and pick.state != 'done':
        pick.action_assign()
        for m in pick.move_ids:
            m.quantity = m.product_uom_qty
            m.picked = True
        pick.button_validate()
    if validar and not so.invoice_ids:
        so._create_invoices().action_post()
    elif not validar and pick.state != 'assigned':
        pick.action_assign()
    print(ref, so.name, pick.name, pick.id, pick.state, len(pick.move_ids), 'líneas',
          'factura', ','.join(so.invoice_ids.mapped('name')) or '-')

pedido('PRUEBA-IA-ENTREGADO', 5, True)   # para imprimir y fotografiar
pedido('PRUEBA-IA-PENDIENTE', 4, False)
if os.environ.get('RECTIFICACION'):        # desechables para pruebas/prueba_rectificacion.py
    pedido('PRUEBA-IA-RECT-HECHO', 5, True)
    pedido('PRUEBA-IA-RECT-PEND', 3, False)
env.cr.commit()
