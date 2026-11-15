import io
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.binary import BinaryBytes


class ScrapGaiaReport(models.Model):
    """ The report for GAIA of a period, usually a month: the deliveries of the products of the
    vehicle recycling done in it and their weight of each material, as written in each delivery.
    Its lines are kept as they were when it was computed, and it can't be changed once it is
    presented. The periods of a company can't overlap. """
    _name = 'scrap.gaia.report'
    _inherit = ['mail.thread']
    _description = "GAIA Report"
    _order = 'date_from desc, id desc'

    name = fields.Char(compute='_compute_name', store=True, readonly=False, required=True, precompute=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    date_from = fields.Date("From", required=True, default=lambda self: self._default_dates()[0])
    date_to = fields.Date("To", required=True, default=lambda self: self._default_dates()[1])
    state = fields.Selection(
        [('draft', "Draft"), ('presented', "Presented")], default='draft', required=True, copy=False,
        tracking=True)
    presented_date = fields.Date("Presented on", copy=False, tracking=True)
    computed_date = fields.Datetime("Computed on", readonly=True, copy=False)
    picking_ids = fields.Many2many(
        'stock.picking', string="Deliveries", readonly=True, copy=False,
        help="The deliveries done in the period with products of the vehicle recycling.")
    picking_count = fields.Integer(compute='_compute_picking_count')
    line_ids = fields.One2many(
        'scrap.gaia.report.line', 'report_id', string="Weight by Delivery", readonly=True, copy=False)
    total_ids = fields.One2many(
        'scrap.gaia.report.total', 'report_id', string="Weight by Material", readonly=True, copy=False)
    weight_total = fields.Float("Total Weight", digits='Stock Weight', compute='_compute_weight_total')
    weight_uom_name = fields.Char(compute='_compute_weight_uom_name')
    note = fields.Text()
    xlsx_file = fields.Binary("Excel", attachment=True, readonly=True, copy=False)
    xlsx_filename = fields.Char(compute='_compute_xlsx_filename')

    def _default_dates(self):
        """ The month after the last report, or the last month. """
        last = self.search([('company_id', '=', self.env.company.id)], order='date_to desc', limit=1)
        if last:
            date_from = last.date_to + timedelta(days=1)
        else:
            date_from = fields.Date.context_today(self).replace(day=1) - relativedelta(months=1)
        return date_from, date_from + relativedelta(day=31)

    @api.depends('date_from', 'date_to')
    def _compute_name(self):
        for report in self:
            if not report.date_from or not report.date_to:
                report.name = report.name or False
            elif (report.date_from.day == 1 and report.date_to == report.date_from + relativedelta(day=31)):
                report.name = f"GAIA {report.date_from:%Y-%m}"
            else:
                report.name = f"GAIA {report.date_from} / {report.date_to}"

    @api.depends('name')
    def _compute_xlsx_filename(self):
        for report in self:
            report.xlsx_filename = f"{report.name or 'GAIA'}.xlsx"

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for report in self:
            report.picking_count = len(report.picking_ids)

    @api.depends('total_ids.weight')
    def _compute_weight_total(self):
        for report in self:
            report.weight_total = sum(report.total_ids.mapped('weight'))

    def _compute_weight_uom_name(self):
        self.weight_uom_name = self.env['product.template']._get_weight_uom_name_from_ir_config_parameter()

    @api.constrains('date_from', 'date_to', 'company_id')
    def _check_dates(self):
        for report in self:
            if report.date_from > report.date_to:
                raise ValidationError(self.env._("The period of %s ends before it starts.", report.name))
            overlapping = self.search([
                ('id', '!=', report.id),
                ('company_id', '=', report.company_id.id),
                ('date_from', '<=', report.date_to),
                ('date_to', '>=', report.date_from),
            ], limit=1)
            if overlapping:
                raise ValidationError(self.env._(
                    "The period of %(report)s overlaps the one of %(other)s (%(date_from)s - %(date_to)s).",
                    report=report.name, other=overlapping.name,
                    date_from=overlapping.date_from, date_to=overlapping.date_to))

    def write(self, vals):
        if self.filtered(lambda report: report.state == 'presented') and set(vals) - {'state', 'presented_date', 'note', 'xlsx_file', 'message_main_attachment_id'}:
            raise UserError(self.env._("A GAIA report presented can't be changed: set it back to draft first."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_presented(self):
        if self.filtered(lambda report: report.state == 'presented'):
            raise UserError(self.env._("A GAIA report presented can't be deleted."))

    def _get_pickings(self):
        """ The deliveries of the company done in the period, in the time zone of the user, with
        products of the vehicle recycling. """
        self.ensure_one()
        tz = self.env.tz
        start = datetime.combine(self.date_from, time.min, tz).astimezone(timezone.utc).replace(tzinfo=None)
        end = datetime.combine(self.date_to + timedelta(days=1), time.min, tz).astimezone(timezone.utc).replace(tzinfo=None)
        pickings = self.env['stock.picking'].search([
            ('company_id', '=', self.company_id.id),
            ('picking_type_code', '=', 'outgoing'),
            ('state', '=', 'done'),
            ('date_done', '>=', start),
            ('date_done', '<', end),
        ], order='date_done, id')
        return pickings.filtered(lambda picking: picking._scrap_gaia_moves())

    def action_compute(self):
        """ The deliveries of the period and their weight of each material, as written in each
        one now: kept in the report as they are. """
        for report in self:
            if report.state == 'presented':
                raise UserError(self.env._("A GAIA report presented can't be computed again."))
            pickings = report._get_pickings()
            totals = defaultdict(float)
            lines = []
            for picking in pickings:
                for line in picking.scrap_material_line_ids.filtered('weight'):
                    totals[line.scrap_material_id] += line.weight
                    lines.append(fields.Command.create({
                        'picking_id': picking.id,
                        'scrap_material_id': line.scrap_material_id.id,
                        'weight': line.weight,
                    }))
            report.write({
                'picking_ids': [fields.Command.set(pickings.ids)],
                'line_ids': [fields.Command.clear(), *lines],
                'total_ids': [fields.Command.clear(), *(
                    fields.Command.create({'scrap_material_id': material.id, 'weight': weight})
                    for material, weight in sorted(totals.items(), key=lambda item: (item[0].sequence, item[0].id)))],
                'computed_date': fields.Datetime.now(),
                'xlsx_file': False,
            })
        return True

    def action_present(self):
        for report in self:
            if not report.computed_date:
                raise UserError(self.env._("Compute %s before presenting it.", report.name))
        self.write({'state': 'presented', 'presented_date': fields.Date.context_today(self)})
        return True

    def action_draft(self):
        self.write({'state': 'draft', 'presented_date': False})
        return True

    def action_open_pickings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Deliveries"),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.picking_ids.ids)],
        }

    # The data of the PDF and the Excel

    def _get_materials(self):
        """ The materials of its lines, in their order. """
        return self.line_ids.scrap_material_id.sorted(lambda material: (material.sequence, material.id))

    def _get_picking_rows(self):
        """ [(delivery, {material: weight}, total)], by date. """
        self.ensure_one()
        weights = defaultdict(lambda: defaultdict(float))
        for line in self.line_ids:
            weights[line.picking_id][line.scrap_material_id] += line.weight
        return [(picking, weights[picking], sum(weights[picking].values()))
                for picking in self.picking_ids.sorted(lambda picking: (picking.date_done, picking.id))]

    def _get_move_rows(self):
        """ The moves of the products of the vehicle recycling of its deliveries. """
        self.ensure_one()
        return self.picking_ids.sorted(lambda picking: (picking.date_done, picking.id))._scrap_gaia_moves().filtered(
            lambda move: move.state == 'done')

    def action_download_xlsx(self):
        self.ensure_one()
        if not self.computed_date:
            raise UserError(self.env._("Compute %s before downloading it.", self.name))
        self.xlsx_file = BinaryBytes(self._build_xlsx(), self.xlsx_filename)
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self._name}/{self.id}/xlsx_file/{self.xlsx_filename}?download=true',
            'target': 'self',
        }

    def _build_xlsx(self):
        self.ensure_one()
        _ = self.env._
        import xlsxwriter  # noqa: PLC0415
        output = io.BytesIO()
        book = xlsxwriter.Workbook(output, {'in_memory': True})
        bold = book.add_format({'bold': True})
        title = book.add_format({'bold': True, 'font_size': 14})
        header = book.add_format({'bold': True, 'bg_color': '#D9D9D9', 'border': 1})
        number = book.add_format({'num_format': '#,##0.00'})
        total = book.add_format({'bold': True, 'num_format': '#,##0.00', 'top': 1})
        date = book.add_format({'num_format': 'dd/mm/yyyy'})
        uom = self.weight_uom_name
        materials = self._get_materials()
        state = dict(self._fields['state']._description_selection(self.env))[self.state]

        sheet = book.add_worksheet(_("Summary"))
        sheet.set_column(0, 0, 28)
        sheet.set_column(1, 1, 16)
        sheet.write(0, 0, self.name, title)
        info = [
            (_("Company"), self.company_id.name),
            (_("From"), self.date_from),
            (_("To"), self.date_to),
            (_("State"), state),
            (_("Presented on"), self.presented_date or ''),
            (_("Deliveries"), self.picking_count),
        ]
        row = 2
        for label, value in info:
            sheet.write(row, 0, label, bold)
            if hasattr(value, 'year'):
                sheet.write_datetime(row, 1, datetime.combine(value, time.min), date)
            else:
                sheet.write(row, 1, value)
            row += 1
        row += 1
        sheet.write(row, 0, _("Material"), header)
        sheet.write(row, 1, f"{_('Weight')} ({uom})", header)
        for line in self.total_ids:
            row += 1
            sheet.write(row, 0, line.scrap_material_id.name)
            sheet.write_number(row, 1, line.weight, number)
        row += 1
        sheet.write(row, 0, _("Total"), bold)
        sheet.write_number(row, 1, self.weight_total, total)

        sheet = book.add_worksheet(_("Deliveries"))
        columns = [_("Date"), _("Delivery"), _("Customer"), _("Origin"),
                   *(f"{material.name} ({uom})" for material in materials), f"{_('Total')} ({uom})"]
        for col, label in enumerate(columns):
            sheet.write(0, col, label, header)
        sheet.set_column(0, 0, 12)
        sheet.set_column(1, 3, 22)
        sheet.set_column(4, len(columns) - 1, 14)
        row = 0
        for picking, weights, picking_total in self._get_picking_rows():
            row += 1
            sheet.write_datetime(row, 0, fields.Datetime.context_timestamp(self, picking.date_done).replace(tzinfo=None), date)
            sheet.write(row, 1, picking.name)
            sheet.write(row, 2, picking.partner_id.display_name or '')
            sheet.write(row, 3, picking.origin or '')
            for col, material in enumerate(materials, start=4):
                sheet.write_number(row, col, weights.get(material, 0.0), number)
            sheet.write_number(row, 4 + len(materials), picking_total, number)
        row += 1
        sheet.write(row, 3, _("Total"), bold)
        totals = {line.scrap_material_id: line.weight for line in self.total_ids}
        for col, material in enumerate(materials, start=4):
            sheet.write_number(row, col, totals.get(material, 0.0), total)
        sheet.write_number(row, 4 + len(materials), self.weight_total, total)

        sheet = book.add_worksheet(_("Moves"))
        columns = [_("Date"), _("Delivery"), _("Customer"), _("Product"), _("Quantity"), _("Unit"),
                   f"{_('Weight')} ({uom})"]
        for col, label in enumerate(columns):
            sheet.write(0, col, label, header)
        sheet.set_column(0, 0, 12)
        sheet.set_column(1, 3, 26)
        sheet.set_column(4, 6, 12)
        row = 0
        for move in self._get_move_rows():
            row += 1
            sheet.write_datetime(row, 0, fields.Datetime.context_timestamp(self, move.date).replace(tzinfo=None), date)
            sheet.write(row, 1, move.picking_id.name)
            sheet.write(row, 2, move.picking_id.partner_id.display_name or '')
            sheet.write(row, 3, move.product_id.display_name)
            sheet.write_number(row, 4, move.quantity, number)
            sheet.write(row, 5, move.uom_id.name)
            sheet.write_number(row, 6, move.product_id.weight * move.product_qty, number)
        book.close()
        return output.getvalue()



class ScrapGaiaReportLine(models.Model):
    _name = 'scrap.gaia.report.line'
    _description = "GAIA Report Line"
    _order = 'id'

    report_id = fields.Many2one('scrap.gaia.report', required=True, index=True, ondelete='cascade')
    picking_id = fields.Many2one('stock.picking', string="Delivery", required=True, ondelete='restrict')
    date_done = fields.Datetime(related='picking_id.date_done', string="Date")
    partner_id = fields.Many2one(related='picking_id.partner_id', string="Customer")
    scrap_material_id = fields.Many2one('scrap.material', string="Material", required=True, ondelete='restrict')
    weight = fields.Float("Weight", digits='Stock Weight')


class ScrapGaiaReportTotal(models.Model):
    _name = 'scrap.gaia.report.total'
    _description = "GAIA Report Total"
    _order = 'sequence, id'

    report_id = fields.Many2one('scrap.gaia.report', required=True, index=True, ondelete='cascade')
    scrap_material_id = fields.Many2one('scrap.material', string="Material", required=True, ondelete='restrict')
    sequence = fields.Integer(related='scrap_material_id.sequence')
    weight = fields.Float("Weight", digits='Stock Weight')
