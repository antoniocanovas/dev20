import base64
import colorsys
import io
import textwrap
import uuid
from datetime import timedelta

from PIL import Image, ImageDraw, ImageFont

from odoo import Command, fields

from .demo_files import create_files

# Vehicles of the demo: (template, plate, make/model, chassis, price, days since their discharge,
# days since their decontamination, days since their dismantling). The dates go back from today,
# so that the CAT lists show vehicles late, close to their limit and done.
# Stages of the pipeline and their type of scrap_crm: the ones of crm, when they exist
CRM_STAGES = [
    ('crm.stage_lead1', 'New', 'comercial'),
    ('crm.stage_lead2', 'Qualified', 'taller'),
    ('crm.stage_lead3', 'Proposition', 'cliente'),
    ('crm.stage_lead4', 'Won', 'positiva'),
]
TO_DISMANTLE = [
    ('template_car', '1234BCD', 'model_renault_clio', 'VF1BR1A0H12345678', 350.0, 12, None, None),
    ('template_car', '5678CDF', 'model_volkswagen_golf', 'WVWZZZ1KZ6W123456', 420.0, 8, None, None),
    ('template_van', '9012DFG', 'model_ford_transit', 'WF0XXXTTGX1234567', 900.0, 25, 20, None),
    ('template_motorbike', '3456FGH', 'model_honda_cbr', 'JH2PC37A07M123456', 150.0, 40, 35, 15),
]


def post_init_hook(env):
    company = env.company
    _set_company(company)
    gruas = env.ref('scrap_demo.partner_gruas')
    taller = env.ref('scrap_demo.partner_taller')
    particular = env.ref('scrap_demo.partner_particular')
    today = fields.Date.context_today(company)
    # Vehicles to dismantle, received, at each stage of their legal deadlines
    order = _buy(env, gruas, 'main', [(template, plate, price) for template, plate, _m, _c, price, *_d in TO_DISMANTLE])
    _receive(order)
    oil = env.ref('scrap_demo.waste_oil')
    for line, (_t, plate, model, chassis, _price, discharge, decontamination, dismantling) in zip(order.order_line, TO_DISMANTLE):
        vehicle = line.product_id.product_tmpl_id
        vehicle.write({
            'vehicle_model_id': env.ref(f'scrap_demo.{model}').id,
            'chassis': chassis,
            'discharge_date': today - timedelta(days=discharge),
        })
        # The oil taken out of the decontaminated ones, into the waste zone
        if decontamination:
            vehicle._scrap_decontaminate(oil, 4.5 if plate == '9012DFG' else 1.5, 'discarded')
        vehicle.write({
            'decontamination_date': decontamination and today - timedelta(days=decontamination),
            'scrap_date': dismantling and today - timedelta(days=dismantling),
        })

    # The van decontaminated, half dismantled: two wheels in good condition, the battery
    # discarded and its engine, a scrap template: a subproduct of the van, to dismantle
    van = order.order_line.product_id.product_tmpl_id.filtered(lambda vehicle: vehicle.scrap_lot_name == '9012DFG')
    lines = van.bom_ids.bom_line_ids
    van._scrap_dismantle(lines.filtered(lambda line: line.product_id == env.ref('scrap_demo.comp_wheel')), 2, 'dismantled', 'good')
    van._scrap_dismantle(lines.filtered(lambda line: line.product_id == env.ref('scrap_demo.comp_battery')), 1, 'discarded')
    engine = env.ref('scrap_demo.template_engine').product_variant_id
    van._scrap_dismantle(lines.filtered(lambda line: line.product_id == engine), 1, 'dismantled', 'functional')

    # A used engine bought to dismantle it, received: a subproduct without origin
    # It can also be sold whole
    order = _buy(env, taller, 'main', [('template_engine', 'MOTOR0001', 120.0)])
    _receive(order)
    order.order_line.product_id.sale_ok = True

    # Given by a private person, for nothing: bought at 0, still to receive
    order = _buy(env, particular, 'main', [('template_car', '7890GHJ', 0.0)])
    order.order_line.product_id.vehicle_model_id = env.ref('scrap_demo.model_peugeot_308')

    # To repair and sell whole, received
    order = _buy(env, taller, 'refurbish', [('template_van', '2468HJK', 3500.0)])
    order.order_line.product_id.vehicle_model_id = env.ref('scrap_demo.model_citroen_berlingo')
    _receive(order)
    _create_repair(env, order.order_line.product_id.product_tmpl_id)

    # A request for quotation saved on the touch screen, to resume it there
    order = _buy(env, gruas, 'main', [('template_car', '1357JKL', 300.0)], confirm=False)
    order.scrap_touch_uuid = str(uuid.uuid4())

    # A vehicle created by hand in the backend: without its analytic account nor its location,
    # which the button "Complete CAT Data" of its CAT tab creates
    env['product.template'].create({
        'name': 'Turismo 8642KLM',
        'type': 'consu',
        'is_storable': True,
        'tracking': 'serial',
        'categ_id': env.ref('scrap_demo.category_vehicles').id,
        'company_id': company.id,
        'scrap_template_id': env.ref('scrap_demo.template_car').id,
        'scrap_unbuild_type': 'main',
        'scrap_lot_name': '8642KLM',
        # To dismantle, not sold whole, as the ones bought
        'sale_ok': False,
        'vehicle_model_id': env.ref('scrap_demo.model_opel_corsa').id,
    })

    _create_opportunities(env)
    # Files (Expedientes): templates of the management of the yard and files made of them
    create_files(env)
    _set_images(env)


