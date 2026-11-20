from odoo import models
from odoo.exceptions import UserError
from odoo.tools import pdf

# The documents of a sale printed on the same (A4) printer, in this order, with their report.
# The box labels go apart: they print on the label printer.
SALE_DOCUMENT_REPORTS = {
    'delivery': 'stock.action_report_delivery',
    'deca': 'l10n_es_deca_oca.action_report_deca',
    'packing': 'mercas_base.action_report_mercas_packing_list',
    'invoice': 'account.account_invoices',
}
SALE_DOCUMENTS_REPORT = 'mercas_touch.report_sale_documents'


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _mercas_sale_document_parts(self, report_ref, res_ids, data):
        """ For the report "Sale documents": [(report, ids)] of the documents of the sales
        chosen in `data['kinds']` (all the available ones by default), in the order of
        SALE_DOCUMENT_REPORTS. None for any other report.

        A single report, so that a direct printing to a printer (OCA base_report_to_printer)
        can send it to the A4 printer as any other. Each document is rendered by its own
        report, as when printed alone: the invoice keeps its PDF, for instance. """
        if self._get_report(report_ref).report_name != SALE_DOCUMENTS_REPORT:
            return None
        kinds = (data or {}).get('kinds') or list(SALE_DOCUMENT_REPORTS)
        Touch = self.env['mercas.touch']
        parts = []
        for order in self.env['sale.order'].browse(res_ids):
            documents = Touch._get_sale_print_documents(order)
            parts += [
                (report, documents[kind].ids)
                for kind, report in SALE_DOCUMENT_REPORTS.items()
                if kind in kinds and documents[kind]
            ]
        if not parts:
            raise UserError(self.env._("There is nothing to print."))
        return parts

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        parts = self._mercas_sale_document_parts(report_ref, res_ids, data)
        if parts is None:
            return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
        streams = []
        for report, ids in parts:
            content, report_type = self._render_qweb_pdf(report, ids)
            if report_type != 'pdf':
                # Tests without PDF rendering: the HTML of all of them
                return self._render_qweb_html(report_ref, res_ids, data=data)
            streams.append(content)
        return pdf.merge_pdf(streams), 'pdf'

    def _render_qweb_html(self, report_ref, docids, data=None):
        parts = self._mercas_sale_document_parts(report_ref, docids, data)
        if parts is None:
            return super()._render_qweb_html(report_ref, docids, data=data)
        return b''.join(self._render_qweb_html(report, ids)[0] for report, ids in parts), 'html'
