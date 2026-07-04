from odoo import api, fields, models


class CommissionSaleLine(models.Model):
    _name = "commission.sale.line"
    _description = "Commission Sale Line Detail"

    sale_id = fields.Many2one(
        "commission.sale",
        string="Sale",
        required=True,
        ondelete="cascade",
    )
    line_type = fields.Selection(
        [("hospital", "Hospital Portion"),
         ("medical_fee", "Medical Fee"),
         ("lio_package", "LIO Package"),
         ("lio_upgrade", "LIO Upgrade")],
        required=True,
    )
    amount = fields.Monetary(
        string="Amount",
        currency_field="currency_id",
        required=True,
    )
    eligible_for_commission = fields.Boolean(
        string="Eligible for Commission",
        compute="_compute_eligibility",
        store=True,
    )
    exclusion_reason = fields.Char(readonly=True)
    currency_id = fields.Many2one(
        "res.currency",
        related="sale_id.currency_id",
    )

    @api.depends("line_type")
    def _compute_eligibility(self):
        for rec in self:
            if rec.line_type == "medical_fee":
                rec.eligible_for_commission = False
                rec.exclusion_reason = "Medical fee never commissions"
            elif rec.line_type == "lio_package":
                rec.eligible_for_commission = False
                rec.exclusion_reason = "Package LIO never commissions"
            else:
                rec.eligible_for_commission = True
                rec.exclusion_reason = False
