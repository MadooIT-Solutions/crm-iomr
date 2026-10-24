# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from markupsafe import Markup

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
    commission_related_html = fields.Html(
        string="Comissões Relacionadas",
        compute="_compute_commission_related_html",
        sanitize=False,
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
        return self.type_partner in self.MEDICAL_AGENT_TYPES

    @api.depends("crm_team_id", "crm_team_id.user_id", "type_partner")
    def _compute_coordenadora_id(self):
        for partner in self:
            if partner.type_partner != "orientadora":
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

    def _compute_commission_related_html(self):
        commission_type_map = {"fixed": "Percentual fixo", "section": "Por faixas (seções)", "progressive": "Progressivo por desempenho", "coordinator": "Coordenador(a) via política"}
        base_type_map = {"gross_amount": "Valor de venda/fatura", "net_amount": "Margem (Valor - Custo)", "net_amount_deduction": "Líquido (Bruto - Impostos - Taxa cartão)"}
        for partner in self:
            rows = []
            if getattr(partner, "commission_id", False):
                comm = partner.commission_id
                rows.append({"origin": "Padrão (Comissionamento)", "commission": comm.name, "type": commission_type_map.get(comm.commission_type, comm.commission_type), "base": base_type_map.get(comm.amount_base_type, comm.amount_base_type), "details": self._format_commission_details(comm), "categories": ", ".join(comm.categ_ids.mapped("name")) or "Todas as categorias", "explanation": self._format_commission_explanation(comm)})
            for rule in partner.agent_rule_ids.sorted(key=lambda r: (r.sequence, r.id)):
                comm = rule.commission_id
                rows.append({"origin": "Regra por categoria (seq. %s)" % rule.sequence, "commission": comm.name, "type": commission_type_map.get(comm.commission_type, comm.commission_type), "base": base_type_map.get(comm.amount_base_type, comm.amount_base_type), "details": self._format_commission_details(comm), "categories": ", ".join(rule.categ_ids.mapped("name")) or "Todas as categorias", "explanation": self._format_commission_explanation(comm)})
            if not rows:
                partner.commission_related_html = "<p><em>Nenhuma comissão configurada para este representante.</em></p>"
                continue
            html = ['<table class="table table-sm table-striped" style="width:100%;">', '<thead><tr><th>Origem</th><th>Comissão</th><th>Tipo</th><th>Base de Cálculo</th><th>Detalhamento dos Cálculos</th><th>Categorias</th><th>Explicação</th></tr></thead><tbody>']
            for row in rows:
                html.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (row["origin"], row["commission"], row["type"], row["base"], row["details"], row["categories"], row["explanation"]))
            html.append('</tbody></table>')
            partner.commission_related_html = Markup(''.join(html))

    def _format_commission_details(self, comm):
        details = []
        if comm.commission_type == "fixed":
            details.append("Percentual fixo: %s%%" % comm.fix_qty)
        elif comm.commission_type == "section":
            if getattr(comm, "section_ids", False):
                for sec in comm.section_ids.sorted(key=lambda s: s.amount_from):
                    details.append("Faixa: de %s até %s = %s%%" % (sec.amount_from, sec.amount_to, sec.percent))
            else:
                details.append("Sem faixas configuradas")
        elif comm.commission_type == "progressive":
            if getattr(comm, "progressive_line_ids", False):
                for line in comm.progressive_line_ids.sorted(key=lambda l: l.sequence):
                    details.append("Desempenho %s%%-%s%% → %s%%" % (line.percent_from, line.percent_to, line.commission_percent))
            details.append("IS-CRM: >=95%% +%s%% | <95%% -%s%%" % (getattr(comm, "is_crm_bonus", 0), getattr(comm, "is_crm_penalty", 0)))
        elif comm.commission_type == "coordinator":
            details.append("Cálculo via política/coordenador")
        if getattr(comm, "deduct_taxes", False):
            details.append("Deduz impostos da linha")
        elif getattr(comm, "tax_deduction_pct", 0):
            details.append("Dedução impostos: %s%%" % comm.tax_deduction_pct)
        if getattr(comm, "deduct_card_fee", False):
            details.append("Deduz taxa de cartão")
        if getattr(comm, "min_margin", 0):
            details.append("Margem mínima: %s%%" % comm.min_margin)
        if getattr(comm, "max_discount", 0):
            details.append("Desconto máx. sem aprovação: %s%%" % comm.max_discount)
        return "<br/>".join(details) if details else "-"

    def _format_commission_explanation(self, comm):
        explanations = []
        base = comm.amount_base_type
        if base == "gross_amount":
            explanations.append("Base = valor bruto da venda/fatura.")
        elif base == "net_amount":
            explanations.append("Base = margem (valor - custo).")
        elif base == "net_amount_deduction":
            explanations.append("Base = líquido (preço - impostos - taxa cartão).")
        if comm.commission_type == "fixed":
            explanations.append("Aplica %s%% sobre a base." % comm.fix_qty)
        elif comm.commission_type == "section":
            explanations.append("Aplica alíquota conforme faixa de valor da base.")
        elif comm.commission_type == "progressive":
            explanations.append("Alíquota por faixa de desempenho + ajuste por IS-CRM.")
        elif comm.commission_type == "coordinator":
            explanations.append("Repasse conforme política de comissionamento.")
        if getattr(comm, "deduct_taxes", False):
            explanations.append("Impostos deduzidos conforme impostos da linha.")
        if getattr(comm, "deduct_card_fee", False):
            explanations.append("Taxa de cartão deduzida da base.")
        return " ".join(explanations) if explanations else "-"

    def write(self, vals):
        result = super().write(vals)
        if "crm_team_id" in vals and not self.env.context.get("crm_commissions_skip_member_team_sync"):
            members = self.env["commission.member"].sudo().search([("partner_id", "in", self.ids), ("team_id", "=", False)])
            members._sync_team_from_partner()
        return result
