from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class CommissionTarget(models.Model):
    _name = "commission.target"
    _description = "Commission Target"
    _order = "period_code desc"

    name = fields.Char(compute="_compute_name", store=True)
    member_id = fields.Many2one(
        "commission.member",
        string="Member",
        domain=[("member_type", "=", "orientadora")],
        required=True,
    )
    year = fields.Integer(required=True)
    month = fields.Selection(
        [(str(i), str(i)) for i in range(1, 13)],
        string="Month",
        required=True,
    )
    period_code = fields.Char(
        compute="_compute_period_code",
        store=True,
    )
    team_target_amount = fields.Monetary(
        string="Team Target",
        currency_field="currency_id",
    )
    individual_target_amount = fields.Monetary(
        string="Individual Target",
        currency_field="currency_id",
        required=True,
    )
    origin_type = fields.Selection(
        [("auto", "Auto"), ("manual", "Manual")],
        default="auto",
    )
    state = fields.Selection(
        [("draft", "Draft"),
         ("in_progress", "In Progress"),
         ("achieved", "Achieved"),
         ("lost", "Lost")],
        default="draft",
    )
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
    )

    @api.depends("member_id", "year", "month")
    def _compute_period_code(self):
        for rec in self:
            if rec.year and rec.month:
                rec.period_code = f"{rec.year}-{int(rec.month):02d}"

    @api.depends("member_id", "period_code")
    def _compute_name(self):
        for rec in self:
            if rec.member_id and rec.period_code:
                rec.name = f"{rec.member_id.name} - {rec.period_code}"
