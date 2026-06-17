# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    orientadora_id = fields.Many2one(
        "res.partner",
        string="Orientadora",
        domain=[("type_partner", "=", "orientadora")],
        tracking=True,
    )
    sdr_id = fields.Many2one(
        "res.partner",
        string="SDR (Pré-orientadora)",
        domain=[("type_partner", "=", "sdr")],
        tracking=True,
    )
    coordinator_id = fields.Many2one(
        "res.partner",
        string="Coordenadora",
        domain=[("type_partner", "=", "coordenadora")],
    )
    doctor_id = fields.Many2one(
        "res.partner",
        string="Doctor/Médico",
        domain=[("type_partner", "in", ("doctorint", "doctorext"))],
        tracking=True,
    )
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

    def action_validate_discount(self):
        self.ensure_one()
        self.discount_approved = True
