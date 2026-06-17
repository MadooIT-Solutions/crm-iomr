# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class CommissionSettlement(models.Model):
    _inherit = "commission.settlement"

    settlement_type = fields.Selection(
        selection_add=[("crm_performance", "CRM Performance")],
        ondelete={"crm_performance": "set default"},
    )
    target_id = fields.Many2one(
        "crm.commission.target",
        string="Related target",
    )
    is_crm_score = fields.Float(string="IS-CRM score")
    performance_pct = fields.Float(string="Performance (%)")
