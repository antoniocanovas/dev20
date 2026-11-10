import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    @api.model
    def _im_riocabo_should_notify(self):
        """ Solo avisa quien es usuario interno y si no se ha desactivado por contexto. """
        return not self.env.context.get('im_riocabo_no_notify') and self.env.user._is_internal()

    @api.model
    def _im_riocabo_notify(self, user, body):
        """ Publica ``body`` en el chat directo entre el usuario actual y ``user``.

        Nunca lanza excepción: un fallo en el aviso no debe impedir crear el registro.
        """
        if not user or user == self.env.user or not user.active or user.share:
            return
        try:
            with self.env.cr.savepoint():
                channel = self._get_or_create_chat([user.partner_id.id])
                channel.message_post(
                    body=body,
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                )
        except Exception:
            _logger.warning("im_riocabo: no se pudo avisar por chat a %s", user.login, exc_info=True)
