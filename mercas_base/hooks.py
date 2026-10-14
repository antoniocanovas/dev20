def post_init_hook(env):
    """Activates, the same way a user would by checking the boxes in
    Inventory > Configuration > Settings and saving, the options:
    - Warehouse: Storage Locations
    - Traceability: Lots & Serial Numbers
    - Products: Variants
    - Products: Units of Measure & Packagings
    - Signature (asks for a signature on delivery orders)

    Done by instantiating and executing `res.config.settings` (instead of
    touching `implied_ids` directly) because several of these settings
    trigger additional logic in their `set_values()` (e.g. `stock`
    activates/deactivates warehouse operation types when
    `group_stock_multi_locations` is touched, and the
    `group_stock_production_lot` group is also applied to
    `base.group_portal`, not only `base.group_user`).
    """
    env["res.config.settings"].create(
        {
            "group_stock_multi_locations": True,
            "group_stock_production_lot": True,
            "group_product_variant": True,
            "group_uom": True,
            "group_stock_sign_delivery": True,
        }
    ).execute()
