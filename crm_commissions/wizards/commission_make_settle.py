# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

from odoo import fields, models


class CommissionMakeSettle(models.TransientModel):
    _inherit = "commission.make.settle"

    date_from = fields.Date(string="From")
    settlement_type = fields.Selection(
        selection_add=[("crm_performance", "CRM Performance")],
        ondelete={"crm_performance": "cascade"},
    )

    def _is_in_mass_period(self, line):
        """Check whether the source line falls inside the chosen period.

        ``invoice_date`` mirrors ``target_date`` on CRM targets and holds the
        invoice date on invoice agent lines, so it works for both settlement
        types.
        """
        self.ensure_one()
        line_date = line.invoice_date
        if not line_date:
            return True
        if self.date_from and line_date < self.date_from:
            return False
        if self.date_to and line_date > self.date_to:
            return False
        return True

    def _get_agent_lines(self, agent, date_to_agent):
        self.ensure_one()
        # The mass settlement wizard passes a context flag because the standard
        # wizard relies on period-truncated dates, which would leave the very
        # period selected by the user out of the settlement.
        strict = bool(self.env.context.get("commission_mass_settle"))
        if self.settlement_type == "crm_performance":
            domain = [
                ("agent_id", "=", agent.id),
                ("state", "in", ["achieved", "in_progress"]),
            ]
            if not strict:
                domain.append(("target_date", "<=", date_to_agent))
            lines = self.env["crm.commission.target"].search(
                domain, order="target_date asc"
            )
        else:
            upper = date_to_agent
            if strict and self.date_to:
                # Inclusive upper bound: `< date_to + 1` equals `<= date_to`.
                upper = self.date_to + timedelta(days=1)
            lines = super()._get_agent_lines(agent, upper)
        if strict:
            lines = lines.filtered(self._is_in_mass_period)
        return lines

    def _prepare_settlement_line_vals(self, settlement, line):
        values = super()._prepare_settlement_line_vals(settlement, line)
        if self.settlement_type == "crm_performance":
            values.update(
                {
                    "settlement_id": settlement.id,
                    "target_id": line.id,
                    "date": line.target_date,
                    "commission_id": line.commission_id.id,
                    "settled_amount": line.achieved_amount,
                }
            )
        return values
