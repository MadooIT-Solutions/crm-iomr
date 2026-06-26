from odoo import api, fields, models


class CommissionSale(models.Model):
    _name = "commission.sale"
    _description = "Commission Sale/Conversion"
    _order = "date desc, id desc"

    name = fields.Char(
        string="Reference",
        required=True,
        default="/",
    )
    date = fields.Date(
        string="Sale Date",
        required=True,
        default=fields.Date.context_today,
    )
    period_code = fields.Char(
        compute="_compute_period_code",
        store=True,
    )
    owner_member_id = fields.Many2one(
        "commission.member",
        string="Owner",
        domain=[("member_type", "=", "orientadora")],
        required=True,
    )
    patient_name = fields.Char(required=True)
    surgery_type = fields.Selection(
        [("catarata", "Catarata"),
         ("refrativa", "Refrativa"),
         ("glaucoma", "Glaucoma"),
         ("vitrectomia", "Vitrectomia"),
         ("outros", "Outros")],
    )
    sale_category = fields.Selection(
        [("particular", "Particular"),
         ("convenio", "Convênio"),
         ("saude_todos", "Saúde para Todos"),
         ("outras", "Outras")],
        required=True,
    )
    lio_package_amount = fields.Monetary(
        string="LIO Package Amount",
        currency_field="currency_id",
    )
    lio_upgrade_amount = fields.Monetary(
        string="LIO Upgrade Amount",
        currency_field="currency_id",
    )
    has_lio_upgrade = fields.Boolean(
        compute="_compute_has_lio_upgrade",
        store=True,
    )
    hospital_gross_amount = fields.Monetary(
        string="Hospital Gross Amount",
        currency_field="currency_id",
    )
    hospital_tax_pct = fields.Float(
        string="Hospital Tax (%)",
        default=0.0,
    )
    hospital_cost_pct = fields.Float(
        string="Hospital Cost (%)",
        default=0.0,
    )
    hospital_net_amount = fields.Monetary(
        string="Hospital Net Amount",
        currency_field="currency_id",
        compute="_compute_hospital_net",
        store=True,
    )
    medical_fee_amount = fields.Monetary(
        string="Medical Fee Amount",
        currency_field="currency_id",
    )
    crm_pct = fields.Float(string="IS-CRM (%)", default=100.0)
    margin_pct = fields.Float(
        string="Margin (%)",
        compute="_compute_margin",
        store=True,
    )
    discount_pct = fields.Float(string="Discount (%)", default=0.0)
    discount_approved = fields.Boolean(default=True)
    status = fields.Selection(
        [("draft", "Draft"),
         ("confirmed", "Confirmed"),
         ("invoiced", "Invoiced"),
         ("cancelled", "Cancelled")],
        default="draft",
    )
    notes = fields.Text()
    line_ids = fields.One2many(
        "commission.sale.line",
        "sale_id",
        string="Detail Lines",
    )
    is_lens_sale = fields.Boolean(string="Lens Sale?")
    lens_type = fields.Selection(
        [("gelatinous", "Gelatinous"),
         ("rigid", "Rigid")],
        string="Lens Type",
    )
    lens_commission_type = fields.Selection(
        [("with_exam", "With Exam (1.5%)"),
         ("without_exam", "Without Exam (5%)")],
        string="Lens Commission Type",
    )
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
    )

    @api.depends("lio_upgrade_amount")
    def _compute_has_lio_upgrade(self):
        for rec in self:
            rec.has_lio_upgrade = bool(rec.lio_upgrade_amount and rec.lio_upgrade_amount > 0)

    @api.depends("date")
    def _compute_period_code(self):
        for rec in self:
            if rec.date:
                rec.period_code = rec.date.strftime("%Y-%m")

    @api.depends("hospital_gross_amount", "hospital_tax_pct", "hospital_cost_pct")
    def _compute_hospital_net(self):
        for rec in self:
            gross = rec.hospital_gross_amount or 0.0
            tax = gross * (rec.hospital_tax_pct / 100.0)
            cost = gross * (rec.hospital_cost_pct / 100.0)
            rec.hospital_net_amount = gross - tax - cost

    @api.depends("hospital_gross_amount", "medical_fee_amount", "lio_package_amount",
                 "lio_upgrade_amount", "discount_pct")
    def _compute_margin(self):
        for rec in self:
            total_revenue = (
                (rec.hospital_gross_amount or 0.0)
                + (rec.medical_fee_amount or 0.0)
                + (rec.lio_package_amount or 0.0)
                + (rec.lio_upgrade_amount or 0.0)
            )
            if total_revenue:
                discounted = total_revenue * (1 - (rec.discount_pct or 0.0) / 100.0)
                cost_estimate = total_revenue * 0.65
                if discounted:
                    rec.margin_pct = (discounted - cost_estimate) / discounted * 100.0
                else:
                    rec.margin_pct = 0.0
            else:
                rec.margin_pct = 0.0

    def action_confirm(self):
        for rec in self:
            rec.status = "confirmed"

    def action_cancel(self):
        for rec in self:
            rec.status = "cancelled"

    def _get_commissionable_amount(self):
        self.ensure_one()
        total = 0.0
        for line in self.line_ids:
            if line.eligible_for_commission:
                total += line.amount
        if self.is_lens_sale:
            total = (self.hospital_gross_amount or 0.0) + (self.lio_upgrade_amount or 0.0)
        return total

    def _get_lens_rate(self):
        self.ensure_one()
        if not self.is_lens_sale:
            return False
        if self.lens_type == "rigid":
            return 1.5
        if self.lens_commission_type == "with_exam":
            return 1.5
        if self.lens_commission_type == "without_exam":
            return 5.0
        return 1.5
