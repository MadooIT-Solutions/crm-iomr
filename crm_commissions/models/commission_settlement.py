# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class CommissionSettlement(models.Model):
    _inherit = "commission.settlement"

    settlement_type = fields.Selection(
        selection_add=[
            ("crm_performance", "CRM Performance"),
            ("crm_quarterly_recovery", "CRM Quarterly Recovery"),
        ],
        ondelete={
            "crm_performance": "set default",
            "crm_quarterly_recovery": "set default",
        },
    )
    target_id = fields.Many2one(
        "crm.commission.target",
        string="Related target",
    )
    is_crm_score = fields.Float(string="IS-CRM score")
    performance_pct = fields.Float(string="Performance (%)")


class CommissionSettlementLine(models.Model):
    _inherit = "commission.settlement.line"

    target_id = fields.Many2one(
        "crm.commission.target",
        string="Related target",
        index=True,
        copy=False,
        readonly=True,
        ondelete="set null",
    )
    quarterly_bonus_id = fields.Many2one(
        "crm.commission.quarterly.bonus",
        string="Related quarterly bonus",
        index=True,
        copy=False,
        readonly=True,
        ondelete="set null",
        help="Bônus trimestral que originou esta linha de recuperação.",
    )
