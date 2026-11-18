def migrate(cr, version):
    """Firm negotiation is now a commercial field: the contacts and addresses
    of a company take the value of the company."""
    cr.execute(
        """
        UPDATE res_partner child
           SET mercas_firm_negotiation = parent.mercas_firm_negotiation
          FROM res_partner parent
         WHERE child.commercial_partner_id = parent.id
           AND child.id != parent.id
           AND child.mercas_firm_negotiation IS DISTINCT FROM parent.mercas_firm_negotiation
        """
    )
