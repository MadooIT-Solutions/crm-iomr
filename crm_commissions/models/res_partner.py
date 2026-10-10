# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    MEDICAL_AGENT_TYPES = ("doctorint", "doctorext")

    type_partner = fields.Selection(
        selection_add=[
            ("orientadora", "Orientador(a)"),
            ("sdr", "SDR (Pré-orientador(a))"),
            ("coordenadora", "Coordenador(a)"),
        ],
        ondelete={
            "orientadora": "set default",
            "sdr": "set default",
            "coordenadora": "set default",
        },
    )
    agent_type = fields.Selection(
        selection_add=[
            ("orientadora", "Orientador(a)"),
            ("sdr", "SDR"),
            ("coordenadora", "Coordenador(a)"),
            ("doctor", "Médico(a)"),
        ],
        ondelete={
            "orientadora": "set default",
            "sdr": "set default",
            "coordenadora": "set default",
            "doctor": "set default",
        },
    )
    crm_team_id = fields.Many2one(
        "crm.team",
        string="Sales team",
    )
    target_ids = fields.One2many(
        "crm.commission.target",
        inverse_name="agent_id",
        string="Monthly targets",
    )
    quarterly_bonus_ids = fields.One2many(
        "crm.commission.quarterly.bonus",
        inverse_name="agent_id",
        string="Quarterly bonuses",
    )
    sdr_agent_ids = fields.Many2many(
        "res.partner",
        relation="orientadora_sdr_rel",
        column1="orientadora_id",
        column2="sdr_id",
        string="Linked SDRs",
        domain=[("type_partner", "=", "sdr")],
    )
    coordenadora_id = fields.Many2one(
        "res.partner",
        string="Coordenador(a)",
        compute="_compute_coordenadora_id",
        store=True,
        readonly=False,
        precompute=True,
        help="Líder da equipe de vendas da orientador(a). Vem automaticamente "
        "do crm_team.user_id (Team Leader) da equipe do contato "
        "(crm_team_id). Pode ser ajustado à mão quando a orientador(a) não "
        "segue a equipe padrão.",
    )
    is_crm_target = fields.Float(
        string="IS-CRM target (%)",
        default=95.0,
    )
    agent_rule_ids = fields.One2many(
        "commission.agent.rule",
        inverse_name="agent_id",
        string="Commission rules per category",
        help="Specific commission rules for this agent based on product "
        "category. When a sale order line matches a category, this commission "
        "is used instead of the default.",
    )
    show_repasse_table = fields.Boolean(
        string="Ver Tabela de Repasses",
        help="Se marcado, o médico pode visualizar a Tabela de Repasses no portal.",
    )
    show_all_values = fields.Boolean(
        string="Ver todos os valores",
        help="Se marcado, o médico pode visualizar todos os valores "
        "(Expectativa, Repasse e Valor) no portal.",
    )

    def is_medical_agent(self):
        """Whether this partner is a doctor.

        Doctors are the only profile allowed to commission HONORARIO and
        PROCEDIMENTO categories, and the only one that reaches those lines
        through the order's ``doctor_id`` / ``referred_partner``.
        """
        return self.type_partner in self.MEDICAL_AGENT_TYPES

    @api.depends("crm_team_id", "crm_team_id.user_id", "type_partner")
    def _compute_coordenadora_id(self):
        """A coordenadora é a líder da equipe de vendas da orientadora.

        Regra padrão da clínica: cada orientadora pertence a uma equipe
        (``crm_team_id``) e quem lidera essa equipe (``crm_team.user_id``)
        coordena sua equipe, recebendo o repasse de coordenador. Assim o
        vínculo se mantém sozinho quando a equipe muda de líder.

        Só orientador(a)s entram aqui. Nos demais tipos o campo é apenas
        preservado, para não apagar um valor preenchido à mão por engano.
        """
        for partner in self:
            if partner.type_partner != "orientadora":
                # Preserva o valor já gravado (inclusive um ajuste manual) nos
                # demais tipos: sem atribuição, o ORM gravaria False por cima.
                partner.coordenadora_id = partner.coordenadora_id
                continue
            leader = partner.crm_team_id.user_id.partner_id if partner.crm_team_id else False
            partner.coordenadora_id = leader

    @api.onchange("type_partner")
    def _onchange_type_partner(self):
        if self.type_partner == "orientadora":
            self.agent = True
            if not self.agent_type or self.agent_type == "agent":
                self.agent_type = "orientadora"
        elif self.type_partner == "sdr":
            self.agent = True
            self.agent_type = "sdr"
        elif self.type_partner == "coordenadora":
            self.agent = True
            self.agent_type = "coordenadora"
        elif self.type_partner in ("doctorint", "doctorext"):
            self.agent = True
            self.agent_type = "doctor"

    def write(self, vals):
        result = super().write(vals)
        if "crm_team_id" in vals and not self.env.context.get(
            "crm_commissions_skip_member_team_sync"
        ):
            members = (
                self.env["commission.member"]
                .sudo()
                .search(
                    [
                        ("partner_id", "in", self.ids),
                        ("team_id", "=", False),
                    ]
                )
            )
            members._sync_team_from_partner()
        return result
