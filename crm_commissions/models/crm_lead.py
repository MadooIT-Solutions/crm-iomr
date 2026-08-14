# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    def _prepare_opportunity_quotation_context(self):
        ctx = super()._prepare_opportunity_quotation_context()
        if self.doctor:
            ctx["default_doctor_id"] = self.doctor.id
        if self.referred_partner:
            ctx["default_referred_partner"] = [(4, pid) for pid in self.referred_partner.ids]
        return ctx

    is_crm_score = fields.Float(
        string="IS-CRM score",
        default=100.0,
        help="CRM quality score for this lead",
    )
    commission_percent = fields.Float(
        string="Commission (%)",
        help="Fixed commission percentage for this opportunity",
    )
    discount_percent = fields.Float(
        string="Discount (%)",
    )
    discount_approved = fields.Boolean(
        string="Discount approved",
        default=False,
    )
    margin_percent = fields.Float(
        string="Margin (%)",
        compute="_compute_margin",
        store=True,
    )
    margin_ok = fields.Boolean(
        string="Margin OK",
        compute="_compute_margin",
        store=True,
    )

    @api.depends("expected_revenue", "discount_percent")
    def _compute_margin(self):
        for rec in self:
            if rec.expected_revenue and rec.discount_percent:
                discounted = rec.expected_revenue * (1 - rec.discount_percent / 100.0)
                rec.margin_percent = (
                    (discounted - rec.expected_revenue * 0.65) / discounted * 100.0
                    if discounted
                    else 0.0
                )
                rec.margin_ok = rec.margin_percent >= 35.0
            else:
                rec.margin_percent = 100.0
                rec.margin_ok = True

    def _get_sdr_partner_from_rotation(self):
        """Return the SDR partner the opportunity passed through, if any.

        Checks the rotation history for any user whose partner is an SDR,
        either as the previous or the current seller of the opportunity.
        """
        self.ensure_one()
        rotations = self.env["crm.lead.rotation"].sudo().search(
            [("lead_id", "=", self.id)]
        )
        for rotation in rotations:
            for user in (rotation.user_to_id, rotation.user_from_id):
                if user and user.partner_id.type_partner == "sdr":
                    return user.partner_id
        return False

    def action_validate_discount(self):
        self.ensure_one()
        self.discount_approved = True

    def action_claim_whatsapp_conversation(self):
        self.ensure_one()
        channel = self.whatsapp_channel_id
        if not channel:
            return
        current_partner = self.env.user.partner_id
        if not any(
            member.partner_id == current_partner
            for member in channel.channel_member_ids
        ):
            self.env["discuss.channel.member"].sudo().create(
                {
                    "partner_id": current_partner.id,
                    "channel_id": channel.id,
                    "is_pinned": False,
                    "unpin_dt": False,
                }
            )
        return {
            "type": "ir.actions.client",
            "tag": "mail.action_discuss",
            "params": {"active_id": f"discuss.channel_{channel.id}"},
        }
