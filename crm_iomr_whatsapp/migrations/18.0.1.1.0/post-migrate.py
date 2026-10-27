"""Copy WhatsApp channel attachments to their CRM leads.

Messages mirrored from WhatsApp keep their attachments linked to the
``discuss.channel``.  The chatter message references them, but only channel
members can open the files.  For messages mirrored before this version, create
a copy linked to the lead and replace the link on the message.
"""

import logging

from odoo import SUPERUSER_ID, Command, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    messages = (
        env["mail.message"]
        .sudo()
        .search(
            [
                ("model", "=", "crm.lead"),
                ("gateway_type", "=", "whatsapp"),
                ("attachment_ids", "!=", False),
            ]
        )
    )
    migrated = 0
    for message in messages:
        lead = env["crm.lead"].sudo().browse(message.res_id)
        if not lead.exists():
            continue

        channel_attachments = message.attachment_ids.filtered(
            lambda attachment: attachment.res_model == "discuss.channel"
        )
        if not channel_attachments:
            continue

        commands = []
        for attachment in channel_attachments:
            copy = attachment._copy_to_record(lead)
            if copy and copy != attachment:
                commands += [
                    Command.unlink(attachment.id),
                    Command.link(copy.id),
                ]
        if commands:
            message.write({"attachment_ids": commands})
            migrated += 1

    _logger.info(
        "crm_iomr_whatsapp: copied WhatsApp attachments to the lead on %s message(s).",
        migrated,
    )
