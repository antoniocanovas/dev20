PRODUCE_TEMPLATE_XMLIDS = [
    "mercas_demo.product_template_manzana",
    "mercas_demo.product_template_manzana_granel",
    "mercas_demo.product_template_pera",
    "mercas_demo.product_template_platano",
    "mercas_demo.product_template_tomate",
    "mercas_demo.product_template_lechuga",
]
BOX_PRODUCT_XMLIDS = [
    "mercas_demo.product_caja1",
    "mercas_demo.product_caja2",
    "mercas_demo.product_europalet",
]

# xmlid: (cost, sale price)
PRODUCE_PRICES = {
    "mercas_demo.product_template_manzana": (0.80, 1.30),
    "mercas_demo.product_template_manzana_granel": (0.80, 1.30),
    "mercas_demo.product_template_pera": (0.90, 1.45),
    "mercas_demo.product_template_platano": (0.70, 1.15),
    "mercas_demo.product_template_tomate": (0.60, 1.05),
    "mercas_demo.product_template_lechuga": (0.45, 0.85),
}
BOX_PRICES = {
    "mercas_demo.product_caja1": (0.35, 0.60),
    "mercas_demo.product_caja2": (0.50, 0.85),
    "mercas_demo.product_europalet": (8.00, 12.00),
}

# Quotation with its boxes on pallets, to try the packing list
PALLET_SALE_REF = "Demo palets"


def post_init_hook(env):
    """Setup on install: lot tracking, company defaults, taxes, prices and the
    quotation of the pallets."""
    _activate_lot_tracking(env)
    _configure_company(env)
    _assign_compensation_journal(env)
    _assign_taxes(env)
    _assign_prices(env)
    _create_pallet_sale(env)


def _activate_lot_tracking(env):
    group_user = env.ref("base.group_user")
    lot_group = env.ref("stock.group_production_lot")
    if lot_group not in group_user.implied_ids:
        group_user.write({"implied_ids": [(4, lot_group.id)]})


def _configure_company(env):
    for company in env["res.company"].search([]):
        if not company.mercas_margin:
            company.write({"mercas_margin": 10.0})


def _assign_compensation_journal(env):
    for company in env["res.company"].search([]):
        if company.compensation_journal_id:
            continue
        journal = env["account.journal"].search(
            [
                ("company_id", "=", company.id),
                ("type", "=", "general"),
                ("code", "=", "MISC"),
            ],
            limit=1,
        )
        if not journal:
            journal = env["account.journal"].search(
                [("company_id", "=", company.id), ("type", "=", "general")],
                limit=1,
            )
        if journal:
            company.compensation_journal_id = journal.id


def _assign_taxes(env):
    """Sustituye los impuestos por defecto (21% Bienes) de los productos de demo:
    4% Bienes en fruta/verdura, 0% Bienes en los envases.

    Se hace por hook (no por domain estático en el XML) porque los xmlid de los
    impuestos del PGC español se generan por compañía (`{company_id}_{xmlid}`) y
    no son estables entre bases de datos; si la compañía no usa el plan contable
    español (l10n_es) simplemente no se encuentran y no se toca nada.
    """
    produce_templates = env["product.template"].browse(
        [
            env.ref(xmlid).id
            for xmlid in PRODUCE_TEMPLATE_XMLIDS
            if env.ref(xmlid, raise_if_not_found=False)
        ]
    )
    box_templates = env["product.template"].browse(
        [
            env.ref(xmlid).product_tmpl_id.id
            for xmlid in BOX_PRODUCT_XMLIDS
            if env.ref(xmlid, raise_if_not_found=False)
        ]
    )

    for company in env["res.company"].search([]):
        chart = env["account.chart.template"].with_company(company)

        sale_4 = chart.ref("account_tax_template_s_iva4b", raise_if_not_found=False)
        purchase_4 = chart.ref("account_tax_template_p_iva4_bc", raise_if_not_found=False)
        if produce_templates and (sale_4 or purchase_4):
            vals = {}
            if sale_4:
                vals["taxes_id"] = [(6, 0, [sale_4.id])]
            if purchase_4:
                vals["supplier_taxes_id"] = [(6, 0, [purchase_4.id])]
            produce_templates.write(vals)

        sale_0 = chart.ref("account_tax_template_s_iva0b", raise_if_not_found=False)
        purchase_0 = chart.ref("account_tax_template_p_iva0_s_bc", raise_if_not_found=False)
        if box_templates and (sale_0 or purchase_0):
            vals = {}
            if sale_0:
                vals["taxes_id"] = [(6, 0, [sale_0.id])]
            if purchase_0:
                vals["supplier_taxes_id"] = [(6, 0, [purchase_0.id])]
            box_templates.write(vals)


