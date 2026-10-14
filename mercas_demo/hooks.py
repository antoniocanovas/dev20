PRODUCE_TEMPLATE_XMLIDS = [
    "mercas_demo.product_template_manzana",
    "mercas_demo.product_template_pera",
    "mercas_demo.product_template_platano",
    "mercas_demo.product_template_tomate",
    "mercas_demo.product_template_lechuga",
]
BOX_PRODUCT_XMLIDS = [
    "mercas_demo.product_caja1",
    "mercas_demo.product_caja2",
]

# xmlid: (cost, sale price)
PRODUCE_PRICES = {
    "mercas_demo.product_template_manzana": (0.80, 1.30),
    "mercas_demo.product_template_pera": (0.90, 1.45),
    "mercas_demo.product_template_platano": (0.70, 1.15),
    "mercas_demo.product_template_tomate": (0.60, 1.05),
    "mercas_demo.product_template_lechuga": (0.45, 0.85),
}
BOX_PRICES = {
    "mercas_demo.product_caja1": (0.35, 0.60),
    "mercas_demo.product_caja2": (0.50, 0.85),
}


def post_init_hook(env):
    """Idempotent setup, called on fresh install (post_init_hook) and re-run on
    upgrade via migrations/<version>/post-mercas_demo.py so it also applies to
    databases where mercas_demo was already installed before this logic existed.
    """
    _activate_lot_tracking(env)
    _configure_company(env)
    _assign_compensation_journal(env)
    _assign_taxes(env)
    _assign_prices(env)


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
