def migrate(cr, version):
    """ The purchases made on the screen before the kinds of entry were scrap entries. """
    cr.execute("""
        UPDATE purchase_order
           SET unbuild_type = 'main'
         WHERE scrap_touch_uuid IS NOT NULL
           AND unbuild_type IS NULL
    """)
