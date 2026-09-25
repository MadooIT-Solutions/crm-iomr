import logging
from datetime import date

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class CommissionTarget(models.Model):
    _name = "commission.target"
    _description = "Commission Target"
    _order = "period_code desc"

    _sql_constraints = [
        (
            "crm_commissions_unique_target",
            "UNIQUE(crm_target_id)",
            "A meta automática deve estar vinculada a apenas uma meta mensal.",
        ),
    ]

    name = fields.Char(compute="_compute_name", store=True)
    member_id = fields.Many2one(
        "commission.member",
        string="Member",
        domain=[("member_type", "=", "orientadora")],
        required=True,
    )
    crm_target_id = fields.Many2one(
        "crm.commission.target",
        string="Monthly CRM target",
        index=True,
        copy=False,
        readonly=True,
        ondelete="set null",
    )
    year = fields.Integer(required=True)
    month = fields.Selection(
        [(str(i), str(i)) for i in range(1, 13)],
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
        default="manual",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("in_progress", "In Progress"),
            ("achieved", "Achieved"),
            ("lost", "Lost"),
        ],
        default="draft",
    )
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
    )
    # Fields below mirror "Metas Mensais" (crm.commission.target) so the legacy
    # menu shows the same indicators as the CRM one.
    target_date = fields.Date(
        string="Mês da Meta",
        compute="_compute_target_date",
        help="Mês de referência da meta (sempre o dia 1).",
    )
    quarter = fields.Char(
        string="Trimestre",
        compute="_compute_quarter",
    )
    team_id = fields.Many2one(
        "crm.team",
        string="Equipe de Vendas",
        compute="_compute_team_id",
    )
    achieved_amount = fields.Monetary(
        string="Atingido",
        currency_field="currency_id",
        compute="_compute_period_indicators",
    )
    performance_pct = fields.Float(
        string="Performance (%)",
        compute="_compute_period_indicators",
    )
    is_crm_score = fields.Float(
        string="IS-CRM (%)",
        compute="_compute_period_indicators",
    )
    is_crm_ok = fields.Boolean(
        string="IS-CRM OK",
        compute="_compute_period_indicators",
    )
    quarterly_target_amount = fields.Monetary(
        string="Meta Trimestral",
        currency_field="currency_id",
        compute="_compute_quarterly_target_amount",
    )

    @api.depends("crm_target_id", "crm_target_id.target_date", "year", "month")
    def _compute_target_date(self):
        for rec in self:
            if rec.crm_target_id:
                rec.target_date = rec.crm_target_id.target_date
            elif rec.year and rec.month:
                rec.target_date = date(int(rec.year), int(rec.month), 1)
            else:
                rec.target_date = False

    @api.depends("target_date")
    def _compute_quarter(self):
        for rec in self:
            if rec.target_date:
                month = rec.target_date.month
                rec.quarter = f"Q{(month - 1) // 3 + 1}/{rec.target_date.year}"
            else:
                rec.quarter = False

    @api.depends(
        "member_id",
        "member_id.team_id",
        "member_id.partner_id.crm_team_id",
    )
    def _compute_team_id(self):
        for rec in self:
            member = rec.member_id
            rec.team_id = member.team_id or member.partner_id.crm_team_id

    @api.depends(
        "crm_target_id",
        "crm_target_id.achieved_amount",
        "crm_target_id.performance_pct",
        "crm_target_id.is_crm_score",
        "member_id",
        "period_code",
        "individual_target_amount",
    )
    def _compute_period_indicators(self):
        """Atingido, performance e IS-CRM da meta do período."""
        sales_model = self.env["commission.sale"].sudo()
        for rec in self:
            if rec.crm_target_id:
                crm_target = rec.crm_target_id
                rec.achieved_amount = crm_target.achieved_amount
                rec.performance_pct = crm_target.performance_pct
                rec.is_crm_score = crm_target.is_crm_score
                rec.is_crm_ok = crm_target.is_crm_ok
                continue
            if not rec.member_id or not rec.period_code:
                rec.achieved_amount = 0.0
                rec.performance_pct = 0.0
                rec.is_crm_score = 100.0
                rec.is_crm_ok = True
                continue
            sales = sales_model.search(
                [
                    ("owner_member_id", "=", rec.member_id.id),
                    ("period_code", "=", rec.period_code),
                    ("status", "in", ("confirmed", "invoiced")),
                ]
            )
            scores = sales.mapped("crm_pct")
            rec.achieved_amount = sum(sales.mapped("hospital_gross_amount"))
            rec.performance_pct = (
                (rec.achieved_amount / rec.individual_target_amount) * 100.0
                if rec.individual_target_amount
                else 0.0
            )
            rec.is_crm_score = min(scores) if scores else 100.0
            rec.is_crm_ok = rec.is_crm_score >= 95.0

    @api.depends("member_id", "year", "month")
    def _compute_quarterly_target_amount(self):
        for rec in self:
            if not rec.member_id or not rec.year or not rec.month:
                rec.quarterly_target_amount = 0.0
                continue
            quarter_start = ((int(rec.month) - 1) // 3) * 3 + 1
            months = [str(value) for value in range(quarter_start, quarter_start + 3)]
            targets = self.search(
                [
                    ("member_id", "=", rec.member_id.id),
                    ("year", "=", rec.year),
                    ("month", "in", months),
                ]
            )
            rec.quarterly_target_amount = sum(
                targets.mapped("individual_target_amount")
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

    @api.model
    def _get_single_active_member_by_partner(self, partners):
        """Map each partner to its unique active orientadora member.

        Partners without exactly one active member are skipped and logged, as
        the legacy target cannot be linked to an ambiguous member.
        """
        members = (
            self.env["commission.member"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("partner_id", "in", partners.ids),
                    ("member_type", "=", "orientadora"),
                ]
            )
        )
        members_by_partner = {}
        for member in members:
            members_by_partner.setdefault(member.partner_id.id, []).append(member)
        member_by_partner = {}
        for partner_id, partner_members in members_by_partner.items():
            active_members = [member for member in partner_members if member.active]
            if len(active_members) == 1:
                member_by_partner[partner_id] = active_members[0]
                continue
            reason = "multiple active members" if active_members else "no active member"
            _logger.warning(
                "Cannot synchronize CRM target for partner %s: %s found",
                partner_id,
                reason,
            )
        return member_by_partner

    @api.model
    def _find_unlinked_target_for_period(self, member, values):
        """Return the automatic target of the period, or an empty recordset.

        ``False`` is returned when the period must not be synchronized, either
        because a manual target exists or because the automatic ones are
        duplicated and need a manual cleanup.
        """
        candidates = self.sudo().search(
            [
                ("member_id", "=", member.id),
                ("year", "=", values["year"]),
                ("month", "=", values["month"]),
                ("crm_target_id", "=", False),
            ],
            order="id",
        )
        manual_candidates = candidates.filtered(
            lambda target: target.origin_type == "manual"
        )
        auto_candidates = candidates.filtered(
            lambda target: target.origin_type != "manual"
        )
        if manual_candidates:
            _logger.warning(
                "CRM target %s has a manual commission target for the same "
                "period; no automatic projection was created",
                values["crm_target_id"],
            )
            return False
        if len(auto_candidates) > 1:
            _logger.warning(
                "CRM target %s has multiple automatic commission targets "
                "for the same period; resolve the duplicates first",
                values["crm_target_id"],
            )
            return False
        return auto_candidates[:1]

    @api.model
    def _apply_sync_values(self, target, values):
        """Write only the values that differ on the given target."""
        changed_values = {}
        for name, value in values.items():
            current_value = target[name]
            if target._fields[name].type == "many2one":
                current_value = current_value.id
            if current_value != value:
                changed_values[name] = value
        if changed_values:
            target.write(changed_values)
        return target

    @api.model
    def _sync_from_crm_targets(self, crm_targets):
        """Create/update the legacy targets used by commissions calculations.

        ``crm.commission.target`` is the source of truth for monthly targets.
        Legacy targets are kept only when the salesperson has a commission
        member, and are removed when that link is no longer valid.
        """
        crm_targets = crm_targets.exists().sudo()
        if not crm_targets:
            return self.browse()

        legacy_model = self.sudo()
        linked_targets = legacy_model.search(
            [
                ("crm_target_id", "in", crm_targets.ids),
            ]
        )
        linked_by_crm_id = {
            target.crm_target_id.id: target for target in linked_targets
        }
        member_by_partner = self._get_single_active_member_by_partner(
            crm_targets.agent_id
        )

        synced_targets = self.browse()
        for crm_target in crm_targets:
            linked_target = linked_by_crm_id.get(crm_target.id, legacy_model.browse())
            member = member_by_partner.get(crm_target.agent_id.id)
            if (
                crm_target.target_scope != "salesperson"
                or not crm_target.agent_id
                or not member
            ):
                if linked_target:
                    if linked_target.origin_type != "manual":
                        linked_target.unlink()
                    else:
                        linked_target.write({"crm_target_id": False})
                continue

            values = {
                "crm_target_id": crm_target.id,
                "member_id": member.id,
                "year": crm_target.target_date.year,
                "month": str(crm_target.target_date.month),
                "individual_target_amount": crm_target.target_amount,
                "currency_id": crm_target.currency_id.id,
                "origin_type": "auto",
                "state": crm_target.state or "draft",
            }
            if linked_target and linked_target.origin_type == "manual":
                _logger.warning(
                    "CRM target %s is linked to a manual commission target; "
                    "the manual target was not overwritten",
                    crm_target.id,
                )
                continue
            if not linked_target:
                candidate = self._find_unlinked_target_for_period(member, values)
                if candidate is False:
                    continue
                linked_target = candidate
            if linked_target:
                synced_targets |= self._apply_sync_values(linked_target, values)
            else:
                synced_targets |= legacy_model.create(values)

        return synced_targets
