# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression


class Commission(models.Model):
    _inherit = "commission"

    commission_type = fields.Selection(
        selection_add=[
            ("progressive", "Progressive by performance"),
            ("coordinator", "Coordinator (via policy)"),
        ],
        ondelete={
            "progressive": "set default",
            "coordinator": "set default",
        },
    )
    amount_base_type = fields.Selection(
        selection_add=[("net_amount_deduction", "Net (Gross - Taxes - Card Fee)")],
        ondelete={"net_amount_deduction": "set default"},
    )
    tax_deduction_pct = fields.Float(
        string="Tax Deduction (%)",
        default=0.0,
        help=(
            "Fixed percentage of taxes to deduct from the commission base "
            "before applying the commission rate (used with "
            "'Net (Gross - Taxes - Card Fee)' base type)."
        ),
    )
    deduct_card_fee = fields.Boolean(
        string="Deduct Card Fee",
        default=False,
        help=(
            "Deduct the credit card fee (sale_credit_card_fee) "
            "from the commission base before applying the commission rate."
        ),
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
    categ_ids = fields.Many2many(
        "product.category",
        string="Product Categories",
        help="Only apply this commission to products in these categories. Leave empty to apply to all.",
    )
    agent_rule_ids = fields.One2many(
        "commission.agent.rule",
        "commission_id",
        string="Agent Rules",
        help="Specific rules linking agents and categories to this commission.",
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

    _sql_constraints = [
        (
            "unique_agent_target_month",
            "UNIQUE (agent_id, target_date)",
            "Já existe uma meta mensal para esta vendedora neste mês.",
        ),
    ]

    name = fields.Char(compute="_compute_name", store=True)
    target_scope = fields.Selection(
        selection=[
            ("salesperson", "Vendedor(a)"),
            ("team", "Equipe de Vendas"),
        ],
        string="Aplicar meta a",
        default="salesperson",
        required=True,
        help="Individual: meta para um/a vendedor(a) específico/a. "
             "Equipe de Vendas: a meta é aplicada a todos os vendedores "
             "(orientadoras) da equipe selecionada ao clicar em 'Aplicar à Equipe'.",
    )
    team_id = fields.Many2one(
        "crm.team",
        string="Equipe de Vendas",
        help="Equipe cujos vendedores (orientadoras) receberão esta meta.",
    )
    agent_id = fields.Many2one(
        "res.partner",
        string="Salesperson",
        domain=[("type_partner", "=", "orientadora")],
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
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    invoice_date = fields.Date(
        string="Settlement date",
        related="target_date",
        readonly=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("in_progress", "In progress"),
            ("achieved", "Achieved"),
            ("lost", "Lost"),
        ],
        compute="_compute_state",
        store=True,
        readonly=True,
        default="draft",
    )
    quarter = fields.Char(
        compute="_compute_quarter",
        store=True,
    )

    @api.model
    def _normalize_target_month(self, value):
        """Keep one canonical target date per month (always day 1)."""
        if not value:
            return value
        return fields.Date.to_date(value).replace(day=1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("target_date"):
                vals["target_date"] = self._normalize_target_month(vals["target_date"])
        targets = super().create(vals_list)
        if not self.env.context.get("crm_commissions_skip_legacy_target_sync"):
            self.env["commission.target"].sudo()._sync_from_crm_targets(targets)
        keys = targets._get_quarterly_bonus_keys()
        if keys:
            targets._invalidate_quarterly_target_values(keys)
            self.env["crm.commission.quarterly.bonus"].sudo()._sync_for_keys(keys)
        return targets

    def write(self, vals):
        if vals.get("target_date"):
            vals["target_date"] = self._normalize_target_month(vals["target_date"])
        quarterly_sync_fields = {
            "target_scope",
            "agent_id",
            "target_date",
            "target_amount",
            "team_id",
            "currency_id",
        }
        legacy_sync_fields = (quarterly_sync_fields - {"team_id"}) | {
            "state",
            "achieved_amount",
            "performance_pct",
        }
        should_sync_quarterly = bool(quarterly_sync_fields.intersection(vals))
        should_sync_legacy = bool(legacy_sync_fields.intersection(vals))
        old_keys = self._get_quarterly_bonus_keys() if should_sync_quarterly else set()
        result = super().write(vals)
        if should_sync_legacy and not self.env.context.get(
            "crm_commissions_skip_legacy_target_sync"
        ):
            self.env["commission.target"].sudo()._sync_from_crm_targets(self)
        if should_sync_quarterly:
            keys = old_keys | self._get_quarterly_bonus_keys()
            if keys:
                self._invalidate_quarterly_target_values(keys)
                self.env["crm.commission.quarterly.bonus"].sudo()._sync_for_keys(keys)
        return result

    def unlink(self):
        keys = self._get_quarterly_bonus_keys()
        if not self.env.context.get("crm_commissions_skip_legacy_target_sync"):
            linked_targets = self.env["commission.target"].sudo().search([
                ("crm_target_id", "in", self.ids),
            ])
            for linked_target in linked_targets:
                if linked_target.origin_type != "manual":
                    linked_target.unlink()
                else:
                    linked_target.write({"crm_target_id": False})
        result = super().unlink()
        if keys:
            self._invalidate_quarterly_target_values(keys)
            self.env["crm.commission.quarterly.bonus"].sudo()._sync_for_keys(keys)
        return result

    def _get_quarter_bounds(self):
        self.ensure_one()
        if not self.target_date:
            return False, False
        quarter_start_month = ((self.target_date.month - 1) // 3) * 3 + 1
        date_from = self.target_date.replace(month=quarter_start_month, day=1)
        date_to = date_from + relativedelta(months=3, days=-1)
        return date_from, date_to

    def _get_quarterly_bonus_keys(self):
        keys = set()
        for target in self:
            if target.target_scope != "salesperson" or not target.agent_id:
                continue
            quarter = f"Q{(target.target_date.month - 1) // 3 + 1}"
            keys.add((target.agent_id.id, target.target_date.year, quarter))
        return keys

    def _invalidate_quarterly_target_values(self, keys, refresh_achieved=False):
        """Invalidate stored aggregates whenever a monthly target changes."""
        if not keys:
            return
        target_model = self.sudo().with_context(active_test=False)
        key_domains = []
        for agent_id, year, quarter in sorted(keys):
            if not quarter or quarter not in {"Q1", "Q2", "Q3", "Q4"}:
                continue
            first_month = (int(quarter[1:]) - 1) * 3 + 1
            date_from = fields.Date.from_string(f"{year}-{first_month:02d}-01")
            date_to = date_from + relativedelta(months=3, days=-1)
            key_domains.append([
                ("agent_id", "=", agent_id),
                ("target_date", ">=", date_from),
                ("target_date", "<=", date_to),
            ])
        if not key_domains:
            return
        domain = [("target_scope", "=", "salesperson")] + expression.OR(key_domains)
        targets = target_model.search(domain)
        if refresh_achieved:
            targets.invalidate_recordset(["achieved_amount"])
        targets.modified(["target_date", "agent_id"])

    def _refresh_from_sale_changes(self):
        """Refresh monthly achievements and already finalized bonus totals."""
        keys = self._get_quarterly_bonus_keys()
        if not keys:
            return
        self._invalidate_quarterly_target_values(keys, refresh_achieved=True)
        self.env["commission.target"].sudo()._sync_from_crm_targets(self)
        bonuses = self.env["crm.commission.quarterly.bonus"].sudo().search([
            ("agent_id", "in", self.agent_id.ids),
            ("is_finalized", "=", True),
        ])
        bonuses.modified(["monthly_targets"])
        bonuses._finalize_if_closed()

    @api.model
    def _sync_all_legacy_targets(self):
        """Backfill/refresh the targets consumed by commission calculations."""
        targets = self.sudo().search([("target_scope", "=", "salesperson")])
        targets_without_company = targets.filtered(lambda target: not target.company_id)
        if targets_without_company:
            targets_without_company.write({"company_id": self.env.company.id})
        legacy_targets = self.env["commission.target"].sudo()._sync_from_crm_targets(
            targets
        )
        self._sync_settlement_line_targets()
        return legacy_targets

    def _sync_settlement_line_targets(self):
        """Link existing CRM performance settlement lines to their source target."""
        lines = self.env["commission.settlement.line"].sudo().search([
            ("target_id", "=", False),
            ("settlement_id.settlement_type", "=", "crm_performance"),
        ])
        if not lines:
            return
        targets = self.sudo().search([
            ("target_scope", "=", "salesperson"),
            ("agent_id", "in", lines.mapped("settlement_id.agent_id").ids),
        ])
        targets_by_key = {
            (target.agent_id.id, target.target_date): target for target in targets
        }
        for line in lines:
            key = (line.settlement_id.agent_id.id, line.date)
            target = targets_by_key.get(key)
            if target:
                line.target_id = target.id

    @api.model
    def _sync_all_quarterly_bonuses(self):
        """Backfill/refresh every automatically managed quarterly record."""
        targets = self.sudo().search([("target_scope", "=", "salesperson")])
        targets.invalidate_recordset(["achieved_amount"])
        targets.modified(["target_date", "agent_id"])
        keys = targets._get_quarterly_bonus_keys()
        manual_keys = (
            self.env["crm.commission.quarterly.bonus"]
            .sudo()
            .search([("monthly_targets", "=", False)])
            ._get_quarterly_bonus_keys()
        )
        return self.env["crm.commission.quarterly.bonus"].sudo()._sync_for_keys(
            keys | manual_keys
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
            if not rec.agent_id or not rec.target_date:
                continue
            period_code = rec.target_date.strftime("%Y-%m")
            members = self.env["commission.member"].sudo().search([
                ("partner_id", "=", rec.agent_id.id),
                ("member_type", "=", "orientadora"),
            ])
            sales = self.env["commission.sale"].sudo().search([
                ("owner_member_id", "in", members.ids),
                ("period_code", "=", period_code),
                ("status", "in", ("confirmed", "invoiced")),
            ])
            if sales:
                rec.achieved_amount = sum(sales.mapped("hospital_gross_amount"))
                continue
            month_start = rec.target_date.replace(day=1)
            next_month = month_start + relativedelta(months=1)
            agent_domain = expression.OR([
                [("partner_id.agent_ids", "=", rec.agent_id.id)],
                [("order_line.agent_ids.agent_id", "=", rec.agent_id.id)],
            ])
            orders = self.env["sale.order"].search(
                agent_domain
                + [
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

    @api.depends("performance_pct", "target_date")
    def _compute_state(self):
        current_month = fields.Date.context_today(self).replace(day=1)
        for rec in self:
            if rec.performance_pct >= 100:
                rec.state = "achieved"
            elif rec.target_date and rec.target_date < current_month:
                rec.state = "lost"
            elif rec.performance_pct > 0:
                rec.state = "in_progress"
            else:
                rec.state = "draft"

    def _skip_settlement(self):
        """Return whether this target already has an active settlement line."""
        self.ensure_one()
        return bool(
            self.env["commission.settlement.line"].search_count([
                ("settlement_id.settlement_type", "=", "crm_performance"),
                ("settlement_id.state", "!=", "cancel"),
                "|",
                ("target_id", "=", self.id),
                "&",
                ("target_id", "=", False),
                ("settlement_id.agent_id", "=", self.agent_id.id),
                ("date", "=", self.target_date),
            ])
        )

    @api.constrains("target_scope", "agent_id", "team_id")
    def _check_target_scope(self):
        for rec in self:
            if rec.target_scope == "salesperson" and not rec.agent_id:
                raise ValidationError(
                    _("Selecione o/a vendedor(a) para a meta individual.")
                )
            if rec.target_scope == "team" and not rec.team_id:
                raise ValidationError(
                    _("Selecione a equipe de vendas para aplicar a meta coletiva.")
                )

    def _get_team_orientadora_partners(self):
        """Vendedores(as) (orientadoras) que são membros da equipe."""
        self.ensure_one()
        users = self.team_id.crm_team_member_ids.user_id
        return users.partner_id.filtered(
            lambda p: p.type_partner == "orientadora"
        )

    def action_apply_team(self):
        """Aplica a meta a todos os vendedores (orientadoras) da equipe.

        Cria um crm.commission.target individual por orientadora da equipe com
        os mesmos mês/valor/IS-CRM digitados (pulando quem já tem meta no mês)
        e remove o registro temporário de equipe.
        """
        self.ensure_one()
        if self.target_scope != "team":
            raise UserError(
                _("Esta ação só se aplica a metas no modo 'Equipe de Vendas'.")
            )
        partners = self._get_team_orientadora_partners()
        if not partners:
            raise UserError(
                _("Nenhum/a vendedor(a) (orientadora) encontrado/a na equipe "
                  "selecionada.")
            )
        existing = self.env["crm.commission.target"].search([
            ("target_date", "=", self.target_date),
            ("agent_id", "in", partners.ids),
        ])
        existing_agent_ids = set(existing.mapped("agent_id.id"))

        created = self.env["crm.commission.target"]
        for partner in partners:
            if partner.id in existing_agent_ids:
                continue
            created |= self.env["crm.commission.target"].create({
                "target_scope": "salesperson",
                "agent_id": partner.id,
                "team_id": self.team_id.id,
                "target_date": self.target_date,
                "target_amount": self.target_amount,
                "is_crm_score": self.is_crm_score,
                "currency_id": self.currency_id.id,
            })

        target_date = self.target_date
        partner_ids = partners.ids
        self.unlink()

        action = self.env["ir.actions.act_window"]._for_xml_id(
            "crm_commissions.action_crm_commission_target"
        )
        action["domain"] = [
            ("agent_id", "in", partner_ids),
            ("target_date", "=", target_date),
        ]
        return action


class CommissionQuarterlyBonus(models.Model):
    _name = "crm.commission.quarterly.bonus"
    _description = "Quarterly commission bonus/recovery"
    _order = "year desc, quarter desc, agent_id"

    _sql_constraints = [
        (
            "unique_agent_quarter",
            "UNIQUE (agent_id, year, quarter)",
            "Já existe um bônus trimestral para esta vendedora neste trimestre.",
        ),
    ]

    name = fields.Char(compute="_compute_name", store=True)
    agent_id = fields.Many2one(
        "res.partner",
        string="Agent",
        required=True,
    )
    team_id = fields.Many2one(
        "crm.team",
        string="Sales team",
    )
    quarter = fields.Char(required=True)
    year = fields.Integer(required=True)
    date_from = fields.Date(
        string="Quarter start",
        compute="_compute_quarter_dates",
        store=True,
    )
    date_to = fields.Date(
        string="Quarter end",
        compute="_compute_quarter_dates",
        store=True,
    )
    monthly_targets = fields.Many2many(
        "crm.commission.target",
        string="Monthly targets",
        readonly=True,
    )
    auto_generated = fields.Boolean(
        string="Automatically generated",
        default=False,
        readonly=True,
    )
    target_count = fields.Integer(
        string="Monthly goals",
        compute="_compute_totals",
        store=True,
    )
    has_all_months = fields.Boolean(
        string="All quarterly goals present",
        compute="_compute_totals",
        store=True,
    )
    missing_months = fields.Char(
        string="Missing months",
        compute="_compute_totals",
        store=True,
    )
    total_target = fields.Monetary(
        string="Total quarterly target",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
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
    is_finalized = fields.Boolean(
        string="Quarter finalized",
        default=False,
        readonly=True,
    )
    is_eligible = fields.Boolean(
        string="Individual eligible",
        compute="_compute_totals",
        store=True,
    )
    team_total_target = fields.Monetary(
        string="Team target",
        currency_field="currency_id",
        compute="_compute_team_totals",
        store=True,
    )
    team_total_achieved = fields.Monetary(
        string="Team achieved",
        currency_field="currency_id",
        compute="_compute_team_totals",
        store=True,
    )
    team_quarterly_pct = fields.Float(
        string="Team performance (%)",
        compute="_compute_team_totals",
        store=True,
    )
    is_team_eligible = fields.Boolean(
        string="Team/coordinator eligible",
        compute="_compute_team_totals",
        store=True,
    )
    lost_commission_recovered = fields.Monetary(
        string="Lost commission recovered",
        currency_field="currency_id",
        compute="_compute_recovery",
        store=True,
    )
    bonus_amount = fields.Monetary(
        string="Special bonus amount",
        currency_field="currency_id",
        help=(
            "O prêmio especial não possui fórmula na política; preencha após a "
            "decisão da equipe."
        ),
    )
    prize_type = fields.Selection(
        selection=[
            ("raffle", "Sorteio"),
            ("celebration", "Celebração coletiva"),
            ("other", "Outro"),
        ],
        string="Prize type",
    )
    prize_description = fields.Char(string="Prize description")
    state = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("incomplete", "Incomplete goals"),
            ("eligible", "Eligible"),
            ("recovered", "Recovered/Paid"),
            ("lost", "Lost"),
        ],
        default="pending",
        readonly=True,
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

    @api.depends("quarter", "year")
    def _compute_quarter_dates(self):
        for rec in self:
            if rec.quarter not in {"Q1", "Q2", "Q3", "Q4"} or not rec.year:
                rec.date_from = False
                rec.date_to = False
                continue
            first_month = (int(rec.quarter[1:]) - 1) * 3 + 1
            rec.date_from = fields.Date.from_string(f"{rec.year}-{first_month:02d}-01")
            rec.date_to = rec.date_from + relativedelta(months=3, days=-1)

    @api.depends(
        "monthly_targets",
        "monthly_targets.target_date",
        "monthly_targets.target_amount",
        "monthly_targets.achieved_amount",
        "is_finalized",
    )
    def _compute_totals(self):
        month_names = {
            1: "Jan",
            2: "Fev",
            3: "Mar",
            4: "Abr",
            5: "Mai",
            6: "Jun",
            7: "Jul",
            8: "Ago",
            9: "Set",
            10: "Out",
            11: "Nov",
            12: "Dez",
        }
        for rec in self:
            targets = rec.monthly_targets
            target_months = {
                target.target_date.month for target in targets if target.target_date
            }
            rec.target_count = len(targets)
            rec.has_all_months = len(target_months) == 3
            valid_quarter = rec.quarter in {"Q1", "Q2", "Q3", "Q4"}
            rec.missing_months = ", ".join(
                month_names[month]
                for month in range(1, 13)
                if month not in target_months
                and valid_quarter
                and (int(rec.quarter[1:]) - 1) * 3 + 1
                <= month
                <= int(rec.quarter[1:]) * 3
            )
            rec.total_target = sum(targets.mapped("target_amount"))
            rec.total_achieved = sum(targets.mapped("achieved_amount"))
            rec.quarterly_pct = (
                (rec.total_achieved / rec.total_target) * 100.0
                if rec.total_target
                else 0.0
            )
            rec.is_eligible = bool(
                rec.is_finalized
                and rec.has_all_months
                and rec.total_target
                and rec.total_achieved >= rec.total_target
            )

    @api.depends(
        "team_id",
        "agent_id",
        "date_from",
        "date_to",
        "monthly_targets",
        "is_finalized",
    )
    def _compute_team_totals(self):
        for rec in self:
            team = rec.team_id or rec.agent_id.crm_team_id
            if not team and rec.agent_id:
                team = self.env["crm.team"].search([
                    ("crm_team_member_ids.user_id.partner_id", "=", rec.agent_id.id),
                ], limit=1)
            if not team or not rec.date_from or not rec.date_to:
                rec.team_total_target = 0.0
                rec.team_total_achieved = 0.0
                rec.team_quarterly_pct = 0.0
                rec.is_team_eligible = False
                continue
            agent_ids = team.crm_team_member_ids.user_id.partner_id.filtered(
                lambda partner: partner.type_partner == "orientadora"
            ).ids
            if rec.agent_id.id not in agent_ids:
                agent_ids.append(rec.agent_id.id)
            targets = self.env["crm.commission.target"].sudo().search([
                ("target_scope", "=", "salesperson"),
                ("agent_id", "in", agent_ids),
                ("target_date", ">=", rec.date_from),
                ("target_date", "<=", rec.date_to),
            ])
            rec.team_total_target = sum(targets.mapped("target_amount"))
            rec.team_total_achieved = sum(targets.mapped("achieved_amount"))
            rec.team_quarterly_pct = (
                (rec.team_total_achieved / rec.team_total_target) * 100.0
                if rec.team_total_target
                else 0.0
            )
            target_months = {
                target.target_date.month for target in targets if target.target_date
            }
            rec.is_team_eligible = bool(
                rec.is_finalized
                and len(target_months) == 3
                and rec.team_total_target
                and rec.team_total_achieved >= rec.team_total_target
            )

    @api.depends(
        "monthly_targets",
        "monthly_targets.agent_id",
        "monthly_targets.target_date",
        "monthly_targets.performance_pct",
        "monthly_targets.target_amount",
        "monthly_targets.achieved_amount",
        "date_from",
        "date_to",
        "is_finalized",
    )
    def _compute_recovery(self):
        for rec in self:
            if not (
                rec.is_finalized
                and rec.has_all_months
                and rec.total_target
                and rec.total_achieved >= rec.total_target
            ):
                rec.lost_commission_recovered = 0.0
                continue
            rec.lost_commission_recovered = rec._calculate_lost_commission()

    def _get_quarterly_bonus_keys(self):
        keys = set()
        for bonus in self:
            if (
                bonus.agent_id
                and bonus.quarter in {"Q1", "Q2", "Q3", "Q4"}
                and bonus.year
            ):
                keys.add((bonus.agent_id.id, bonus.year, bonus.quarter))
        return keys

    @api.model
    def _sync_for_keys(self, keys):
        """Create or refresh exactly one bonus per salesperson and quarter."""
        target_model = self.env["crm.commission.target"].sudo()
        for agent_id, year, quarter in sorted(keys):
            if quarter not in {"Q1", "Q2", "Q3", "Q4"}:
                continue
            first_month = (int(quarter[1:]) - 1) * 3 + 1
            date_from = fields.Date.from_string(f"{year}-{first_month:02d}-01")
            date_to = date_from + relativedelta(months=3, days=-1)
            targets = target_model.search([
                ("target_scope", "=", "salesperson"),
                ("agent_id", "=", agent_id),
                ("target_date", ">=", date_from),
                ("target_date", "<=", date_to),
            ], order="target_date")
            bonuses = self.search([
                ("agent_id", "=", agent_id),
                ("year", "=", year),
                ("quarter", "=", quarter),
            ], order="id")
            bonus = bonuses[:1]
            duplicates = bonuses[1:]
            if duplicates and duplicates.filtered(
                lambda item: item.auto_generated and not item.is_finalized
            ):
                duplicates.filtered(
                    lambda item: item.auto_generated and not item.is_finalized
                ).unlink()
            if not targets:
                if bonus and bonus.auto_generated and not bonus.is_finalized:
                    bonus.unlink()
                continue
            team = targets[:1].team_id or targets.agent_id[:1].crm_team_id
            values = {
                "monthly_targets": [(6, 0, targets.ids)],
                "team_id": team.id,
                "currency_id": targets[:1].currency_id.id,
            }
            if bonus:
                bonus.write(values)
            else:
                bonus = self.create({
                    **values,
                    "agent_id": agent_id,
                    "year": year,
                    "quarter": quarter,
                    "auto_generated": True,
                })
            bonus._finalize_if_closed()

    def _get_rate_for_performance(self, performance_pct):
        self.ensure_one()
        date_from = self.date_from or fields.Date.context_today(self)
        date_to = self.date_to or fields.Date.context_today(self)
        policy = self.env["commission.policy"].sudo().search(
            [
                ("active", "=", True),
                ("date_start", "<=", date_to),
            ]
            + expression.OR([
                [("date_end", "=", False)],
                [("date_end", ">=", date_from)],
            ]),
            order="date_start desc",
            limit=1,
        )
        if policy:
            line = self._select_rate_line(
                policy.line_ids.sorted(key=lambda item: item.sequence),
                performance_pct,
                "delivery_pct_from",
                "delivery_pct_to",
            )
            return line.base_rate if line else 0.0
        commission = self.agent_id.commission_id
        if commission:
            line = self._select_rate_line(
                commission.progressive_line_ids.sorted(key=lambda item: item.sequence),
                performance_pct,
                "percent_from",
                "percent_to",
            )
            return line.commission_percent if line else 0.0
        return 0.0

    @api.model
    def _select_rate_line(self, lines, performance_pct, from_field, to_field):
        for line in lines:
            if line[from_field] <= performance_pct <= line[to_field]:
                return line
        for line in lines:
            if performance_pct < line[from_field]:
                return line
        return lines[-1] if lines else False

    def _get_monthly_commission_base(self, target):
        self.ensure_one()
        members = self.env["commission.member"].sudo().search([
            ("partner_id", "=", target.agent_id.id),
            ("member_type", "=", "orientadora"),
        ])
        sales = self.env["commission.sale"].sudo().search([
            ("owner_member_id", "in", members.ids),
            ("period_code", "=", target.target_date.strftime("%Y-%m")),
            ("status", "in", ("confirmed", "invoiced")),
        ])
        total = 0.0
        for sale in sales:
            if sale.is_lens_sale:
                lens_rate = sale._get_lens_rate()
                if lens_rate:
                    total += sale._get_commissionable_amount() * lens_rate / 100.0
            else:
                total += sale._get_commissionable_amount()
        return total

    def _calculate_lost_commission(self):
        self.ensure_one()
        reference_rate = self._get_rate_for_performance(100.0)
        recovery = 0.0
        for target in self.monthly_targets.filtered(
            lambda item: item.performance_pct < 100.0
        ):
            actual_rate = self._get_rate_for_performance(target.performance_pct)
            lost_rate = max(0.0, reference_rate - actual_rate)
            if not lost_rate:
                continue
            commission_base = self._get_monthly_commission_base(target)
            recovery += commission_base * lost_rate / 100.0
        return recovery

    def _finalize_if_closed(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.date_to or today <= rec.date_to:
                continue
            targets = rec.monthly_targets
            target_months = {
                target.target_date.month for target in targets if target.target_date
            }
            total_target = sum(targets.mapped("target_amount"))
            total_achieved = sum(targets.mapped("achieved_amount"))
            rec.is_finalized = True
            if len(target_months) != 3:
                rec.state = "incomplete"
            elif total_target and total_achieved >= total_target:
                rec.state = (
                    "recovered" if rec._calculate_lost_commission() > 0 else "eligible"
                )
            else:
                rec.state = "lost"

    def action_finalize_quarter(self):
        self._finalize_if_closed()
        return True

    @api.model
    def _cron_sync_and_finalize_quarterly_bonuses(self):
        targets = self.env["crm.commission.target"]
        targets._sync_all_quarterly_bonuses()
        targets._sync_all_legacy_targets()
        today = fields.Date.context_today(self)
        bonuses = self.search([("date_to", "<", today)])
        bonuses.modified(["monthly_targets"])
        bonuses._finalize_if_closed()
        return True

    @api.constrains("quarter", "year")
    def _check_quarter(self):
        for rec in self:
            if rec.quarter not in {"Q1", "Q2", "Q3", "Q4"}:
                raise ValidationError(_("O trimestre deve ser Q1, Q2, Q3 ou Q4."))
            if not rec.year or rec.year < 2000:
                raise ValidationError(_("Informe um ano válido para o trimestre."))


class CommissionAgentRule(models.Model):
    _name = "commission.agent.rule"
    _description = "Commission rule per agent and product category"
    _order = "sequence, id"
    _rec_name = "agent_id"

    agent_id = fields.Many2one(
        "res.partner",
        string="Agent",
        domain=[("agent", "=", True)],
        required=True,
    )
    commission_id = fields.Many2one(
        "commission",
        string="Commission",
        required=True,
    )
    categ_ids = fields.Many2many(
        "product.category",
        string="Categories",
        required=True,
        help="Product categories that trigger this commission rule for this agent.",
    )
    sequence = fields.Integer(
        default=10,
        help="Lower sequence = higher priority when multiple rules match.",
    )
