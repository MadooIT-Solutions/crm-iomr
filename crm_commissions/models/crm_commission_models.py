# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountInvoiceLineAgent(models.Model):
    _inherit = "account.invoice.line.agent"

    @api.depends(
        "object_id.price_subtotal",
        "object_id.commission_free",
        "commission_id",
    )
    def _compute_amount(self):
        for line in self:
            inv_line = line.object_id
            amount = line._get_commission_amount(
                line.commission_id,
                inv_line.price_subtotal,
                inv_line.product_id,
                inv_line.quantity,
            )
            if line.invoice_id.move_type and "refund" in line.invoice_id.move_type:
                amount = -amount
            if line.commission_split_percent:
                amount *= line.commission_split_percent / 100.0
            line.amount = amount


class Commission(models.Model):
    _inherit = "commission"

    commission_type = fields.Selection(
        selection_add=[("progressive", "Progressive by performance")],
        ondelete={"progressive": "set default"},
    )
    progressive_line_ids = fields.One2many(
        string="Progressive rates",
        comodel_name="commission.progressive.line",
        inverse_name="commission_id",
    )
    is_crm_bonus = fields.Float(
        string="IS-CRM bonus (%)",
        default=0.25,
        help="Additional percentage when IS-CRM >= 95%",
    )
    is_crm_penalty = fields.Float(
        string="IS-CRM penalty (%)",
        default=0.25,
        help="Penalty percentage when IS-CRM < 95%",
    )
    min_margin = fields.Float(
        string="Minimum margin (%)",
        default=35.0,
        help="Minimum profit margin for full commission validation",
    )
    max_discount = fields.Float(
        string="Max discount (%)",
        default=5.0,
        help="Maximum discount allowed without management approval",
    )

    def _get_progressive_rate(self, performance_pct):
        self.ensure_one()
        lines = self.progressive_line_ids.sorted(key=lambda rec: rec.sequence)
        for line in lines:
            if line.percent_from <= performance_pct <= line.percent_to:
                return line
        last_line = lines[-1] if lines else False
        if last_line and performance_pct > last_line.percent_to:
            return last_line
        if lines:
            return lines[0]
        return False

    def compute_progressive_commission(self, base_amount, performance_pct, is_crm_ok):
        self.ensure_one()
        rate = self._get_progressive_rate(performance_pct)
        if not rate:
            return 0.0
        commission_amount = base_amount * (rate.commission_percent / 100.0)
        if is_crm_ok:
            commission_amount += base_amount * (self.is_crm_bonus / 100.0)
        else:
            commission_amount -= base_amount * (self.is_crm_penalty / 100.0)
        return max(commission_amount, 0.0)


