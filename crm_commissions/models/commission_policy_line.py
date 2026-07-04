from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CommissionPolicyLine(models.Model):
    _name = "commission.policy.line"
    _description = "Commission Policy Rate Band"
    _order = "sequence, id"

    policy_id = fields.Many2one(
        "commission.policy",
        string="Policy",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    delivery_pct_from = fields.Float(string="Performance From (%)", required=True)
    delivery_pct_to = fields.Float(string="Performance To (%)", required=True)
    base_rate = fields.Float(string="Commission Rate (%)", required=True)

    @api.constrains("delivery_pct_from", "delivery_pct_to")
    def _check_percent_ranges(self):
        for line in self:
            if line.delivery_pct_to < line.delivery_pct_from:
                raise ValidationError(
                    _("Upper limit cannot be lower than lower limit.")
                )
            if line.delivery_pct_from < 0 or line.delivery_pct_to < 0:
                raise ValidationError(_("Percentages must be non-negative."))
