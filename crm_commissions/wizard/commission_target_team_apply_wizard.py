# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CommissionTargetTeamApply(models.TransientModel):
    _name = "crm.commission.target.team.apply"
    _description = "Confirm monthly target application to a sales team"

    target_id = fields.Many2one(
        "crm.commission.target",
        string="Meta da equipe",
        required=True,
        readonly=True,
    )
    team_name = fields.Char(related="target_id.team_id.name", readonly=True)
    month = fields.Date(related="target_id.target_date", readonly=True)
    team_amount = fields.Monetary(
        related="target_id.target_amount",
        currency_field="currency_id",
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="target_id.currency_id",
        readonly=True,
    )
    split_team_target = fields.Boolean(
        related="target_id.split_team_target",
        readonly=True,
    )
    conflict_ids = fields.Many2many(
        "res.partner",
        string="Já possuem meta no mês",
        readonly=True,
    )
    conflict_names = fields.Char(
        string="Pessoas com meta existente",
        compute="_compute_conflict_names",
    )
    apply_mode = fields.Selection(
        selection=[
            ("keep", "Manter as metas existentes"),
            ("replace", "Substituir pelas metas da equipe"),
        ],
        string="Para as metas já existentes",
        default="keep",
        required=True,
    )

    @api.depends("conflict_ids")
    def _compute_conflict_names(self):
        for rec in self:
            rec.conflict_names = ", ".join(
                rec.conflict_ids.sorted("name").mapped("name")
            )

    def action_open_wizard(self):
        """Abre a confirmação pedindo o que fazer com as metas já existentes."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Aplicar meta à equipe"),
            "res_model": self._name,
            "res_id": self.id,
            "views": [(False, "form")],
            "view_mode": "form",
            "target": "new",
            "context": dict(
                self.env.context,
                default_target_id=self.target_id.id,
                default_apply_mode=self.apply_mode,
            ),
        }

    def _prepare_summary(self):
        self.ensure_one()
        month = fields.Date.to_string(self.month)
        if self.split_team_target:
            amount_label = _("o total da equipe, dividido igualmente")
        else:
            amount_label = _("o valor integral")
        if self.apply_mode == "replace":
            detail = _(
                "As metas existentes serão substituídas. As %(count)d pessoa(s) "
                "listadas e as demais da equipe recebem %(amount)s de "
                "%(total)s.",
                count=len(self.conflict_ids),
                amount=amount_label,
                total=self.team_amount,
            )
        else:
            detail = _(
                "As metas existentes serão mantidas como estão. As demais "
                "pessoas da equipe recebem %(amount)s de %(total)s.",
                amount=amount_label,
                total=self.team_amount,
            )
        return _(
            "A meta de %(total)s de %(month)s será aplicada à equipe "
            "%(team)s.\n"
            "Estas pessoas já possuem meta em %(month)s: %(names)s.\n\n"
            "%(detail)s",
            total=self.team_amount,
            month=month,
            team=self.team_name or "-",
            names=self.conflict_names or "-",
            detail=detail,
        )

    def action_confirm(self):
        """Confirma e aplica a meta conforme a escolha feita na tela."""
        self.ensure_one()
        target = self.target_id
        if not target.exists():
            raise UserError(_("A meta da equipe não existe mais."))
        return target.with_context(
            crm_commissions_team_apply_confirmed=self.apply_mode
        ).action_apply_team()

    def action_cancel(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window_close"}
