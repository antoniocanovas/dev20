import base64
import io
import uuid

from PIL import Image

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestScrapCrmAvailable(TransactionCase):
    """ What is available for an opportunity: in stock, of a brand, and assembled, with the
    scrap template asked for still to dismantle. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Product = cls.env['product.product']
        cls.brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'CRM Brand'})
        cls.other_brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'CRM Other Brand'})
        cls.model = cls.env['fleet.vehicle.model'].create({'name': 'CRM Model', 'brand_id': cls.brand.id})
        cls.engine = Product.create({
            'name': 'CRM Engine', 'type': 'consu', 'is_storable': True,
            'is_template': True, 'scrap_unbuild_type': 'subproduct',
        })
        cls.car = Product.create({
            'name': 'CRM Car', 'type': 'consu', 'is_storable': True, 'tracking': 'serial',
            'is_template': True, 'vehicle_model_id': cls.model.id, 'supplier_taxes_id': [Command.clear()],
        })
        cls.env['mrp.bom'].create({
            'product_tmpl_id': cls.car.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': cls.engine.id, 'product_qty': 1})],
        })
        supplier = cls.env['res.partner'].create({'name': 'CRM Supplier'})
        result = cls.env['scrap.touch'].purchase_entry({
            'uuid': str(uuid.uuid4()), 'partner_id': supplier.id, 'unbuild_type': 'main',
            'lines': [{'product_id': cls.car.id, 'lot_name': 'CRM0001', 'price_unit': 100.0}],
        })
        cls.vehicle = cls.env['purchase.order'].browse(result['id']).order_line.product_id.product_tmpl_id
        cls.vehicle.decontamination_date = cls.vehicle.discharge_date
        stock = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1).lot_stock_id
        cls.wheel = Product.create({'name': 'CRM Wheel', 'type': 'consu', 'is_storable': True, 'barcode': 'CRM-BAR-1'})
        cls.alternator = Product.create({
            'name': 'CRM Alternator', 'type': 'consu', 'is_storable': True,
            'vehicle_model_id': cls.model.id, 'ref_oem': 'CRM-OEM-1', 'ref_market': 'CRM-VIS-1',
        })
        cls.env['stock.quant']._update_available_quantity(cls.wheel, stock, 4)
        cls.env['stock.quant']._update_available_quantity(cls.alternator, stock, 1)
        cls.user = new_test_user(cls.env, login='crm_available', groups='sales_team.group_sale_salesman,stock.group_stock_user')
        cls.lead = cls.env['crm.lead'].create({
            'user_id': cls.user.id, 'name': 'CRM Engine asked', 'type': 'opportunity',
            'brand_id': cls.brand.id, 'scrap_template_id': cls.engine.product_tmpl_id.id,
        })
        cls.Available = cls.env['scrap.crm.available'].with_user(cls.user)

    def _ids(self, mode, query='', brand=False, template=False):
        result = self.Available.search_available(mode, query, brand and brand.id, template and template.id)
        return result['products'], result['counts']

    def test_screen_data(self):
        data = self.Available.get_screen_data(self.lead.id)
        self.assertEqual((data['brand_id'], data['template_id']), (self.brand.id, self.engine.product_tmpl_id.id))
        self.assertIn(self.brand.id, [brand['id'] for brand in data['brands']])
        self.assertNotIn(self.other_brand.id, [brand['id'] for brand in data['brands']], "Without products")
        self.assertIn(self.engine.product_tmpl_id.id, [template['id'] for template in data['templates']])
        action = self.lead.action_scrap_available_parts()
        self.assertEqual((action['tag'], action['params']), ('scrap_crm.available', {'lead_id': self.lead.id}))
        with self.assertRaises(ValidationError):
            self.Available.get_screen_data('x')

    def test_in_stock(self):
        """ The products in stock of the brand, or of all; by name, barcode and references. """
        ids = lambda products: {product['id'] for product in products}  # noqa: E731
        products, counts = self._ids('stock', brand=self.brand)
        self.assertEqual(ids(products) & {self.vehicle.id, self.alternator.product_tmpl_id.id, self.wheel.product_tmpl_id.id},
                         {self.vehicle.id, self.alternator.product_tmpl_id.id}, "Of the brand")
        self.assertEqual(counts['stock'], len(products))
        products, _counts = self._ids('stock')
        self.assertIn(self.wheel.product_tmpl_id.id, ids(products), "All the brands")
        self.assertNotIn(self.car.product_tmpl_id.id, ids(products), "Not the templates")
        for query, product in (('crm-oem-1', self.alternator), ('CRM-VIS-1', self.alternator),
                               ('CRM-BAR-1', self.wheel), ('crm 0001', self.vehicle)):
            products, _counts = self._ids('stock', query)
            self.assertEqual(ids(products), {product.product_tmpl_id.id if product._name == 'product.product' else product.id}, query)
        vehicle = next(product for product in self._ids('stock', 'CRM0001')[0])
        self.assertEqual((vehicle['plate'], vehicle['brand']), ('CRM0001', 'CRM Brand'))

    def test_in_stock_template(self):
        """ In stock, of the template asked for: the products made of it, as the engine
        dismantled; with the brand too. """
        engine = self.engine.product_tmpl_id
        self.assertEqual(self._ids('stock', template=engine)[0], [], "Not dismantled yet")
        part = self.vehicle._scrap_dismantle(self.vehicle.bom_ids.bom_line_ids, 1, 'dismantled', 'good')
        copy = part.product_id.product_tmpl_id
        products, counts = self._ids('stock', template=engine)
        self.assertEqual([product['id'] for product in products], [copy.id])
        self.assertEqual(counts['stock'], 1)
        self.assertEqual([product['id'] for product in self._ids('stock', brand=self.brand, template=engine)[0]], [copy.id])
        self.assertEqual(self._ids('stock', brand=self.other_brand, template=engine)[0], [], "Both conditions")

    def test_assembled(self):
        """ In stock, with the engine still to dismantle; not anymore once dismantled. """
        products, counts = self._ids('assembled', brand=self.brand, template=self.engine.product_tmpl_id)
        self.assertEqual([product['id'] for product in products], [self.vehicle.id])
        self.assertEqual((products[0]['pending_qty'], products[0]['pending_name']), (1, 'CRM Engine'))
        self.assertEqual(counts['assembled'], 1)
        self.assertEqual(self._ids('assembled', brand=self.other_brand, template=self.engine.product_tmpl_id)[0], [])
        self.assertEqual(self._ids('assembled'), ([], self._ids('assembled')[1]))
        self.assertEqual(self._ids('assembled')[1]['assembled'], 0, "Without template")
        self.vehicle._scrap_dismantle(self.vehicle.bom_ids.bom_line_ids, 1, 'dismantled', 'good')
        self.assertEqual(self._ids('assembled', template=self.engine.product_tmpl_id)[0], [], "Dismantled")
        with self.assertRaises(ValidationError):
            self.Available.search_available('other')

    @staticmethod
    def _image(color):
        output = io.BytesIO()
        Image.new('RGB', (64, 64), color).save(output, format='PNG')
        return base64.b64encode(output.getvalue()).decode()

    def test_product_images(self):
        """ The photos of a product, as in the shop: the main one first, then the extra ones. """
        product = self.alternator.product_tmpl_id
        self.assertEqual(self.Available.get_product_images(product.id), [], "Without photos")
        product.image_1920 = self._image('red')
        self.env['product.image'].create([{
            'name': f'CRM photo {color}', 'product_tmpl_id': product.id, 'image_1920': self._image(color),
        } for color in ('green', 'blue')])
        images = self.Available.get_product_images(product.id)
        self.assertEqual(len(images), 3)
        self.assertEqual({image['model'] for image in images}, {'product.image'})
        self.assertEqual([image['name'] for image in images][1:], ['CRM photo green', 'CRM photo blue'])
        tile = next(item for item in self._ids('stock', 'CRM-OEM-1')[0] if item['id'] == product.id)
        self.assertEqual(tile['image_count'], 3)
        with self.assertRaises(ValidationError):
            self.Available.get_product_images(False)
