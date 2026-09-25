from odoo import api, fields, models


class CommissionMember(models.Model):
    _name = "commission.member"
    _description = "Commission Team Member"
    _order = "name"

    name = fields.Char(required=True)
    member_type = fields.Selection(
        [
            ("orientadora", "Orientadora"),
            ("sdr", "SDR"),
            ("coordenadora", "Coordenadora"),
        ],
        required=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Related Contact",
        domain=[("type_partner", "in", ("orientadora", "sdr", "coordenadora"))],
        required=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="User",
        compute="_compute_user_id",
        inverse="_inverse_user_id",
        search="_search_user_id",
    )
    active = fields.Boolean(default=True)
    color = fields.Integer()
    team_id = fields.Many2one("crm.team", string="Equipe de Vendas")
    sdr_ids = fields.Many2many(
        "commission.member",
        "commission_member_sdr_rel",
        "orientadora_id",
        "sdr_id",
        string="Linked SDRs",
        domain=[("member_type", "=", "sdr")],
    )
    orientadora_id = fields.Many2one(
        "commission.member",
        string="Orientadora",
        domain=[("member_type", "=", "orientadora")],
    )
    target_ids = fields.One2many(
        "commission.target",
        "member_id",
        string="Targets",
    )
    result_ids = fields.One2many(
        "commission.result",
        "member_id",
        string="Results",
    )

    @api.depends("partner_id")
    def _compute_user_id(self):
        for rec in self:
            if rec.partner_id:
                user = self.env["res.users"].search(
                    [("partner_id", "=", rec.partner_id.id)], limit=1
                )
                rec.user_id = user
            else:
                rec.user_id = False

    def _inverse_user_id(self):
        for rec in self:
            if rec.user_id:
                rec.partner_id = rec.user_id.partner_id

    def _search_user_id(self, operator, value):
        partners = (
            self.env["res.users"]
            .search([("partner_id", operator, value)])
            .mapped("partner_id.id")
        )
        return [("partner_id", "in", partners)]

    @api.model
    def _sync_crm_targets_for_partners(self, partners):
        """Synchronize monthly targets after a member link changes."""
        if not partners:
            return self.browse()
        targets = (
            self.env["crm.commission.target"]
            .sudo()
            .search(
                [
                    ("target_scope", "=", "salesperson"),
                    ("agent_id", "in", partners.ids),
                ]
            )
        )
        return self.env["commission.target"].sudo()._sync_from_crm_targets(targets)

    def _sync_team_from_partner(self):
        """Fill the sales team from the related contact when it is missing.

        The team is maintained on the contact (``res.partner.crm_team_id``), so
        members created by other means (imports, sync, manual creation) end up
        without any team. Values already informed by hand are preserved.
        """
        to_sync = self.filtered(
            lambda member: not member.team_id and member.partner_id.crm_team_id
        )
        if not to_sync:
            return
        member_ids_by_team = {}
        for member in to_sync:
            team_id = member.partner_id.crm_team_id.id
            member_ids_by_team.setdefault(team_id, []).append(member.id)
        members_model = self.with_context(crm_commissions_skip_member_team_sync=True)
        for team_id, member_ids in member_ids_by_team.items():
            members_model.browse(member_ids).write({"team_id": team_id})

    @api.model_create_multi
    def create(self, vals_list):
        members = super().create(vals_list)
        if not self.env.context.get("crm_commissions_skip_member_team_sync"):
            members._sync_team_from_partner()
        members._sync_crm_targets_for_partners(members.mapped("partner_id"))
        return members

    def write(self, vals):
        old_partners = self.mapped("partner_id")
        result = super().write(vals)
        if not self.env.context.get("crm_commissions_skip_member_team_sync"):
            self._sync_team_from_partner()
        if {"partner_id", "member_type", "active"}.intersection(vals):
            partners = old_partners | self.mapped("partner_id")
            self._sync_crm_targets_for_partners(partners)
        return result

    def unlink(self):
        partners = self.mapped("partner_id")
        linked_targets = (
            self.env["commission.target"]
            .sudo()
            .search(
                [
                    ("member_id", "in", self.ids),
                    ("crm_target_id", "!=", False),
                ]
            )
        )
        linked_targets.unlink()
        result = super().unlink()
        self._sync_crm_targets_for_partners(partners)
        return result
