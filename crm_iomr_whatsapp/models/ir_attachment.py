from odoo import models


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def _copy_to_record(self, record):
        """Return attachments linked to ``record``, copying them if needed.

        Attachments created in a WhatsApp/Discuss channel stay linked to the
        ``discuss.channel``.  When the related message is mirrored to a business
        record, the attachment is only linked to the message, so its access
        rules remain those of the channel.  This helper creates a copy linked to
        the business record, making the file available to every user that can
        read that record.  The original attachment is left untouched in the
        channel conversation.
        """
        record.ensure_one()
        copies = self.browse()
        for attachment in self:
            attachment = attachment.sudo()
            if attachment.res_model == record._name and attachment.res_id == record.id:
                copies |= attachment
                continue

            # Avoid creating a new copy when the same file was already copied
            # to the record (e.g. a historical sync running more than once).
            domain = [
                ("res_model", "=", record._name),
                ("res_id", "=", record.id),
                ("name", "=", attachment.name),
                ("type", "=", attachment.type),
            ]
            if attachment.type == "url":
                domain.append(("url", "=", attachment.url))
            else:
                domain.append(("checksum", "=", attachment.checksum))
            existing = self.env["ir.attachment"].sudo().search(domain, limit=1)
            if existing:
                copies |= existing
                continue

            vals = {
                "name": attachment.name,
                "description": attachment.description,
                "res_model": record._name,
                "res_id": record.id,
                "type": attachment.type,
                "mimetype": attachment.mimetype,
                # Keep the copy private to the record's users instead of
                # exposing it through a public URL.
                "public": False,
            }
            company = getattr(record, "company_id", False)
            if company:
                vals["company_id"] = company.id
            if attachment.type == "url":
                vals["url"] = attachment.url
            else:
                vals["raw"] = attachment.raw
            copies |= self.env["ir.attachment"].sudo().create(vals)
        return copies