def _create_repair(env, vehicle):
    """ The Berlingo, in stock, being repaired to sell it (scrap_repair): a new clutch kit and
    3 hours of labour, confirmed, to finish it; then their costs go to the analytic account of
    the vehicle. The clutch kits are in stock. """
    clutch = env.ref('scrap_demo.part_clutch')
    warehouse = env['stock.warehouse'].search([('company_id', '=', vehicle.company_id.id or env.company.id)], limit=1)
    env['stock.quant']._update_available_quantity(clutch, warehouse.lot_stock_id, 5)
    repair = vehicle._scrap_get_repair()
    repair.write({
        'internal_notes': '<p>Patina el embrague: cambiar el kit completo antes de venderla.</p>',
        'move_ids': [Command.create({'product_id': clutch.id, 'product_uom_qty': 1, 'repair_line_type': 'add'})],
        'repair_service_line_ids': [Command.create({'product_id': env.ref('scrap_demo.service_labour').id, 'quantity': 3})],
    })
    repair.action_validate()
    return repair


def _create_opportunities(env):
    """ Opportunities of customers asking for parts, at each stage of the pipeline, with the
    brand, the prices and the tasks of the workshop (scrap_crm), some of them on the vehicles of
    the demo. Their brand is the one of Fleet, as the one of the vehicles and their parts. The
    project of the tasks and its user are set in the company, if it has none. """
    company = env.company
    admin = env.ref('base.user_admin')
    project = env.ref('scrap_demo.project_scrap')
    vals = {}
    if not company.scrap_project_id:
        vals['scrap_project_id'] = project.id
    if not company.scrap_user_id:
        vals['scrap_user_id'] = admin.id
    if vals:
        company.write(vals)
    stages = {}
    for sequence, (xmlid, name, stage_type) in enumerate(CRM_STAGES):
        stage = env.ref(xmlid, raise_if_not_found=False) or env['crm.stage'].create({'name': name, 'sequence': sequence})
        if not stage.type:
            stage.type = stage_type
        stages[stage_type] = stage
    Template = env['product.template']
    clio = Template.search([('scrap_lot_name', '=', '1234BCD')], limit=1)
    transit = Template.search([('scrap_lot_name', '=', '9012DFG')], limit=1)
    cbr = Template.search([('scrap_lot_name', '=', '3456FGH')], limit=1)
    today = fields.Datetime.now()
    opportunities = [
        # (customer, brand, name, stage, market price, quoted price, price note, sales notes,
        #  technical notes, tasks: (name, category, product, tags, stage, days to the deadline:
        #  some late, one today, some to come))
        ('partner_taller', 'fleet.brand_renault', 'Motor 1.5 dCi para Clio IV', 'cliente', 950.0, 780.0,
         '700 - 800 €', 'Lo necesita para un cliente esta semana.',
         'Motor K9K. Comprobar compresión y fugas antes de ofertar.',
         [('Comprobar compresión del motor', 'scrap_category_mechanics', clio, ['task_tag_check'], 'task_stage_doing', 0),
          ('Fotografiar motor', 'scrap_category_mechanics', clio, ['task_tag_photo'], 'task_stage_done', -1)]),
        ('partner_particular', 'fleet.brand_volkswagen', 'Faro delantero izquierdo Golf VI', 'comercial', 180.0, 0.0,
         '', 'Pregunta por teléfono si lo tenemos y el precio.', '',
         [('Buscar faro en stock', 'scrap_category_electrics', env.ref('scrap_demo.part_headlight'), ['task_tag_check'], 'task_stage_todo', 1)]),
        ('partner_recambios', 'fleet.brand_ford', 'Puerta lateral corredera Transit', 'positiva', 300.0, 250.0,
         '250 €', 'Aceptada: la recoge el viernes.', 'Color blanco, sin golpes.',
         [('Desmontar puerta corredera', 'scrap_category_body', transit, ['task_tag_dismantle'], 'task_stage_done', -2)]),
        ('partner_recambios', 'fleet.brand_honda', 'Manillar CBR 600', 'taller', 90.0, 70.0,
         '60 - 75 €', 'Para una CBR 600 de 2007.', 'Revisar que no esté doblado.',
         [('Desmontar manillar', 'scrap_category_body', cbr, ['task_tag_dismantle', 'task_tag_check'], 'task_stage_todo', 3)]),
        ('partner_taller', 'fleet.brand_renault', 'Alternador Clio III (Valeo TG11C068)', 'comercial', 120.0, 0.0,
         '', 'Busca el alternador por la referencia Valeo.', 'Referencia OEM 231001234R.',
         []),
    ]
    for partner, brand, name, stage, market, quoted, note, description, technical, tasks in opportunities:
        lead = env['crm.lead'].create({
            'type': 'opportunity',
            'name': name,
            'partner_id': env.ref(f'scrap_demo.{partner}').id,
            'brand_id': env.ref(brand).id,
            'stage_id': stages[stage].id,
            'user_id': admin.id,
            'market_value': market,
            'quotation_value': quoted,
            'expected_revenue': quoted or market,
            'price_note': note,
            'description': description and f'<p>{description}</p>',
            'description_tech': technical,
        })
        if name.startswith('Motor'):
            # What the customer asks for: a used engine
            lead.scrap_template_id = env.ref('scrap_demo.template_engine')
        env['project.task'].create([{
            'name': task_name,
            'lead_id': lead.id,
            'project_id': project.id,
            'partner_id': lead.partner_id.id,
            'brand_id': lead.brand_id.id,
            'categ_id': env.ref(f'scrap_demo.{category}').id,
            'product_tmpl_id': product.id,
            'tag_ids': [Command.set([env.ref(f'scrap_demo.{tag}').id for tag in tags])],
            'stage_id': env.ref(f'scrap_demo.{task_stage}').id,
            'user_ids': [Command.set(admin.ids)],
            # The deadline of Odoo (a datetime since v18), the one of the kanban, the list and
            # their colours: red when late, yellow today
            'date_deadline': today + timedelta(days=days),
        } for task_name, category, product, tags, task_stage, days in tasks])


