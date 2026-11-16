# Copyright 2024 Dixmit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class MailMessage(models.Model):
    _inherit = "mail.message"

    @api.depends("gateway_notification_ids")
    def _compute_gateway_channel_id(self):
        for rec in self:
            if rec.gateway_notification_ids:
                notification = rec.gateway_notification_ids[0]
                # Resolve gateway_channel_id correctly:
                # - If model is discuss.channel, look up the partner via the channel's gateway_token
                # - If model is res.partner, use the partner's direct gateway_channel_id
                if rec.model == "discuss.channel" and notification.gateway_channel_id:
                    # Look up the discuss channel and get its partner via gateway_token
                    channel = self.env["discuss.channel"].browse(notification.gateway_channel_id)
                    if channel.gateway_channel_token:
                        # Find the res_partner_gateway.channel via token matching
                        gc = self.env["res.partner.gateway.channel"].sudo().search(
                            [("gateway_token", "=", channel.gateway_channel_token)],
                            limit=1,
                        )
                        if gc:
                            rec.gateway_channel_id = gc.id
                        else:
                            rec.gateway_channel_id = notification.gateway_channel_id
                    else:
                        rec.gateway_channel_id = notification.gateway_channel_id
                else:
                    # For res.partner model or no special handling, use as-is
                    rec.gateway_channel_id = notification.gateway_channel_id