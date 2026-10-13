from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from .res_partner import check_offline_uuid, is_record_id

# Most lines of an order made on the tablet
MAX_LINES = 200


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    offline_uuid = fields.Char(
        'Offline Identifier', copy=False, readonly=True,
        help="Identifier given by the tablet that made the order offline.")
    offline_revision = fields.Integer(
        'Offline Revision', copy=False, readonly=True,
        help="Last version of the order received from the tablet.")

    # The unique index also serves the searches by uuid
    _offline_uuid_unique = models.Constraint(
        'UNIQUE (offline_uuid)',
        "This order was already received from the tablet.",
    )

    @api.model
    def save_from_tablet(self, vals):
        """ Create or update the order made on the tablet, and confirm it if asked.

        The tablet numbers each version of an order. A version is applied once: the tablet may
        send it again if the connection is lost after the commit, and an older version may arrive
        after a newer one; both are ignored. Prices, taxes and totals are computed again here; the
        ones shown on the tablet are an estimate.

        While the order is a quotation, the tablet owns its product lines: a new version updates
        the lines it knows (`line_id`), adds the new ones and removes the missing ones. Sections
        and notes are kept. Once confirmed, the lines can't be changed from the tablet anymore.

        A quotation made in the backend gets the uuid of the tablet the first time it is changed
        there (`order_id`).

        :param dict vals: {
            'offline_uuid': str, 'revision': int, 'partner_id': int, 'confirm': bool,
            'order_id': int (optional),
            'lines': [{'product_id': int, 'qty': float, 'discount': float, 'line_id': int (optional)}],
        }
        :return: {'id': int, 'name': str, 'state': str}
        """
        if not isinstance(vals, dict):
            raise ValidationError(self.env._("Invalid order."))
        offline_uuid = check_offline_uuid(self.env, vals.get('offline_uuid'))
        revision = vals.get('revision', 1)
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise ValidationError(self.env._("Invalid order version."))
        confirm = vals.get('confirm', False)
        if not isinstance(confirm, bool):
            raise ValidationError(self.env._("Invalid order."))
        # Look among every order, so that a duplicate isn't hidden by the access rules
        existing = self.sudo().search([('offline_uuid', '=', offline_uuid)], limit=1)
        order = self.browse(existing.id)
        if existing.create_uid != self.env.user and not order.has_access('write'):
            raise AccessError(self.env._("This order was made by another user."))
        if order and revision <= order.offline_revision:
            return order._get_tablet_result()

        customer = self.env['res.partner']._get_route_customer(vals.get('partner_id'))
        if not order and vals.get('order_id') is not None:
            order = self._get_tablet_backend_order(vals['order_id'], offline_uuid)
        lines = self._prepare_tablet_lines(vals.get('lines'), order)
        if not order:
            order = self.create({
                'partner_id': customer.id,
                'user_id': self.env.uid,
                'offline_uuid': offline_uuid,
                'offline_revision': revision,
                'order_line': [Command.create({k: v for k, v in line.items() if k != 'line_id'}) for line in lines],
            })
        elif order.partner_id.commercial_partner_id != customer:
            raise ValidationError(self.env._("The customer of an order can't be changed."))
        elif order.state in ('draft', 'sent'):
            order.write({
                'offline_uuid': offline_uuid,
                'offline_revision': revision,
                'order_line': order._get_tablet_line_commands(lines),
            })
        elif order.state == 'sale' and confirm:
            # Confirmed meanwhile, e.g. from the backend: nothing left to do
            order.offline_revision = revision
        else:
            raise ValidationError(self.env._(
                "The order %s is not a quotation anymore: it can't be changed from the tablet.", order.name))
        if confirm and order.state in ('draft', 'sent'):
            order.action_confirm()
        return order._get_tablet_result()

    @api.model
    def _get_tablet_backend_order(self, order_id, offline_uuid):
        """ The quotation made in the backend that the tablet changes for the first time. """
        if not is_record_id(order_id):
            raise ValidationError(self.env._("Invalid order."))
        order = self.browse(order_id).exists()
        if not order:
            raise ValidationError(self.env._("The order doesn't exist anymore."))
        order.check_access('write')
        if order.offline_uuid and order.offline_uuid != offline_uuid:
            raise ValidationError(self.env._(
                "The order %s was changed from another tablet: prepare the route again.", order.name))
        return order

    def _get_tablet_line_commands(self, lines):
        """ Commands to make the product lines of the order match the ones of the tablet. """
        self.ensure_one()
        product_lines = self.order_line.filtered(lambda line: not line.display_type)
        kept = self.env['sale.order.line']
        commands = []
        for line in lines:
            line = dict(line)
            current = product_lines.filtered(lambda l: l.id == line.get('line_id')) - kept
            line.pop('line_id', None)
            if current and current.product_id.id == line['product_id']:
                kept |= current
                line.pop('product_id')
                commands.append(Command.update(current.id, line))
            else:
                # Also a line removed in the backend meanwhile: it comes back
                commands.append(Command.create(line))
        commands += [Command.unlink(line.id) for line in product_lines - kept]
        return commands
    @api.model
    def create_from_tablet(self, vals):
        """ Calls queued by the first version of the tablet screen, which only made quotations. """
        return self.save_from_tablet(dict(vals, revision=1, confirm=False))

    def _get_tablet_result(self):
        self.ensure_one()
        return {'id': self.id, 'name': self.name, 'state': self.state}

    @api.model
    def _prepare_tablet_lines(self, lines, order=None):
        """ Check the lines sent by the tablet. The products already in `order` are accepted even
        if they can't be sold anymore. """
        if not isinstance(lines, list) or not lines or len(lines) > MAX_LINES:
            raise ValidationError(self.env._("The order must have between 1 and %s lines.", MAX_LINES))
        has_discount = self.env.user.has_group('sale.group_discount_per_so_line')
        product_ids = set()
        line_vals = []
        for line in lines:
            if not isinstance(line, dict):
                raise ValidationError(self.env._("Invalid order line."))
            product_id, qty, discount = line.get('product_id'), line.get('qty'), line.get('discount') or 0.0
            line_id = line.get('line_id')
            if not is_record_id(product_id) or (line_id is not None and not is_record_id(line_id)):
                raise ValidationError(self.env._("Invalid product."))
            if not isinstance(qty, (int, float)) or isinstance(qty, bool) or qty <= 0:
                raise ValidationError(self.env._("The quantity must be positive."))
            if not isinstance(discount, (int, float)) or isinstance(discount, bool) or not 0 <= discount <= 100:
                raise ValidationError(self.env._("The discount must be between 0 and 100."))
            product_ids.add(product_id)
            vals = {'product_id': product_id, 'product_uom_qty': qty}
            # Without the discount feature, the discount of the pricelist is computed as usual
            if has_discount:
                vals['discount'] = discount
            if line_id:
                vals['line_id'] = line_id
            line_vals.append(vals)
        products = self.env['product.product'].browse(product_ids).exists()
        current_products = order.order_line.product_id if order else self.env['product.product']
        if len(products) != len(product_ids) or not all((products - current_products).mapped('sale_ok')):
            raise ValidationError(self.env._("Some products can't be sold."))
        products.check_access('read')
        return line_vals
