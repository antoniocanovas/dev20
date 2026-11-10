def migrate(cr, version):
    """ The license plates of the lines are now kept by scrap_base (`scrap_lot_name`), updated
    before this module. """
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'purchase_order_line' AND column_name = 'scrap_touch_lot_name'
    """)
    if not cr.fetchone():
        return
    cr.execute("""
        UPDATE purchase_order_line
           SET scrap_lot_name = scrap_touch_lot_name
         WHERE scrap_touch_lot_name IS NOT NULL
           AND scrap_lot_name IS NULL
    """)
