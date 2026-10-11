# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CommissionMassInvoice(models.TransientModel):
    _name = "commission.mass.invoice"
    _description = "Mass Commission Invoice Creation"

    date = fields.Date(
        string="Data da Fatura",
        default=fields.Date.today,
        required=True,
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Diário",
        required=True,
        domain="[('type', '=', 'purchase')]",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Produto para Faturamento",
        required=True,
    )
    team_ids = fields.Many2many(
        comodel_name="crm.team",
        string="Equipes",
        help="Deixe vazio para incluir todas as equipes.",
    )
    agent_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Agentes",
        domain="[('agent', '=', True)]",
        help="Deixe vazio para incluir todos os agentes.",
    )
    date_from = fields.Date(string="Período - De")
    date_to = fields.Date(string="Período - Até")
    group_by = fields.Selection(
        selection=[
            ("agent", "Agente"),
            ("period", "Agente + Período"),
            ("individual", "Individual"),
        ],
        string="Agrupar Por",
        default="agent",
        required=True,
    )
    settlement_ids = fields.Many2many(
        comodel_name="commission.settlement",
        string="Settlements",
        domain="[('state', '=', 'settled')]",
    )

    def _get_settlement_domain(self):
        """Retorna domínio para buscar settlements pendentes."""
        domain = [("state", "=", "settled")]
        if self.team_ids:
            domain.append(("agent_id.crm_team_id", "in", self.team_ids.ids))
        if self.agent_ids:
            domain.append(("agent_id", "in", self.agent_ids.ids))
        if self.date_from:
            domain.append(("date_from", ">=", self.date_from))
        if self.date_to:
            domain.append(("date_to", "<=", self.date_to))
        return domain

    def action_preview(self):
        """Busca settlements pendentes e atualiza a lista para revisão."""
        self.ensure_one()
        domain = self._get_settlement_domain()
        settlements = self.env["commission.settlement"].search(domain)
        self.settlement_ids = [(6, 0, settlements.ids)]
        return {
            "type": "ir.actions.act_window",
            "name": _("Revisão de Faturamento"),
            "res_model": "commission.mass.invoice",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }

    def action_create_invoices(self):
        """Cria faturas de pagamento para os settlements selecionados."""
        self.ensure_one()
        if not self.settlement_ids:
            raise UserError(_("Nenhum settlement selecionado para faturamento."))

        settlements = self.settlement_ids.filtered(lambda s: s.state == "settled")
        if not settlements:
            raise UserError(_("Nenhum settlement válido para faturamento."))

        # O método ``groupby`` de recordset foi removido no Odoo 18. O
        # ``make_invoices`` do account_commission_oca já agrupa por agente
        # (company/currency), troca faturas negativas para refund e marca os
        # settlements como faturados. Para "Agente + Período" pré-agrupamos em
        # buckets, pois o OCA não considera o período nas chaves de agrupamento.
        settlement_obj = self.env["commission.settlement"]
        if self.group_by == "period":
            buckets = {}
            for settlement in settlements:
                key = (settlement.agent_id, settlement.date_from, settlement.date_to)
                buckets.setdefault(key, settlement_obj)
                buckets[key] |= settlement
            groups = list(buckets.values())
        else:
            groups = [settlements]

        grouped_invoice = self.group_by != "individual"
        invoices = self.env["account.move"]
        for group in groups:
            invoices |= group.make_invoices(
                self.journal_id,
                self.product_id,
                self.date,
                grouped=grouped_invoice,
            )

        return {
            "name": _("Faturas Criadas"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", invoices.ids)],
        }

    @api.model
    def _cron_mass_invoice(self):
        """Executa criação de faturas automaticamente (cron mensal)."""
        today = fields.Date.today()
        last_month = today.replace(day=1) - timedelta(days=1)

        journal = self.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", self.env.company.id)],
            limit=1,
        )
        if not journal:
            return False

        product = self.env["product.product"].search(
            [("name", "ilike", "commission")],
            limit=1,
        )
        if not product:
            product = self.env["product.product"].search(
                [("type", "=", "service")],
                limit=1,
            )
        if not product:
            return False

        wizard = self.create(
            {
                "date": today,
                "journal_id": journal.id,
                "product_id": product.id,
                "date_from": last_month.replace(day=1),
                "date_to": last_month,
                "group_by": "agent",
            }
        )
        wizard.action_preview()
        return wizard.action_create_invoices()
