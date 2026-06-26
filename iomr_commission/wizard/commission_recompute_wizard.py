from odoo import fields, models


class CommissionRecomputeWizard(models.TransientModel):
    _name = "commission.recompute.wizard"
    _description = "Recompute Commission for Period"

    period_code = fields.Char(
        string="Period (YYYY-MM)",
        required=True,
    )
    member_ids = fields.Many2many(
        "commission.member",
        string="Members",
        domain=[("member_type", "=", "orientadora")],
    )

    def action_recompute(self):
        domain = [("period_code", "=", self.period_code)]
        if self.member_ids:
            domain.append(("member_id", "in", self.member_ids.ids))

        results = self.env["commission.result"].search(domain)
        for result in results:
            result.action_calculate()
            result._check_and_create_recovery()

        return {"type": "ir.actions.act_window_close"}
