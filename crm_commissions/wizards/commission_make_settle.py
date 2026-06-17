# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class CommissionMakeSettle(models.TransientModel):
    _inherit = "commission.make.settle"

    settlement_type = fields.Selection(
        selection_add=[("crm_performance", "CRM Performance")],
        ondelete={"crm_performance": "cascade"},
    )

    def _get_agent_lines(self, agent, date_to_agent):
        self.ensure_one()
        if self.settlement_type == "crm_performance":
            return self.env["crm.commission.target"].search(
                [
                    ("agent_id", "=", agent.id),
                    ("target_date", "<=", date_to_agent),
                    ("state", "in", ["achieved", "in_progress"]),
                ]
            )
        return super()._get_agent_lines(agent, date_to_agent)

    def _prepare_settlement_line_vals(self, settlement, line):
        if self.settlement_type == "crm_performance":
            return {
                "settlement_id": settlement.id,
                "date": line.target_date,
                "commission_id": line.commission_id.id,
                "settled_amount": line.achieved_amount,
            }
        return super()._prepare_settlement_line_vals(settlement, line)
