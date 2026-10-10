# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

from odoo import _, api, fields, models


class CommissionMassSettle(models.TransientModel):
    _name = "commission.mass.settle"
    _description = "Mass Commission Settlement"

    date_from = fields.Date(
        string="Data Início",
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string="Data Fim",
        required=True,
        default=fields.Date.today,
    )
    team_ids = fields.Many2many(
        comodel_name="crm.team",
        string="Equipes",
        help="Deixe vazio para processar todas as equipes.",
    )
    agent_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Agentes",
        domain="['|', '|', ('agent', '=', True), ('target_ids', '!=', False), "
        "('type_partner', 'in', ['doctorint', 'doctorext'])]",
        help="Deixe vazio para processar todos os agentes.",
    )
    settlement_type = fields.Selection(
        selection=[
            ("all", "Todos os Tipos"),
            ("crm_performance", "CRM Performance"),
            ("sale_invoice", "Sales Invoice"),
        ],
        string="Tipo de Liquidação",
        default="all",
        required=True,
    )

    def _get_agents(self):
        """Retorna agentes filtrados por equipe e/ou seleção manual.

        Inclui quem tem ``agent=True``, quem possui metas CRM
        (``crm.commission.target``) e os médicos (``doctorint``/``doctorext``),
        cujo repasse corre por fatura e pode não ter a marca de agente.
        """
        domain = [
            "|",
            "|",
            ("agent", "=", True),
            ("target_ids", "!=", False),
            ("type_partner", "in", ("doctorint", "doctorext")),
        ]
        if self.team_ids:
            domain.append(("crm_team_id", "in", self.team_ids.ids))
        if self.agent_ids:
            domain.append(("id", "in", self.agent_ids.ids))
        return self.env["res.partner"].search(domain)

    def _get_settlement_types(self):
        """Retorna lista de tipos de liquidação para processar."""
        if self.settlement_type == "all":
            return ["crm_performance", "sale_invoice"]
        return [self.settlement_type]

    def action_settle(self):
        """Executa o fechamento em lote de comissões."""
        self.ensure_one()
        agents = self._get_agents()
        if not agents:
            raise models.UserError(
                _("Nenhum agente encontrado com os filtros selecionados.")
            )

        settlement_types = self._get_settlement_types()
        make_settle = self.env["commission.make.settle"]
        all_settlements = self.env["commission.settlement"]
        summary = {
            "agents_processed": 0,
            "agents_skipped": 0,
            "settlements_created": 0,
            "total_amount": 0.0,
        }

        for agent in agents:
            agent_settlements = self.env["commission.settlement"]
            for stype in settlement_types:
                wizard = make_settle.with_context(commission_mass_settle=True).create(
                    {
                        "date_from": self.date_from,
                        "date_to": self.date_to,
                        "agent_ids": [(6, 0, [agent.id])],
                        "settlement_type": stype,
                    }
                )
                result = wizard.action_settle()
                if isinstance(result, dict) and result.get("domain"):
                    # Formato: [["id", "in", [1, 2, 3]]]
                    domain = result["domain"]
                    if domain and domain[0][0] == "id":
                        settlement_ids = domain[0][2]
                        if settlement_ids:
                            agent_settlements |= self.env[
                                "commission.settlement"
                            ].browse(settlement_ids)

            if agent_settlements:
                all_settlements |= agent_settlements
                summary["agents_processed"] += 1
                summary["settlements_created"] += len(agent_settlements)
                summary["total_amount"] += sum(agent_settlements.mapped("total"))
            else:
                summary["agents_skipped"] += 1

        # Armazena resultado no contexto para exibição
        self.env.context = {
            **self.env.context,
            "mass_settle_result": {
                "settlement_ids": all_settlements.ids,
                "summary": summary,
            },
        }

        if all_settlements:
            return {
                "name": _("Mass Settlement Result"),
                "type": "ir.actions.act_window",
                "res_model": "commission.settlement",
                "view_mode": "list,form",
                "domain": [("id", "in", all_settlements.ids)],
                "context": {
                    "mass_settle_summary": summary,
                },
            }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Mass Settlement"),
                "message": _(
                    "Nenhum settlement foi criado para o período de "
                    "%(date_from)s a %(date_to)s. Verifique se há comissões "
                    "pendentes (faturas postadas e/ou metas alcançadas) para "
                    "os %(agent_count)s agente(s) selecionado(s).",
                    date_from=self.date_from or "-",
                    date_to=self.date_to or "-",
                    agent_count=len(agents),
                ),
                "type": "warning",
                "sticky": False,
            },
        }

    @api.model
    def _cron_mass_settle(self):
        """Executa fechamento em lote automaticamente (cron mensal)."""
        today = fields.Date.today()
        last_month = today.replace(day=1) - timedelta(days=1)
        date_from = last_month.replace(day=1)

        wizard = self.create(
            {
                "date_from": date_from,
                "date_to": last_month,
                "settlement_type": "all",
            }
        )
        result = wizard.action_settle()
        return result
