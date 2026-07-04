from odoo import api, fields, models


class CommissionRecovery(models.Model):
    _name = "commission.recovery"
    _description = "Quarterly Commission Recovery"
    _order = "year desc, quarter"

    name = fields.Char(compute="_compute_name", store=True)
    member_id = fields.Many2one(
        "commission.member",
        string="Member",
        required=True,
    )
    quarter = fields.Selection(
        [("Q1", "Q1"), ("Q2", "Q2"), ("Q3", "Q3"), ("Q4", "Q4")],
        required=True,
    )
    year = fields.Integer(required=True)
    quarter_target_amount = fields.Monetary(
        string="Quarter Target",
        currency_field="currency_id",
    )
    quarter_sales_amount = fields.Monetary(
        string="Quarter Sales",
        currency_field="currency_id",
    )
    quarter_delivery_pct = fields.Float(
        string="Quarter Performance (%)",
        compute="_compute_quarter_pct",
        store=True,
    )
    expected_commission_amount = fields.Monetary(
        string="Expected Commission",
        currency_field="currency_id",
    )
    calculated_commission_amount = fields.Monetary(
        string="Calculated Commission",
        currency_field="currency_id",
    )
    recovery_amount = fields.Monetary(
        string="Recovery Amount",
        currency_field="currency_id",
        compute="_compute_recovery",
        store=True,
    )
    state = fields.Selection(
        [("pending", "Pending"),
         ("recovered", "Recovered"),
         ("lost", "Lost")],
        default="pending",
    )
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
    )

    @api.depends("member_id", "quarter", "year")
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.member_id.name} - {rec.quarter}/{rec.year}"

    @api.depends("quarter_target_amount", "quarter_sales_amount")
    def _compute_quarter_pct(self):
        for rec in self:
            if rec.quarter_target_amount:
                rec.quarter_delivery_pct = (
                    (rec.quarter_sales_amount / rec.quarter_target_amount) * 100.0
                )
            else:
                rec.quarter_delivery_pct = 0.0

    @api.depends("quarter_delivery_pct", "expected_commission_amount",
                 "calculated_commission_amount")
    def _compute_recovery(self):
        for rec in self:
            if rec.quarter_delivery_pct >= 100.0:
                rec.recovery_amount = (
                    (rec.expected_commission_amount or 0.0)
                    - (rec.calculated_commission_amount or 0.0)
                )
                if rec.recovery_amount > 0:
                    rec.state = "recovered"
                else:
                    rec.recovery_amount = 0.0
                    rec.state = "pending"
            else:
                rec.recovery_amount = 0.0

    def action_calculate(self):
        for rec in self:
            targets = self.env["commission.target"].search([
                ("member_id", "=", rec.member_id.id),
                ("year", "=", rec.year),
                ("period_code", "=like", f"{rec.year}-%"),
            ])
            quarter_map = {"Q1": [1, 2, 3], "Q2": [4, 5, 6],
                           "Q3": [7, 8, 9], "Q4": [10, 11, 12]}
            q_months = quarter_map.get(rec.quarter, [])
            q_targets = targets.filtered(
                lambda t: int(t.month) in q_months
            )
            rec.quarter_target_amount = sum(q_targets.mapped("individual_target_amount"))

            results = self.env["commission.result"].search([
                ("member_id", "=", rec.member_id.id),
                ("state", "=", "calculated"),
            ])
            q_results = results.filtered(
                lambda r: r._get_quarter() == rec.quarter
                and r._get_year() == rec.year
            )
            rec.quarter_sales_amount = sum(q_results.mapped("commission_base_amount"))
            rec.expected_commission_amount = sum(q_results.mapped("commission_amount"))