def _set_company(company):
    """ The sequences of the vehicles and the legal days, where the company has none, and the
    oil to recycle as a waste of the decontamination. """
    Sequence = company.env['ir.sequence']
    vals = {'scrap_waste_product_ids': [Command.link(company.env.ref('scrap_demo.waste_oil').id)]}
    if not company.scrap_main_sequence_id:
        vals['scrap_main_sequence_id'] = Sequence.create({
            'name': 'Vehículos para desguazar', 'prefix': 'DES%(year)s-', 'padding': 5,
            'company_id': company.id,
        }).id
    if not company.scrap_refurbish_sequence_id:
        vals['scrap_refurbish_sequence_id'] = Sequence.create({
            'name': 'Vehículos compra / venta', 'prefix': 'CV%(year)s-', 'padding': 5,
            'company_id': company.id,
        }).id
    if not company.decontamination_days:
        vals['decontamination_days'] = 10
    if not company.scrap_days:
        vals['scrap_days'] = 30
    if vals:
        company.write(vals)


def _buy(env, partner, unbuild_type, lines, confirm=True):
    """ A purchase of vehicles, one per line: (xmlid of the template, plate, price). """
    order = env['purchase.order'].create({
        'partner_id': partner.id,
        'unbuild_type': unbuild_type,
        'order_line': [Command.create({
            'product_id': env.ref(f'scrap_demo.{template}').product_variant_id.id,
            'product_qty': 1,
            'price_unit': price,
            'scrap_lot_name': plate,
        }) for template, plate, price in lines],
    })
    if confirm:
        order.button_confirm()
    return order


