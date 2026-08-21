from odoo import api, fields, models


class MailGateway(models.Model):
    _inherit = "mail.gateway"

    sdr_user_id = fields.Many2one(
        "res.users",
        string="SDR Responsável",
        help="Usuário SDR responsável pelo gerenciamento das conversas do WhatsApp",
    )


class CrmLead(models.Model):
    _inherit = "crm.lead"

    def write(self, vals):
        old_user_ids = {}
        if "user_id" in vals:
            old_user_ids = {lead.id: lead.user_id.id for lead in self}
        result = super().write(vals)
        if "user_id" in vals:
            for lead in self:
                old_id = old_user_ids.get(lead.id)
                new_id = vals["user_id"]
                if old_id and old_id != new_id:
                    lead._add_user_to_whatsapp_channel()
        return result

    def _add_user_to_whatsapp_channel(self):
        if not self.user_id:
            return
        if not self.env.registry.get("mail.whatsapp.chatter.link"):
            return
        link = self.env["mail.whatsapp.chatter.link"].sudo().search(
            [("res_model", "=", "crm.lead"), ("res_id", "=", self.id)], limit=1
        )
        if not link or not link.channel_id:
            return
        channel = link.channel_id.sudo()
        new_partner = self.user_id.partner_id
        if not any(
            member.partner_id == new_partner
            for member in channel.channel_member_ids
        ):
            self.env["discuss.channel.member"].sudo().create(
                {
                    "partner_id": new_partner.id,
                    "channel_id": channel.id,
                    "is_pinned": False,
                    "unpin_dt": False,
                }
            )
