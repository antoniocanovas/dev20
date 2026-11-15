from odoo import Command
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestScrapGaia(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ferrous = cls.env.ref('scrap_gaia.material_ferrous')
        cls.plastic = cls.env.ref('scrap_gaia.material_plastic')
        cls.tyres = cls.env.ref('scrap_gaia.material_tyres')
        cls.template = cls.env['product.template'].create({
            'name': 'Turismo GAIA',
            'type': 'consu',
            'is_storable': True,
            'is_template': True,
            'scrap_unbuild_type': 'main',
            'weight': 1000,
            'scrap_material_line_ids': [
                Command.create({'scrap_material_id': cls.ferrous.id, 'percent': 70}),
                Command.create({'scrap_material_id': cls.plastic.id, 'percent': 20}),
            ],
        })
        cls.other_template = cls.env['product.template'].create({
            'name': 'Moto GAIA',
            'type': 'consu',
            'is_storable': True,
            'is_template': True,
            'scrap_unbuild_type': 'main',
            'weight': 150,
            'scrap_material_line_ids': [Command.create({'scrap_material_id': cls.tyres.id, 'percent': 10})],
        })

    def _lines(self, record):
        return {line.scrap_material_id: line.percent if line._name == 'product.scrap.material' else line.weight
                for line in record.scrap_material_line_ids}

    def test_materials(self):
        materials = self.env['scrap.material'].search([])
        self.assertEqual(materials.mapped('name'), ['Férreo', 'No férreo', 'Metales', 'Plástico', 'Neumáticos'])

    def test_product_from_template(self):
        """ A vehicle copied from its template, as when its purchase is confirmed: its weight and
        its materials, editable without changing the template. """
        vehicle = self.template.copy({'name': 'Turismo 1234BCD', 'is_template': False, 'scrap_unbuild_type': 'main', 'scrap_template_id': self.template.id})
        self.assertEqual(vehicle.weight, 1000)
        self.assertEqual(self._lines(vehicle), {self.ferrous: 70, self.plastic: 20})
        self.assertAlmostEqual(vehicle.scrap_material_line_ids[0].weight, 700)
        vehicle.scrap_material_line_ids[0].percent = 65
        vehicle.weight = 950
        self.assertEqual(self._lines(self.template), {self.ferrous: 70, self.plastic: 20})
        self.assertEqual(self.template.weight, 1000)

        # Created with another template (as a product created by hand): the ones of the template
        product = self.env['product.template'].create({'name': 'Moto a mano', 'scrap_template_id': self.other_template.id})
        self.assertEqual((product.weight, self._lines(product)), (150, {self.tyres: 10}))
        # Its own ones, when given
        product = self.env['product.template'].create({
            'name': 'Moto pesada', 'scrap_template_id': self.other_template.id, 'weight': 300,
            'scrap_material_line_ids': [Command.create({'scrap_material_id': self.ferrous.id, 'percent': 50})],
        })
        self.assertEqual((product.weight, self._lines(product)), (300, {self.ferrous: 50}))

        # The template changed by hand: the ones of the new template, instead of the ones there
        vehicle.scrap_template_id = self.other_template
        self.assertEqual((vehicle.weight, self._lines(vehicle)), (150, {self.tyres: 10}))
        # The same template again: nothing changes
        vehicle.scrap_material_line_ids.percent = 15
        vehicle.scrap_template_id = self.other_template
        self.assertEqual(self._lines(vehicle), {self.tyres: 15})

        # In the form, as soon as the template is changed
        with Form(vehicle) as form:
            form.scrap_template_id = self.template
            self.assertEqual(form.weight, 1000)
            self.assertEqual(len(form.scrap_material_line_ids), 2)
        self.assertEqual(self._lines(vehicle), {self.ferrous: 70, self.plastic: 20})

    def test_percent_check(self):
        with self.assertRaises(Exception):
            self.template.scrap_material_line_ids[0].percent = 90
        with self.assertRaises(Exception):
            self.template.scrap_material_line_ids[0].percent = -1

    def test_delivery(self):
        """ The weight of each material of a delivery, from its products, editable, kept on
        validating it, and printed on the delivery slip. """
        part = self.template.copy({'name': 'Turismo 5678CDF', 'is_template': False, 'scrap_unbuild_type': 'main', 'scrap_template_id': self.template.id})
        part = part.product_variant_id
        bike = self.other_template.copy({'name': 'Moto 3456FGH', 'is_template': False, 'scrap_unbuild_type': 'refurbish',
                                         'scrap_template_id': self.other_template.id})
        bike = bike.product_variant_id
        no_weight = self.env['product.product'].create({'name': 'Sin peso', 'is_storable': True, 'scrap_unbuild_type': 'subproduct'})
        # Only bought and sold, without scrap type: left out, although it has weight and materials
        oil = self.env['product.product'].create({
            'name': 'Lata de aceite nueva', 'is_storable': True, 'weight': 5,
            'scrap_material_line_ids': [Command.create({'scrap_material_id': self.plastic.id, 'percent': 10})],
        })
        no_type = self.env['product.product'].create({'name': 'Sin tipo', 'is_storable': True})
        stock = self.env.ref('stock.stock_location_stock')
        for product in part | bike | no_weight | oil | no_type:
            self.env['stock.quant']._update_available_quantity(product, stock, 20)
        picking_type = self.env.ref('stock.picking_type_out')
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': stock.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'move_ids': [
                Command.create({'product_id': part.id, 'product_uom_qty': 2}),
                Command.create({'product_id': bike.id, 'product_uom_qty': 1}),
                Command.create({'product_id': no_weight.id, 'product_uom_qty': 1}),
                Command.create({'product_id': oil.id, 'product_uom_qty': 10}),
                Command.create({'product_id': no_type.id, 'product_uom_qty': 1}),
            ],
        })
        self.assertEqual(self._lines(picking), {self.ferrous: 1400, self.plastic: 400, self.tyres: 15})
        self.assertIn('Sin peso: without weight', picking.scrap_gaia_warning)
        self.assertNotIn('Turismo 5678CDF', picking.scrap_gaia_warning)
        self.assertNotIn('Sin tipo', picking.scrap_gaia_warning)

        # Another quantity: computed again
        picking.move_ids.filtered(lambda move: move.product_id == part).product_uom_qty = 1
        self.assertEqual(self._lines(picking), {self.ferrous: 700, self.plastic: 200, self.tyres: 15})

        # Written by hand, and kept on validating it and when the products change
        picking.scrap_material_line_ids.filtered(lambda line: line.scrap_material_id == self.ferrous).weight = 680
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.picked = True
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        part.weight = 2000
        self.assertEqual(self._lines(picking), {self.ferrous: 680, self.plastic: 200, self.tyres: 15})

        html = self.env['ir.actions.report']._render_qweb_html('stock.report_deliveryslip', picking.ids)[0].decode()
        self.assertIn('scrap_gaia_table', html)
        self.assertIn('Plástico', html)

        # Computed again from the products, as they are now
        picking.action_scrap_compute_gaia()
        self.assertEqual(self._lines(picking), {self.ferrous: 1400, self.plastic: 400, self.tyres: 15})

    def test_receipt_not_computed(self):
        """ Only the deliveries are computed: a receipt keeps what is written by hand. """
        product = self.template.copy({'name': 'Turismo 9012DFG', 'is_template': False, 'scrap_unbuild_type': 'main', 'scrap_template_id': self.template.id})
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': self.env.ref('stock.stock_location_stock').id,
            'move_ids': [Command.create({'product_id': product.product_variant_id.id, 'product_uom_qty': 1})],
        })
        self.assertFalse(picking.scrap_material_line_ids)
        self.assertFalse(picking.scrap_gaia_warning)
