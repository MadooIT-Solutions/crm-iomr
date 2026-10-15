# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

from odoo import fields, models


class CommissionMakeSettle(models.TransientModel):
    _inherit = "commission.make.settle"

    date_from = fields.Date(string="From")
    settlement_type = fields.Selection(
        selection_add=[
            ("crm_performance", "CRM Performance"),
            ("crm_quarterly_recovery", "CRM Quarterly Recovery"),
        ],
        ondelete={
            "crm_performance": "cascade",
            "crm_quarterly_recovery": "cascade",
        },
    )

    def _is_in_mass_period(self, line):
        """Check whether the source line falls inside the chosen period.

        ``invoice_date`` mirrors ``target_date`` on CRM targets and holds the
        invoice date on invoice agent lines, so it works for both settlement
        types.
        """
        self.ensure_one()
        line_date = line.invoice_date
        if not line_date:
            return True
        if self.date_from and line_date < self.date_from:
            return False
        if self.date_to and line_date > self.date_to:
            return False
        return True

    def _get_agent_lines(self, agent, date_to_agent):
        self.ensure_one()
        # The mass settlement wizard passes a context flag because the standard
        # wizard relies on period-truncated dates, which would leave the very
        # period selected by the user out of the settlement.
        strict = bool(self.env.context.get("commission_mass_settle"))
        if self.settlement_type == "crm_performance":
            domain = [
                ("agent_id", "=", agent.id),
                ("state", "in", ["achieved", "in_progress"]),
            ]
            if not strict:
                domain.append(("target_date", "<=", date_to_agent))
            lines = self.env["crm.commission.target"].search(
                domain, order="target_date asc"
            )
        elif self.settlement_type == "crm_quarterly_recovery":
            # Bônus trimestrais com recuperação de comissão que ainda não
            # foram faturados. A ordenação precisa ser ascendente por data:
            # ``action_settle`` agrupa as linhas por período a partir da
            # primeira linha e só abre um novo período quando encontra uma
            # data posterior.
            domain = [
                ("agent_id", "=", agent.id),
                ("state", "=", "recovered"),
                ("lost_commission_recovered", ">", 0),
            ]
            if not strict:
                domain.append(("date_to", "<=", date_to_agent))
            lines = self.env["crm.commission.quarterly.bonus"].search(
                domain, order="date_to asc"
            )
        else:
            upper = date_to_agent
            if strict and self.date_to:
                # Inclusive upper bound: `< date_to + 1` equals `<= date_to`.
                upper = self.date_to + timedelta(days=1)
            lines = super()._get_agent_lines(agent, upper)
        if strict:
            lines = lines.filtered(self._is_in_mass_period)
        return lines

    def _get_crm_performance_base(self, target):
        """Base elegível de comissão da meta (Política 2026).

        Repassa o cálculo ao modelo da meta para manter a mesma base usada
        no fechamento do bônus trimestral: vendas sincronizadas do mês,
        menos impostos e taxa de cartão (lentes entram pela taxa própria).
        """
        return target._get_commission_base()

    def _get_crm_performance_rate(self, target):
        """Taxa base da Política 2026 para a performance da meta.

        - 0-50%: 0,25%
        - 51-99%: 0,45%
        - 100%: 0,75%
        - 101-120%: 1,25%
        - >120%: 1,75%

        A escolha da faixa é compartilhada com o cálculo da recuperação
        trimestral, garantindo que os dois valores fechados batam.
        """
        return target._get_rate_for_performance(target.performance_pct or 0.0)

    def _calculate_crm_performance_commission(self, target):
        """Calcula o valor da comissão CRM Performance.

        Valor = base_elegível × taxa_final / 100
        taxa_final = taxa_base + bônus_IS_CRM (ou - penalidade_IS_CRM)
        """
        if not target or not target.agent_id:
            return 0.0

        base = self._get_crm_performance_base(target)
        if not base:
            return 0.0

        rate = self._get_crm_performance_rate(target)

        # Aplica bônus/penalidade IS-CRM
        is_crm_ok = target.is_crm_ok
        commission = target.commission_id
        if commission:
            if is_crm_ok:
                rate += commission.is_crm_bonus
            else:
                rate -= commission.is_crm_penalty

        commission_amount = base * rate / 100.0
        return max(commission_amount, 0.0)

    def _prepare_settlement_line_vals(self, settlement, line):
        values = super()._prepare_settlement_line_vals(settlement, line)
        if self.settlement_type == "crm_performance":
            values.update(
                {
                    "settlement_id": settlement.id,
                    "target_id": line.id,
                    "date": line.target_date,
                    "commission_id": line.commission_id.id,
                    "settled_amount": self._calculate_crm_performance_commission(line),
                }
            )
        elif self.settlement_type == "crm_quarterly_recovery":
            agent = line.agent_id
            commission = agent.commission_id if agent else False
            values.update(
                {
                    "settlement_id": settlement.id,
                    "quarterly_bonus_id": line.id,
                    "date": line.date_to,
                    "commission_id": commission.id,
                    "settled_amount": line.lost_commission_recovered,
                }
            )
        return values
