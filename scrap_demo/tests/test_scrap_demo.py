from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestScrapDemo(TransactionCase):

    def test_demo_data(self):
        """ The vehicles of the demo, at each stage, and the one created by hand. """
        Template = self.env['product.template']
        vehicles = Template.search([('scrap_lot_name', 'in', ('1234BCD', '5678CDF', '9012DFG', '3456FGH'))])
        self.assertEqual(len(vehicles), 4)
        self.assertTrue(all(vehicles.mapped('discharge_date')))
        self.assertTrue(all(vehicles.mapped('scrap_location_id')))
        self.assertTrue(all(vehicles.mapped('default_code')), "Received, with their reference")
        late = vehicles.filtered(lambda vehicle: vehicle.scrap_lot_name == '1234BCD')
        self.assertLess(late.decontamination_days_left, 0)
        done = vehicles.filtered(lambda vehicle: vehicle.scrap_lot_name == '3456FGH')
        self.assertTrue(done.scrap_date)

        to_receive = Template.search([('scrap_lot_name', '=', '7890GHJ')])
        self.assertFalse(to_receive.discharge_date)
        self.assertEqual(Template.search([('scrap_lot_name', '=', '2468HJK')]).scrap_unbuild_type, 'refurbish')

        by_hand = Template.search([('scrap_lot_name', '=', '8642KLM')])
        self.assertFalse(by_hand.scrap_analytic_account_id)
        self.assertFalse(by_hand.sale_ok, "To dismantle, not sold whole")
        by_hand.action_scrap_complete_vehicle()
        self.assertEqual(by_hand.scrap_location_id.name, '8642KLM')
        self.assertEqual(by_hand.bom_ids.code, 'Despiece turismo', "Copied from its template")

        # The bills of materials of the templates, copied for each vehicle
        car = vehicles.filtered(lambda vehicle: vehicle.scrap_lot_name == '1234BCD')
        self.assertEqual(car.bom_ids.code, 'Despiece turismo')
        self.assertEqual(len(car.bom_ids.operation_ids), 2)
        self.assertEqual(car.bom_ids.bom_line_ids.product_id, self.env.ref('scrap_demo.bom_car').bom_line_ids.product_id)
        self.assertEqual(done.bom_ids.code, 'Despiece motocicleta')
        van = vehicles.filtered(lambda vehicle: vehicle.scrap_lot_name == '9012DFG')
        self.assertEqual(van.bom_ids.code, 'Despiece furgoneta')
        dismantled = van.scrap_dismantle_line_ids.filtered(lambda part: part.stage == 'dismantling')
        self.assertEqual(sorted(dismantled.mapped('result')), ['discarded', 'dismantled', 'dismantled'], "Half dismantled")
        # The oil taken out while decontaminating, into the waste zone
        oil = self.env.ref('scrap_demo.waste_oil')
        self.assertIn(oil, self.env.company.scrap_waste_product_ids)
        self.assertEqual(oil.uom_id, self.env.ref('uom.product_uom_litre'))
        waste = van.scrap_dismantle_line_ids.filtered(lambda part: part.stage == 'decontamination')
        self.assertEqual((waste.product_id, waste.quantity, waste.location_dest_id), (oil, 4.5, self.env.company.scrap_waste_location_id))
        self.assertEqual(sum(van.bom_ids.bom_line_ids.filtered(lambda line: line.product_id == self.env.ref('scrap_demo.comp_wheel')).mapped('product_qty')), 2)

        # The engine of a car, a scrap template: dismantled, a product of its own
        car.decontamination_date = car.discharge_date
        engine_line = car.bom_ids.bom_line_ids.filtered(lambda line: line.product_id.is_template)
        self.assertEqual(engine_line.product_id, self.env.ref('scrap_demo.template_engine').product_variant_id)
        engine = car._scrap_dismantle(engine_line, 1, 'dismantled', 'good').product_id
        self.assertEqual(engine.name, f"Motor usado {car.default_code}")
        self.assertEqual(engine.bom_ids.code, 'Despiece motor')
        self.assertEqual((engine.scrap_unbuild_type, engine.scrap_origin_id), ('subproduct', car))
        # Its cylinder head, a scrap template too: a subproduct of the car, with its own bill
        head_line = engine.bom_ids.bom_line_ids.filtered(lambda line: line.product_id.is_template)
        self.assertEqual(head_line.product_id, self.env.ref('scrap_demo.comp_cylinder_head'))
        head = engine.product_tmpl_id._scrap_dismantle(head_line, 1, 'dismantled', 'good').product_id
        self.assertEqual((head.scrap_unbuild_type, head.scrap_origin_id), ('subproduct', car))
        self.assertEqual(head.bom_ids.code, 'Despiece culata')
        self.assertEqual(head.bom_ids.bom_line_ids.product_id,
                         self.env.ref('scrap_demo.comp_valve') | self.env.ref('scrap_demo.comp_camshaft'))

        # The engine is a template in every vehicle; the van's, dismantled, and an engine bought
        # are in the list of the subproducts to dismantle
        template_engine = self.env.ref('scrap_demo.template_engine').product_variant_id
        for xmlid in ('bom_car', 'bom_van', 'bom_motorbike'):
            self.assertIn(template_engine, self.env.ref(f'scrap_demo.{xmlid}').bom_line_ids.product_id)
        van_engine = Template.search([('scrap_origin_id', '=', van.id)])
        self.assertEqual(van_engine.scrap_template_id, self.env.ref('scrap_demo.template_engine'))
        bought = Template.search([('scrap_lot_name', '=', 'MOTOR0001')])
        self.assertEqual((bought.scrap_unbuild_type, bought.scrap_origin_id.id), ('subproduct', False))
        self.assertTrue(bought.discharge_date, "Received")
        self.assertTrue(bought.sale_ok, "Also sold whole")
        listed = [item['id'] for item in self.env['scrap.touch'].get_vehicles('', 'subproduct', 'scrap')]
        self.assertIn(van_engine.id, listed)
        self.assertIn(bought.id, listed)

        # The templates are neither bought nor sold; a vehicle to repair is sold whole
        templates = Template.search([('is_template', '=', True), ('id', 'in', [
            self.env.ref(f'scrap_demo.template_{name}').id for name in ('car', 'van', 'motorbike', 'engine')])])
        self.assertEqual(len(templates), 4)
        self.assertFalse(any(templates.mapped('purchase_ok')) or any(templates.mapped('sale_ok')))
        self.assertTrue(all(templates.mapped('bom_ids')), "Each template to dismantle or subproduct has its bill of materials")
        self.assertEqual(self.env.ref('scrap_demo.template_engine').scrap_unbuild_type, 'subproduct')
        berlingo = Template.search([('scrap_lot_name', '=', '2468HJK')])
        self.assertTrue(berlingo.sale_ok)

        # The Berlingo, being repaired to sell it: confirmed, with a clutch kit and 3 hours of
        # labour; once finished, their costs go to its analytic account
        repair = berlingo._scrap_open_repairs()
        self.assertEqual(len(repair), 1)
        self.assertEqual(repair.state, 'confirmed')
        self.assertFalse(repair.partner_id, "In stock: repaired to sell it")
        self.assertEqual(repair.lot_id.name, '2468HJK')
        self.assertEqual(repair.move_ids.product_id, self.env.ref('scrap_demo.part_clutch'))
        self.assertEqual(self.env['scrap.touch'].get_vehicle(berlingo.id)['open_repair'], repair.name)
        repair.move_ids.quantity = 1
        repair.move_ids.picked = True
        repair.action_repair_end()
        account = berlingo.scrap_analytic_account_id
        lines = self.env['account.analytic.line'].search([(account.plan_id._column_name(), '=', account.id)])
        self.assertEqual(sorted(lines.mapped('amount')), [-120.0, -75.0], "The clutch kit and 3 hours of labour")
        self.assertIn(self.env.ref('scrap_demo.template_car').product_variant_id,
                      self.env['scrap.touch']._get_entry_products(), "Offered by the touch screen")

        # The brand of the vehicles, from their make/model, as the one of the opportunities
        self.assertEqual(car.scrap_vehicle_brand_id, self.env.ref('fleet.brand_renault'))

        # Opportunities of customers asking for parts, with their brand, prices and tasks
        leads = self.env['crm.lead'].search([('partner_id', 'in', [
            self.env.ref(f'scrap_demo.partner_{name}').id for name in ('taller', 'particular', 'recambios')])])
        self.assertEqual(len(leads), 5)
        self.assertTrue(all(leads.mapped('brand_id')))
        self.assertEqual(leads.brand_id._name, 'fleet.vehicle.model.brand')
        self.assertEqual(set(leads.stage_id.mapped('type')), {'comercial', 'taller', 'cliente', 'positiva'})
        engine = leads.filtered(lambda lead: lead.name == 'Motor 1.5 dCi para Clio IV')
        self.assertEqual((engine.market_value, engine.quotation_value), (950.0, 780.0))
        self.assertEqual(engine.scrap_template_id, self.env.ref('scrap_demo.template_engine'))
        self.assertEqual(engine.display_name, f"TL01 {engine.name}", "With the reference of the customer")
        self.assertEqual(engine.partner_tag_ids, self.env.ref('scrap_demo.partner_tag_workshop'))
        self.assertEqual(len(engine.task_ids), 2)
        self.assertEqual(engine.task_ids.product_tmpl_id, car)
        self.assertEqual(engine.task_ids.project_id, self.env.ref('scrap_demo.project_scrap'))
        # Their deadline is the one of Odoo (kanban, list and colours), from today: one today, others late
        tasks = leads.task_ids
        self.assertTrue(all(tasks.mapped('date_deadline')))
        today = fields.Datetime.now().date()
        days = sorted((deadline.date() - today).days for deadline in tasks.mapped('date_deadline'))
        self.assertEqual(days, [-2, -1, 0, 1, 3])
        # The vehicles and parts of its brand in stock, from the opportunity
        renault = self.env['product.template'].search(engine._get_scrap_available_domain())
        self.assertIn(car, renault, "The Clio, received")
        self.assertNotIn(Template.search([('scrap_lot_name', '=', '9012DFG')]), renault, "A Ford")
        self.assertEqual(engine.scrap_available_count, len(renault))
        action = engine.action_scrap_available_parts()
        self.assertEqual((action['tag'], action['params']), ('scrap_crm.available', {'lead_id': engine.id}))
        # On its screen: in stock, of Renault; assembled, the Renault cars with their used engine
        # still to dismantle (not the Clio, which was dismantled above)
        Available = self.env['scrap.crm.available']
        data = Available.get_screen_data(engine.id)
        self.assertEqual((data['brand_id'], data['template_id']), (engine.brand_id.id, engine.scrap_template_id.id))
        in_stock = Available.search_available('stock', '', data['brand_id'])
        self.assertIn(car.id, [product['id'] for product in in_stock['products']])
        golf = Template.search([('scrap_lot_name', '=', '5678CDF')])
        assembled = Available.search_available('assembled', '', False, data['template_id'])['products']
        self.assertIn(golf.id, [product['id'] for product in assembled], "With its used engine")
        self.assertNotIn(car.id, [product['id'] for product in assembled], "Its engine, dismantled")
        self.assertEqual(Available.search_available('stock', 'VF1BR1A0H12345678')['products'][0]['id'], car.id, "By chassis")
        self.assertEqual(self.env.company.scrap_project_id, self.env.ref('scrap_demo.project_scrap'))

        # Each product with an image of its own, a solid colour with its name
        products = car | van | van_engine | bought | self.env.ref('scrap_demo.template_engine') | self.env.ref('scrap_demo.part_alternator')
        self.assertTrue(all(products.mapped('image_1920')))
        self.assertEqual(len(set(products.mapped('image_1920'))), len(products), "All different")

        # The clutch kit, a new spare part, replenished from Recambios Norte
        clutch = self.env.ref('scrap_demo.part_clutch')
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        replenish = self.env['product.replenish'].create({
            'product_id': clutch.id, 'product_tmpl_id': clutch.product_tmpl_id.id,
            'quantity': 2, 'uom_id': clutch.uom_id.id, 'warehouse_id': warehouse.id,
        })
        replenish.launch_replenishment()
        purchase = self.env['purchase.order.line'].search([('product_id', '=', clutch.id), ('order_id.state', '=', 'draft')]).order_id
        self.assertEqual(purchase.partner_id, self.env.ref('scrap_demo.partner_recambios'))

        # The parts are found by their CAT data
        self.assertIn(self.env.ref('scrap_demo.part_alternator').product_variant_id,
                      self.env['product.product'].search([('display_name', 'ilike', 'TG11C068')]))

    def test_demo_files(self):
        """ The files (Expedientes) of the demo: templates and files made of them. """
        Project = self.env['project.project'].with_context(active_test=False)
        templates = Project.search([('is_template', '=', True), ('touch_ok', '=', True)])
        self.assertEqual(set(templates.mapped('name')) & {
            'Salida de residuos', 'Onboarding de empleado', 'Gestión AEAT mensual', 'Formación de taller'},
            {'Salida de residuos', 'Onboarding de empleado', 'Gestión AEAT mensual', 'Formación de taller'})
        self.assertTrue(all(templates.filtered(lambda t: t.name == 'Gestión AEAT mensual').mapped('date')), "With planned dates")
        self.assertTrue(all(templates.task_ids.filtered(lambda task: not task.parent_id).mapped('date_deadline')),
                        "With deadlines, moved to the files made of them")
        files = Project.search([('touch_template_id', 'in', templates.ids)])
        self.assertTrue(all(files.mapped('date')), "With an end, from the template")
        self.assertTrue(all(files.mapped('touch_ok')))
        self.assertGreaterEqual(len(files), 6)
        today = fields.Date.context_today(files)

        # Waste: one task each month; the last one done, this one created by its recurrence
        waste = files.filtered(lambda file: file.name == 'Salida de residuos')
        pickups = waste.task_ids.filtered(lambda task: not task.parent_id).sorted('date_deadline')
        self.assertEqual(len(pickups), 2)
        self.assertEqual(pickups.mapped('state'), ['1_done', '01_in_progress'])
        self.assertTrue(all(pickups.mapped('recurring_task')))
        self.assertEqual(pickups[1].date_deadline.month, today.month, "The one of this month")
        self.assertEqual(len(pickups[1].child_ids), 4, "With its subtasks")

        # Onboarding: the presentation waits for the training in risks, still open
        juan = files.filtered(lambda file: file.name == 'Onboarding Juan Pérez (mecánico)')
        tasks = {task.name: task for task in juan.task_ids}
        self.assertEqual(tasks['Contrato y alta en la Seguridad Social'].state, '1_done')
        self.assertEqual(tasks['Formación inicial en prevención de riesgos'].state, '01_in_progress')
        self.assertEqual(tasks['Presentación al equipo y acompañamiento la primera semana'].state, '04_waiting_normal')
        self.assertTrue(tasks['Formación inicial en prevención de riesgos'].date_deadline.date() < today, "Late")

        # AEAT: the month before the last one presented, the last one under way
        aeat = files.filtered(lambda file: file.name.startswith('AEAT')).sorted('date_start')
        self.assertEqual(len(aeat), 2)
        self.assertTrue(all(state == '1_done' for state in aeat[0].task_ids.mapped('state')))
        self.assertIn('04_waiting_normal', aeat[1].task_ids.mapped('state'), "The submission waits for the 303")

        # Training: courses with their steps as subtasks
        training = files.filtered(lambda file: file.name.startswith('Formación de taller'))
        vfu = training.task_ids.filtered(lambda task: task.name.startswith('Descontaminación'))
        self.assertEqual(sorted(vfu.child_ids.mapped('state')), ['01_in_progress', '1_done', '1_done'])
