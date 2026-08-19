from odoo import api, fields, models


class CommissionResult(models.Model):
    _name = "commission.result"
    _description = "Commission Monthly Result"
    _order = "period_code desc, member_id"

    name = fields.Char(compute="_compute_name", store=True)
    member_id = fields.Many2one(
        "commission.member",
        string="Member",
        required=True,
    )
    period_code = fields.Char(
        string="Period",
        required=True,
    )
    policy_id = fields.Many2one(
        "commission.policy",
        string="Policy",
    )
    target_id = fields.Many2one(
        "commission.target",
        string="Target",
    )
    target_amount = fields.Monetary(
        string="Target Amount",
        currency_field="currency_id",
    )
    lio_sales_amount = fields.Monetary(
        string="LIO Sales",
        currency_field="currency_id",
    )
    hospital_sales_amount = fields.Monetary(
        string="Hospital Sales",
        currency_field="currency_id",
    )
    delivery_pct = fields.Float(
        string="Delivery (%)",
        compute="_compute_delivery_pct",
        store=True,
    )
    range_label = fields.Char()
    base_rate = fields.Float(string="Base Rate (%)")
    crm_bonus_rate = fields.Float(string="CRM Bonus (%)")
    final_rate = fields.Float(
        string="Final Rate (%)",
        compute="_compute_final_rate",
        store=True,
    )
    commission_base_amount = fields.Monetary(
        string="Commission Base",
        currency_field="currency_id",
    )
    commission_amount = fields.Monetary(
        string="Commission Amount",
        currency_field="currency_id",
        compute="_compute_commission_amount",
        store=True,
    )
    is_crm_score = fields.Float(string="IS-CRM Score (%)", default=100.0)
    is_crm_ok = fields.Boolean(
        string="IS-CRM OK",
        compute="_compute_is_crm_ok",
        store=True,
    )
    quarter_recovery_amount = fields.Monetary(
        string="Quarter Recovery",
        currency_field="currency_id",
    )
    state = fields.Selection(
        [("draft", "Draft"),
         ("calculated", "Calculated"),
         ("approved", "Approved"),
         ("paid", "Paid")],
        default="draft",
    )
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
    )
    coordinator_rate = fields.Float(
        string="Coordinator Rate (%)",
        compute="_compute_coordinator_rate",
        store=True,
    )
    orientadora_count = fields.Integer(
        string="Orientadoras",
        compute="_compute_orientadora_count",
    )

    @api.depends("member_id", "period_code")
    def _compute_name(self):
        for rec in self:
            if rec.member_id and rec.period_code:
                rec.name = f"{rec.member_id.name} - {rec.period_code}"

    @api.depends("target_amount", "commission_base_amount")
    def _compute_delivery_pct(self):
        for rec in self:
            if rec.target_amount:
                rec.delivery_pct = (
                    (rec.commission_base_amount / rec.target_amount) * 100.0
                )
            else:
                rec.delivery_pct = 0.0

    @api.depends("is_crm_score")
    def _compute_is_crm_ok(self):
        for rec in self:
            policy = rec.policy_id or self._get_active_policy()
            crm_min = policy.crm_min_pct if policy else 95.0
            rec.is_crm_ok = rec.is_crm_score >= crm_min

    @api.depends("base_rate", "crm_bonus_rate", "is_crm_ok")
    def _compute_final_rate(self):
        for rec in self:
            rate = rec.base_rate
            if rec.is_crm_ok:
                rate += rec.crm_bonus_rate
            rec.final_rate = rate

    @api.depends("commission_base_amount", "final_rate")
    def _compute_commission_amount(self):
        for rec in self:
            rec.commission_amount = (
                (rec.commission_base_amount or 0.0)
                * (rec.final_rate or 0.0) / 100.0
            )

    @api.depends("policy_id")
    def _compute_coordinator_rate(self):
        for rec in self:
            if rec.member_id.member_type == "coordenadora" and rec.policy_id:
                rec.coordinator_rate = rec.policy_id.coordinator_rate
            else:
                rec.coordinator_rate = 0.0

    def _compute_orientadora_count(self):
        for rec in self:
            if rec.member_id.member_type == "coordenadora":
                rec.orientadora_count = self.env["commission.member"].search_count([
                    ("member_type", "=", "orientadora"),
                ])
            else:
                rec.orientadora_count = 0

    def _get_active_policy(self):
        return self.env["commission.policy"].search(
            [("active", "=", True)], order="date_start desc", limit=1
        )

    def _get_policy_rate(self, delivery_pct, policy):
        policy = policy or self._get_active_policy()
        if not policy:
            return False
        for line in policy.line_ids.sorted(key=lambda l: l.sequence):
            if line.delivery_pct_from <= delivery_pct <= line.delivery_pct_to:
                return line
        return False

    def _get_quarter(self):
        self.ensure_one()
        if self.period_code and len(self.period_code) == 7:
            month = int(self.period_code.split("-")[1])
            q = (month - 1) // 3 + 1
            return f"Q{q}"
        return False

    def _get_year(self):
        self.ensure_one()
        if self.period_code and len(self.period_code) == 7:
            return int(self.period_code.split("-")[0])
        return False

    def action_calculate(self):
        for rec in self:
            policy = rec.policy_id or self._get_active_policy()
            if not policy:
                continue
            rec.policy_id = policy.id

            if rec.member_id.member_type == "coordenadora":
                rec._calculate_coordinator(policy)
            else:
                rec._calculate_orientadora(policy)
            rec.state = "calculated"

    def _calculate_orientadora(self, policy):
        self.ensure_one()

        target = self.target_id or self.env["commission.target"].search([
            ("member_id", "=", self.member_id.id),
            ("period_code", "=", self.period_code),
        ], limit=1)
        if target:
            self.target_id = target.id
            self.target_amount = target.individual_target_amount

        sales = self.env["commission.sale"].search([
            ("owner_member_id", "=", self.member_id.id),
            ("period_code", "=", self.period_code),
            ("status", "in", ("confirmed", "invoiced")),
        ])

        self.lio_sales_amount = sum(sales.mapped("lio_upgrade_amount"))
        self.hospital_sales_amount = sum(sales.mapped("hospital_net_amount"))

        commissionable = 0.0
        crm_score_sum = 0.0
        sale_count = len(sales)

        for sale in sales:
            if sale.is_lens_sale:
                lens_rate = sale._get_lens_rate()
                if lens_rate:
                    commissionable += sale._get_commissionable_amount() * lens_rate / 100.0
            else:
                commissionable += sale._get_commissionable_amount()
            crm_score_sum += sale.crm_pct

        self.commission_base_amount = commissionable
        self.is_crm_score = (crm_score_sum / sale_count) if sale_count else 100.0

        rate_line = self._get_policy_rate(self.delivery_pct, policy)
        if rate_line:
            self.base_rate = rate_line.base_rate
            self.range_label = (
                f"{rate_line.delivery_pct_from:.0f}% - {rate_line.delivery_pct_to:.0f}%"
            )
            self.crm_bonus_rate = policy.crm_bonus_rate if self.is_crm_ok else -policy.crm_penalty_rate

    def _calculate_coordinator(self, policy):
        self.ensure_one()

        orientadora_type = self.env["commission.member"].search([
            ("member_type", "=", "orientadora"),
        ])

        total_commissionable = 0.0
        total_target = 0.0
        total_lio = 0.0
        total_hospital = 0.0

        for orientadora in orientadora_type:
            orientadora_results = self.env["commission.result"].search([
                ("member_id", "=", orientadora.id),
                ("period_code", "=", self.period_code),
                ("state", "in", ("calculated", "approved", "paid")),
            ])
            for result in orientadora_results:
                total_commissionable += result.commission_base_amount
                total_target += result.target_amount
                total_lio += result.lio_sales_amount
                total_hospital += result.hospital_sales_amount

        self.target_amount = total_target
        self.lio_sales_amount = total_lio
        self.hospital_sales_amount = total_hospital
        self.commission_base_amount = total_commissionable

        self.base_rate = policy.coordinator_rate
        self.range_label = "Coordenadora"
        self.crm_bonus_rate = 0.0
        self.is_crm_score = 100.0

    def action_approve(self):
        for rec in self:
            rec.state = "approved"

    def action_pay(self):
        for rec in self:
            rec.state = "paid"

    def action_draft(self):
        for rec in self:
            rec.state = "draft"

    def _check_and_create_recovery(self):
        for rec in self.filtered(lambda r: r.state == "calculated"):
            quarter = rec._get_quarter()
            year = rec._get_year()
            if quarter and year:
                recovery = self.env["commission.recovery"].search([
                    ("member_id", "=", rec.member_id.id),
                    ("quarter", "=", quarter),
                    ("year", "=", year),
                ], limit=1)
                if not recovery:
                    recovery = self.env["commission.recovery"].create({
                        "member_id": rec.member_id.id,
                        "quarter": quarter,
                        "year": year,
                    })
                recovery.action_calculate()