def _receive(order):
    picking = order.picking_ids.filtered(lambda picking: picking.state not in ('done', 'cancel'))
    picking.move_ids.picked = True
    picking.button_validate()


# Demo images: a solid colour with the name of the product
IMAGE_SIZE = 768
FONT_SIZE = 72
GOLDEN_RATIO = 0.618033988749895


def _set_images(env):
    """ An image for each product of the demo, the ones of its data and the ones made of its
    templates (the vehicles bought, the parts dismantled...), each one of a different solid
    colour, with its name. Only for the ones without image. """
    Template = env['product.template']
    data = env['ir.model.data'].search([('module', '=', 'scrap_demo'), ('model', 'in', ('product.template', 'product.product'))])
    products = Template.browse(data.filtered(lambda xmlid: xmlid.model == 'product.template').mapped('res_id'))
    products |= env['product.product'].browse(data.filtered(lambda xmlid: xmlid.model == 'product.product').mapped('res_id')).product_tmpl_id
    products |= Template.search([('scrap_template_id', 'in', products.ids)])
    for index, product in enumerate(products.exists().sorted('id')):
        if not product.image_1920:
            product.image_1920 = _demo_image(product.name, (index * GOLDEN_RATIO) % 1)


def _demo_image(name, hue):
    """ A PNG of a solid colour, of the hue given, with the name centred on it. """
    red, green, blue = (round(value * 255) for value in colorsys.hsv_to_rgb(hue, 0.55, 0.8))
    image = Image.new('RGB', (IMAGE_SIZE, IMAGE_SIZE), (red, green, blue))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=FONT_SIZE)
    # Dark text on the light colours, white on the dark ones
    light = (0.299 * red + 0.587 * green + 0.114 * blue) > 150
    text = "\n".join(textwrap.wrap(name, width=16)[:5])
    draw.multiline_text((IMAGE_SIZE / 2, IMAGE_SIZE / 2), text, font=font, anchor='mm', align='center',
                        spacing=FONT_SIZE // 4, fill=(33, 37, 41) if light else (255, 255, 255))
    output = io.BytesIO()
    image.save(output, format='PNG', optimize=True)
    return base64.b64encode(output.getvalue()).decode()
