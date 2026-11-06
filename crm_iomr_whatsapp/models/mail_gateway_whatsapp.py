import re
import unicodedata

from odoo import models


class MailGatewayWhatsappService(models.AbstractModel):
    """Envío de mensagens WhatsApp pelo módulo crm_iomr_whatsapp.

    Herda de mail.gateway.whatsapp e sobreescreve _send_payload para garantir
    a estrutura correta dos templates, incluindo o campo "policy": "deterministic"
    exigido pela Meta API, além de dar suporte ao tipo call_permission_request.

    O fluxo principal continua sendo o mail_gateway (OCA), mas este módulo
    intercepta os envios para adicionar a política necessária e suportar
    permisões de ligação, sem interferir no fluxo original.
    """

    _inherit = "mail.gateway.whatsapp"

    def _get_whatsapp_template_for_send(self):
        whatsapp_template_id = self.env.context.get("whatsapp_template_id")
        if not whatsapp_template_id:
            return False
        return self.env["mail.whatsapp.template"].sudo().browse(whatsapp_template_id)

    def _is_call_permission_request_template(self):
        whatsapp_template = self._get_whatsapp_template_for_send()
        if not whatsapp_template or not whatsapp_template.exists():
            return False
        template_names = (
            whatsapp_template.template_name or "",
            whatsapp_template.name or "",
        )
        for template_name in template_names:
            normalized_name = re.sub(r"[\s_]+", " ", str(template_name).lower())
            normalized_name = unicodedata.normalize("NFKD", normalized_name)
            normalized_name = "".join(
                character
                for character in normalized_name
                if not unicodedata.combining(character)
            )
            if "permission" in normalized_name or "permissao" in normalized_name:
                return True
        return False

    def _prepare_call_permission_request_components(
        self, whatsapp_template, body=False
    ):
        components = []
        body_text = str(body or (whatsapp_template.body if whatsapp_template else "") or "").strip()
        header = str(whatsapp_template.header or "").strip() if whatsapp_template else ""
        footer = str(whatsapp_template.footer or "").strip() if whatsapp_template else ""
        if header:
            components.append({"type": "header", "format": "TEXT", "text": header})
        components.append(
            {
                "type": "body",
                "parameters": [{"type": "text", "text": body_text}],
            }
        )
        if footer:
            components.append({"type": "footer", "text": footer})
        components.append({"type": "call_permission_request"})
        return components

    def _send_call_permission_request_payload(self, channel, body=False):
        whatsapp_template = self._get_whatsapp_template_for_send()
        if not whatsapp_template or not whatsapp_template.exists():
            whatsapp_template = self.env["mail.whatsapp.template"]
        components = self._prepare_call_permission_request_components(
            whatsapp_template, body=body
        )
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": channel.gateway_channel_token,
            "type": "template",
            "template": {
                "name": whatsapp_template.template_name,
                "language": {"policy": "deterministic", "code": whatsapp_template.language},
                "components": components,
            },
        }

    def _send_payload(
        self,
        channel,
        body=False,
        media_id=False,
        media_type=False,
        media_name=False,
    ):
        if not media_id and self._is_call_permission_request_template():
            return self._send_call_permission_request_payload(
                channel=channel, body=body
            )
        # Para templates regulares, constrói o payload garantindo o "policy": "deterministic"
        whatsapp_template = self._get_whatsapp_template_for_send()
        if not whatsapp_template or not whatsapp_template.exists():
            whatsapp_template = self.env["mail.whatsapp.template"]
        if body:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": channel.gateway_channel_token,
            }
            if whatsapp_template:
                payload.update(
                    {
                        "type": "template",
                        "template": {
                            "name": whatsapp_template.template_name,
                            # IMPORTANTE: incluir policy "deterministic" conforme exigido pela Meta
                            "language": {"policy": "deterministic", "code": whatsapp_template.language},
                            "components": whatsapp_template.prepare_value_to_send(),
                        },
                    }
                )
            else:
                payload.update(
                    {
                        "type": "text",
                        "text": {
                            "preview_url": False,
                            "body": self._html_to_whatsapp(body),
                        },
                    }
                )
            return payload
        # Sem template e sem corpo: retorna payload texto padrão
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": channel.gateway_channel_token,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": body or "",
            },
        }