def _assign_prices(env):
    # standard_price is only settable at template level for single-variant
    # products (see ProductTemplate._set_product_variant_field): Manzana and
    # Tomate have several variants (attribute lines), so the cost has to be
    # written on each product.product variant instead.
    for xmlid, (cost, price) in {**PRODUCE_PRICES, **BOX_PRICES}.items():
        template = env.ref(xmlid, raise_if_not_found=False)
        if not template:
            continue
        if xmlid in BOX_PRICES:
            template = template.product_tmpl_id
        template.write({"list_price": price})
        template.product_variant_ids.write({"standard_price": cost})


def _create_pallet_sale(env):
    """A quotation of Cliente1 with its boxes on two pallets: a europallet
    (returnable) with tomatoes and pears, and a single-use pallet with the
    rest of the tomatoes and the bananas. Its goods are bought first from
    Proveedor1 and received with their lots (see _receive_pallet_stock), so
    "Sold & Sent" works right away. Created once; deleting it doesn't bring
    it back unless the module is installed again."""
    customer = env.ref("mercas_demo.res_partner_cliente1", raise_if_not_found=False)
    euro = env.ref("mercas_demo.package_type_palet_europeo", raise_if_not_found=False)
    single = env.ref("mercas_demo.package_type_palet_desechable", raise_if_not_found=False)
    if not (customer and euro and single):
        return
    SaleOrder = env["sale.order"]
    if SaleOrder.search_count([("client_order_ref", "=", PALLET_SALE_REF)], limit=1):
        return

    def variant(xmlid):
        return env.ref(xmlid).product_variant_ids[:1]

    tomato = variant("mercas_demo.product_template_tomate")
    pear = variant("mercas_demo.product_template_pera")
    banana = variant("mercas_demo.product_template_platano")
    caja1 = env.ref("mercas_demo.product_caja1")
    caja2 = env.ref("mercas_demo.product_caja2")
    lots = _receive_pallet_stock(env, [
        (tomato, 200.0, 20, caja2, "DEMO-TOMATE"),
        (pear, 100.0, 10, caja1, "DEMO-PERA"),
        (banana, 100.0, 10, caja2, "DEMO-PLATANO"),
    ])
    order = SaleOrder.create({
        "partner_id": customer.id,
        "client_order_ref": PALLET_SALE_REF,
        "order_line": [
            (0, 0, {"product_id": tomato.id, "product_uom_qty": 150.0, "box_qty": 15, "box_product_id": caja2.id,
                    "lot_id": lots.get(tomato, env["stock.lot"]).id}),
            (0, 0, {"product_id": pear.id, "product_uom_qty": 80.0, "box_qty": 8, "box_product_id": caja1.id,
                    "lot_id": lots.get(pear, env["stock.lot"]).id}),
            (0, 0, {"product_id": banana.id, "product_uom_qty": 60.0, "box_qty": 6, "box_product_id": caja2.id,
                    "lot_id": lots.get(banana, env["stock.lot"]).id}),
        ],
    })
    tomato_line, pear_line, banana_line = order.order_line
    order._mercas_set_pallets([
        {
            "package_type_id": euro.id,
            "lines": [
                {"sale_line_id": tomato_line.id, "box_qty": 10},
                {"sale_line_id": pear_line.id, "box_qty": 8},
            ],
        },
        {
            "package_type_id": single.id,
            "height": 1100.0,
            "lines": [
                {"sale_line_id": tomato_line.id, "box_qty": 5},
                {"sale_line_id": banana_line.id, "box_qty": 6},
            ],
        },
    ])


def _receive_pallet_stock(env, lines):
    """Buy and receive from Proveedor1, with "Purchase & Receive", the goods of
    the pallet quotation, each in a lot of its own (with its boxes).

    :param list lines: [(product, kg, boxes, box product, lot name)]
    :return: {product: its lot}; empty if Proveedor1 is missing
    """
    supplier = env.ref("mercas_demo.res_partner_proveedor1", raise_if_not_found=False)
    if not supplier:
        return {}
    Lot = env["stock.lot"]
    lots = {}
    order_lines = []
    for product, qty, boxes, box, lot_name in lines:
        lot = Lot.search([("name", "=", lot_name), ("product_id", "=", product.id)], limit=1) or Lot.create({
            "name": lot_name,
            "product_id": product.id,
        })
        lots[product] = lot
        order_lines.append((0, 0, {
            "product_id": product.id,
            "product_qty": qty,
            "price_unit": product.standard_price,
            "lot_id": lot.id,
            "box_qty": boxes,
            "box_product_id": box.id,
        }))
    europallet = env.ref("mercas_demo.product_europalet", raise_if_not_found=False)
    if europallet:
        order_lines.append((0, 0, {"product_id": europallet.id, "product_qty": 5.0, "price_unit": europallet.standard_price}))
    purchase = env["purchase.order"].create({"partner_id": supplier.id, "order_line": order_lines})
    purchase.button_purchase_and_receive()
    return lots
