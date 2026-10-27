import base64

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestWhatsappChatterAttachments(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lead = cls.env["crm.lead"].create(
            {
                "name": "WhatsApp attachment test",
                "type": "opportunity",
            }
        )
        cls.channel = cls.env["discuss.channel"].create(
            {
                "name": "WhatsApp attachment test",
                "channel_type": "channel",
            }
        )
        cls.channel_attachment = cls.env["ir.attachment"].create(
            {
                "name": "whatsapp.pdf",
                "raw": base64.b64encode(b"whatsapp attachment"),
                "mimetype": "application/pdf",
                "res_model": "discuss.channel",
                "res_id": cls.channel.id,
            }
        )

    def test_copy_to_record(self):
        copy = self.channel_attachment._copy_to_record(self.lead)

        self.assertEqual(copy.res_model, "crm.lead")
        self.assertEqual(copy.res_id, self.lead.id)
        self.assertEqual(copy.checksum, self.channel_attachment.checksum)
        self.assertEqual(copy.name, self.channel_attachment.name)
        self.assertEqual(self.channel_attachment.res_model, "discuss.channel")
        self.assertEqual(self.channel_attachment.res_id, self.channel.id)
        # A second call must reuse the existing copy.
        self.assertEqual(copy, self.channel_attachment._copy_to_record(self.lead))

    def test_message_post_copies_whatsapp_attachment(self):
        message = self.lead.message_post(
            body="Mensagem espelhada do WhatsApp",
            gateway_type="whatsapp",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            attachment_ids=[self.channel_attachment.id],
        )

        self.assertEqual(len(message.attachment_ids), 1)
        attachment = message.attachment_ids
        self.assertNotEqual(attachment, self.channel_attachment)
        self.assertEqual(attachment.res_model, "crm.lead")
        self.assertEqual(attachment.res_id, self.lead.id)

    def test_message_post_keeps_attachment_already_on_lead(self):
        lead_attachment = self.env["ir.attachment"].create(
            {
                "name": "lead.pdf",
                "raw": base64.b64encode(b"lead attachment"),
                "mimetype": "application/pdf",
                "res_model": "crm.lead",
                "res_id": self.lead.id,
            }
        )

        message = self.lead.message_post(
            body="Mensagem com anexo do lead",
            gateway_type="whatsapp",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            attachment_ids=[lead_attachment.id],
        )

        self.assertEqual(message.attachment_ids, lead_attachment)

    def test_message_post_without_gateway_keeps_attachment(self):
        message = self.lead.message_post(
            body="Mensagem normal do chatter",
            attachment_ids=[self.channel_attachment.id],
        )

        self.assertEqual(message.attachment_ids, self.channel_attachment)
