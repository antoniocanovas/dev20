import base64
import io
import uuid

from PIL import Image

from odoo import Command
from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestScrapCrmAvailableUi(HttpCase):

    def test_available_tour(self):
        brand = self.env['fleet.vehicle.model.brand'].create({'name': 'Tour Brand'})
        model = self.env['fleet.vehicle.model'].create({'name': 'Tour Model', 'brand_id': brand.id})
        engine = self.env['product.product'].create({
            'name': 'Tour Engine', 'type': 'consu', 'is_storable': True,
            'is_template': True, 'scrap_unbuild_type': 'subproduct',
        })
        car = self.env['product.product'].create({
            'name': 'Tour Car', 'type': 'consu', 'is_storable': True, 'tracking': 'serial',
            'is_template': True, 'vehicle_model_id': model.id,
        })
        self.env['mrp.bom'].create({
            'product_tmpl_id': car.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': engine.id, 'product_qty': 1})],
        })
        supplier = self.env['res.partner'].create({'name': 'Tour Supplier'})
        result = self.env['scrap.touch'].purchase_entry({
            'uuid': str(uuid.uuid4()), 'partner_id': supplier.id, 'unbuild_type': 'main',
            'lines': [{'product_id': car.id, 'lot_name': plate, 'price_unit': 100.0} for plate in ('TOURAV1', 'TOURAV2')],
        })
        # The engine of the second car, dismantled: a product of its own, in stock
        dismantled = self.env['purchase.order'].browse(result['id']).order_line.product_id.product_tmpl_id.filtered(
            lambda vehicle: vehicle.scrap_lot_name == 'TOURAV2')
        dismantled.decontamination_date = dismantled.discharge_date
        dismantled._scrap_dismantle(dismantled.bom_ids.bom_line_ids, 1, 'dismantled', 'good')
        # The engine, with two photos
        photos = []
        for color in ('red', 'blue'):
            output = io.BytesIO()
            Image.new('RGB', (64, 64), color).save(output, format='PNG')
            photos.append(base64.b64encode(output.getvalue()).decode())
        engine_copy = self.env['product.template'].search([('scrap_origin_id', '=', dismantled.id)])
        engine_copy.image_1920 = photos[0]
        self.env['product.image'].create({'name': 'Tour photo', 'product_tmpl_id': engine_copy.id, 'image_1920': photos[1]})
        user = new_test_user(self.env, login='crm_available_tour', groups='sales_team.group_sale_salesman,stock.group_stock_user')
        lead = self.env['crm.lead'].create({
            'user_id': user.id, 'name': 'Tour engine asked', 'type': 'opportunity',
            'brand_id': brand.id, 'scrap_template_id': engine.product_tmpl_id.id,
        })
        self.start_tour(f'/odoo/crm/{lead.id}', 'scrap_crm_available_tour', login='crm_available_tour')