class CommissionProgressiveLine(models.Model):
    _name = "commission.progressive.line"
    _description = "Commission progressive rate line"
    _order = "sequence, id"

    commission_id = fields.Many2one(
        "commission",
        string="Commission",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    percent_from = fields.Float(string="Performance from (%)", required=True)
    percent_to = fields.Float(string="Performance to (%)", required=True)
    commission_percent = fields.Float(
        string="Commission rate (%)",
        required=True,
        help="Base commission percentage for this range",
    )

    @api.constrains("percent_from", "percent_to")
    def _check_percent_ranges(self):
        for line in self:
            if line.percent_to < line.percent_from:
                raise ValidationError(
                    _("Upper limit cannot be lower than lower limit.")
                )
            if line.percent_from < 0 or line.percent_to < 0:
                raise ValidationError(_("Percentages must be non-negative."))


class CommissionTarget(models.Model):
    _name = "crm.commission.target"
    _description = "Commission monthly/quarterly target"
    _order = "target_date desc"

    name = fields.Char(compute="_compute_name", store=True)
    agent_id = fields.Many2one(
        "res.partner",
        string="Salesperson",
        domain=[("type_partner", "=", "orientadora")],
        required=True,
    )
    target_date = fields.Date(string="Target month", required=True)
    target_amount = fields.Monetary(
        string="Monthly target",
        currency_field="currency_id",
        required=True,
    )
    quarterly_target_amount = fields.Monetary(
        string="Quarterly target",
        currency_field="currency_id",
        compute="_compute_quarterly_target",
        store=True,
    )
    achieved_amount = fields.Monetary(
        string="Achieved",
        currency_field="currency_id",
        compute="_compute_achieved",
        store=True,
    )
    performance_pct = fields.Float(
        string="Performance (%)",
        compute="_compute_performance",
        store=True,
    )
    is_crm_score = fields.Float(
        string="IS-CRM score (%)",
        default=100.0,
        help="CRM Health Index score for this period",
    )
    is_crm_ok = fields.Boolean(
        string="IS-CRM OK",
        compute="_compute_is_crm_ok",
        store=True,
    )
    commission_id = fields.Many2one(
        "commission",
        string="Commission rule",
        related="agent_id.commission_id",
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("in_progress", "In progress"),
            ("achieved", "Achieved"),
            ("lost", "Lost"),
        ],
        default="draft",
    )
    quarter = fields.Char(
        compute="_compute_quarter",
        store=True,
    )

    @api.depends("target_date")
    def _compute_quarter(self):
        for rec in self:
            if rec.target_date:
                month = rec.target_date.month
                q = (month - 1) // 3 + 1
                rec.quarter = f"Q{q}/{rec.target_date.year}"

    @api.depends("agent_id", "target_date")
    def _compute_name(self):
        for rec in self:
            if rec.agent_id and rec.target_date:
                rec.name = f"{rec.agent_id.name} - {rec.target_date.strftime('%m/%Y')}"

    @api.depends("target_date")
    def _compute_quarterly_target(self):
        for rec in self:
            if rec.target_date:
                month = rec.target_date.month
                q_start = ((month - 1) // 3) * 3 + 1
                date_from = rec.target_date.replace(month=q_start, day=1)
                date_to = date_from + relativedelta(months=3, days=-1)
                targets = self.search(
                    [
                        ("agent_id", "=", rec.agent_id.id),
                        ("target_date", ">=", date_from),
                        ("target_date", "<=", date_to),
                    ]
                )
                rec.quarterly_target_amount = sum(targets.mapped("target_amount"))

    @api.depends("agent_id", "target_date")
    def _compute_achieved(self):
        for rec in self:
            if rec.agent_id and rec.target_date:
                month_start = rec.target_date.replace(day=1)
                next_month = month_start + relativedelta(months=1)
                orders = self.env["sale.order"].search(
                    [
                        ("partner_id.agent_ids", "in", rec.agent_id.id),
                        ("date_order", ">=", month_start),
                        ("date_order", "<", next_month),
                        ("state", "in", ["sale", "done"]),
                    ]
                )
                rec.achieved_amount = sum(orders.mapped("amount_total"))

    @api.depends("achieved_amount", "target_amount")
    def _compute_performance(self):
        for rec in self:
            if rec.target_amount:
                rec.performance_pct = (rec.achieved_amount / rec.target_amount) * 100.0
            else:
                rec.performance_pct = 0.0

    @api.depends("is_crm_score")
    def _compute_is_crm_ok(self):
        for rec in self:
            rec.is_crm_ok = rec.is_crm_score >= 95.0

    @api.depends("performance_pct")
    def _compute_state(self):
        for rec in self:
            if rec.performance_pct >= 100:
                rec.state = "achieved"
            elif rec.performance_pct > 0:
                rec.state = "in_progress"
            else:
                rec.state = "draft"


class CommissionQuarterlyBonus(models.Model):
    _name = "crm.commission.quarterly.bonus"
    _description = "Quarterly commission bonus/recovery"
    _order = "quarter, agent_id"

    name = fields.Char(compute="_compute_name", store=True)
    agent_id = fields.Many2one(
        "res.partner",
        string="Agent",
        required=True,
    )
    quarter = fields.Char(required=True)
    year = fields.Integer(required=True)
    monthly_targets = fields.Many2many(
        "crm.commission.target",
        string="Monthly targets",
    )
    total_target = fields.Monetary(
        string="Total quarterly target",
        currency_field="currency_id",
    )
    total_achieved = fields.Monetary(
        string="Total achieved",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    quarterly_pct = fields.Float(
        string="Quarterly performance (%)",
        compute="_compute_totals",
        store=True,
    )
    lost_commission_recovered = fields.Monetary(
        string="Lost commission recovered",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    bonus_amount = fields.Monetary(
        string="Bonus amount",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    state = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("recovered", "Recovered/Paid"),
            ("lost", "Lost"),
        ],
        default="pending",
    )
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )

    @api.depends("agent_id", "quarter", "year")
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.agent_id.name} - {rec.quarter}/{rec.year}"

    @api.depends("monthly_targets", "total_target")
    def _compute_totals(self):
        for rec in self:
            targets = rec.monthly_targets
            rec.total_achieved = sum(targets.mapped("achieved_amount"))
            if rec.total_target:
                rec.quarterly_pct = (rec.total_achieved / rec.total_target) * 100.0
            if rec.quarterly_pct >= 100:
                rec.lost_commission_recovered = sum(
                    targets.filtered(lambda t: t.performance_pct < 100).mapped(
                        "achieved_amount"
                    )
                )
