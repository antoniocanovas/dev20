from markupsafe import Markup

from odoo import api, models
from odoo.tools.misc import format_date


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    @api.model_create_multi
    def create(self, vals_list):
        activities = super().create(vals_list)
        Channel = self.env['discuss.channel']
        if Channel._im_riocabo_should_notify():
            for activity in activities.filtered(lambda a: a.user_id and a.user_id != self.env.user):
                user = activity.user_id
                Channel._im_riocabo_notify(user, activity.with_context(lang=user.lang)._im_riocabo_chat_body())
        return activities

    def _im_riocabo_chat_body(self):
        self.ensure_one()
        _ = self.env._
        if self.res_model and self.res_id:
            record = self.env[self.res_model].browse(self.res_id)
            model_name = self.env['ir.model']._get(self.res_model).display_name
            document = Markup("%s %s") % (model_name, record._get_html_link_with_href(self.res_name))
        else:
            document = self.res_name or ''
        lines = [_("New activity assigned to you on %s", document)]
        lines.append(_("Type: %s", self.activity_type_id.display_name or _("To-Do")))
        if self.summary:
            lines.append(_("Summary: %s", self.summary))
        if self.date_deadline:
            lines.append(_("Due date: %s", format_date(self.env, self.date_deadline)))
        return Markup("<br/>").join(lines)
