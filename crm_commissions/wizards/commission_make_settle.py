# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date, timedelta
from itertools import groupby

from odoo import _, api, fields, models

from ..models.account_move import PAYMENT_STATES


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

    def _get_settlement_date(self, line):
        """Date that decides the settlement period of a source line.

        Invoice commissions are closed by the date the invoice was **paid**,
        not by the invoice date. CRM lines keep using their own settlement
        date (``target_date`` on targets, ``date_to`` on quarterly bonuses),
        exposed through ``invoice_date`` by those models.
        """
        if self.settlement_type == "sale_invoice":
            return line.payment_date or line.invoice_date
        return line.invoice_date

    @api.model
    def _agent_lines_sorted(self, agent_line):
        """Sort source lines by company, currency and settlement date.

        The settle loop opens a new settlement period whenever the date moves
        forward, so the lines of each company/currency must arrive in
        ascending date order. OCA relies on the search order for that; with
        the payment date in place we make the ordering explicit.
        """
        return (
            agent_line.company_id.id,
            agent_line.currency_id.id,
            self._get_settlement_date(agent_line) or date.min,
        )

    def _is_in_mass_period(self, line):
        """Check whether the source line falls inside the chosen period.

        The date used here is the settlement date: the invoice payment date
        for invoice commissions, and the target/bonus date for CRM lines.
        """
        self.ensure_one()
        line_date = self._get_settlement_date(line)
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
            # Invoice commissions are payment based: only invoices already
            # paid (or with a registered payment) can be closed, and the date
            # that matters is the payment date. The OCA domain filters by
            # ``invoice_date``, which would both close unpaid invoices and put
            # an invoice paid in October into the September settlement.
            domain = [
                ("agent_id", "=", agent.id),
                ("settled", "=", False),
                ("object_id.display_type", "=", "product"),
                ("invoice_id.state", "=", "posted"),
                ("invoice_id.payment_state", "in", PAYMENT_STATES),
            ]
            lines = self.env["account.invoice.line.agent"].search(domain)
            if not strict and date_to_agent:
                lines = lines.filtered(
                    lambda line: line.payment_date
                    and line.payment_date < date_to_agent
                )
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
        if self.settlement_type == "sale_invoice":
            # The line date follows the payment date, so the settlement line
            # and its period tell when the commission was actually earned.
            values["date"] = self._get_settlement_date(line)
            # O amount da linha de agente pode estar defasado se foi computado
            # antes da fatura ser paga (o compute nao depende de
            # invoice_id.payment_state). Forca o recompute para garantir o
            # valor correto antes de aplicar o rateio proporcional.
            line.invalidate_model(["amount"])
            agent_line = line
            invoice = agent_line.invoice_id
            if (
                invoice
                and invoice.payment_state == "partial"
                and invoice.amount_total
            ):
                amount_paid = invoice.amount_total - (invoice.amount_residual or 0.0)
                ratio = amount_paid / invoice.amount_total
                values["settled_amount"] = (agent_line.amount or 0.0) * ratio
        elif self.settlement_type == "crm_performance":
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

    def action_settle(self):
        """Create the settlements using the payment date as the period date.

        This is the OCA loop with one change: the period is opened from
        ``_get_settlement_date(line)`` instead of ``line.invoice_date``. The
        standard implementation would put an invoice paid in October into the
        September settlement just because it was issued in September.
        """
        self.ensure_one()
        settlement_obj = self.env["commission.settlement"]
        settlement_line_obj = self.env["commission.settlement.line"]
        settlement_ids = []
        agents = self.agent_ids or self.env["res.partner"].search(
            [("agent", "=", True)]
        )
        date_to = self.date_to
        for agent in agents:
            date_to_agent = self._get_period_start(agent, date_to)
            grouped_agent_lines = groupby(
                sorted(
                    self._get_agent_lines(agent, date_to_agent),
                    key=self._agent_lines_sorted,
                ),
                key=self._agent_lines_groupby,
            )
            for _k, grouper_agent_lines in grouped_agent_lines:
                agent_lines = list(grouper_agent_lines)
                pos = 0
                sett_to = date(year=1900, month=1, day=1)
                settlement = settlement_obj
                settlement_line_vals = []
                while pos < len(agent_lines):
                    line = agent_lines[pos]
                    pos += 1
                    if line._skip_settlement():
                        continue
                    line_date = self._get_settlement_date(line)
                    if not line_date:
                        continue
                    if line_date > sett_to:
                        sett_from = self._get_period_start(agent, line_date)
                        sett_to = self._get_next_period_date(agent, sett_from)
                        sett_to -= timedelta(days=1)
                        settlement = self._get_settlement(
                            agent,
                            line.company_id,
                            line.currency_id,
                            sett_from,
                            sett_to,
                        )
                        if not settlement:
                            settlement = settlement_obj.create(
                                self._prepare_settlement_vals(
                                    agent,
                                    line.company_id,
                                    sett_from,
                                    sett_to,
                                )
                            )
                            settlement.currency_id = line.currency_id
                        settlement_ids.append(settlement.id)
                    settlement_line_vals.append(
                        self._prepare_settlement_line_vals(settlement, line)
                    )
                settlement_line_obj.create(settlement_line_vals)
        if settlement_ids:
            return {
                "name": _("Created Settlements"),
                "type": "ir.actions.act_window",
                "views": [[False, "list"], [False, "form"]],
                "res_model": "commission.settlement",
                "domain": [["id", "in", settlement_ids]],
            }
        return False
