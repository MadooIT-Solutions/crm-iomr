from odoo import fields, models


class CommissionPolicy(models.Model):
    _name = "commission.policy"
    _description = "Commission Policy"
    _order = "date_start desc"

    name = fields.Char(required=True)
    date_start = fields.Date(required=True)
    date_end = fields.Date()
    margin_min_pct = fields.Float(
        string="Minimum Margin (%)",
        default=35.0,
        help="Minimum profit margin for commission eligibility",
    )
    crm_min_pct = fields.Float(
        string="IS-CRM Minimum (%)",
        default=95.0,
        help="Minimum CRM health index score for bonus eligibility",
    )
    max_discount_pct = fields.Float(
        string="Max Discount (%)",
        default=5.0,
        help="Maximum discount allowed without management approval",
    )
    crm_bonus_rate = fields.Float(
        string="CRM Bonus Rate (%)",
        default=0.25,
        help="Additional commission rate when IS-CRM >= minimum",
    )
    crm_penalty_rate = fields.Float(
        string="CRM Penalty Rate (%)",
        default=0.25,
        help="Commission rate deduction when IS-CRM < minimum",
    )
    coordinator_rate = fields.Float(
        string="Coordinator Rate (%)",
        default=0.5,
        help="Fixed commission rate for coordinators on total Orientadora sales",
    )
    line_ids = fields.One2many(
        "commission.policy.line",
        "policy_id",
        string="Rate Bands",
    )
    active = fields.Boolean(default=True)
