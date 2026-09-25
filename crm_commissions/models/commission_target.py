import logging

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
        default="manual",
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
        linked_targets = legacy_model.search([
            ("crm_target_id", "in", crm_targets.ids),
        ])
        linked_by_crm_id = {
            target.crm_target_id.id: target for target in linked_targets
        }

        members = (
            self.env["commission.member"]
            .sudo()
            .with_context(active_test=False)
            .search([
                ("partner_id", "in", crm_targets.agent_id.ids),
                ("member_type", "=", "orientadora"),
            ])
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
            if linked_target:
                if linked_target.origin_type == "manual":
                    _logger.warning(
                        "CRM target %s is linked to a manual commission target; "
                        "the manual target was not overwritten",
                        crm_target.id,
                    )
                    continue
            else:
                candidates = legacy_model.search([
                    ("member_id", "=", member.id),
                    ("year", "=", values["year"]),
                    ("month", "=", values["month"]),
                    ("crm_target_id", "=", False),
                ], order="id")
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
                        crm_target.id,
                    )
                    continue
                if len(auto_candidates) > 1:
                    _logger.warning(
                        "CRM target %s has multiple automatic commission targets "
                        "for the same period; resolve the duplicates first",
                        crm_target.id,
                    )
                    continue
                linked_target = auto_candidates[:1]
            if linked_target:
                changed_values = {}
                for name, value in values.items():
                    current_value = linked_target[name]
                    if linked_target._fields[name].type == "many2one":
                        current_value = current_value.id
                    if current_value != value:
                        changed_values[name] = value
                if changed_values:
                    linked_target.write(changed_values)
            else:
                linked_target = legacy_model.create(values)
            synced_targets |= linked_target

        return synced_targets
