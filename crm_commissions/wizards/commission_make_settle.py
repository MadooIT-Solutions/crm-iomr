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
            # A zero-amount line would mark the target as closed and hide it
            # from every later closing (the form filters zero lines out), so
            # only settle targets whose commission is actually positive.
            lines = lines.filtered(
                lambda target: self._calculate_crm_performance_commission(target)
                > 0.0
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
        if self.settlement_type == "sale_invoice":
            lines = self._exclude_already_settled_invoice_lines(lines)
        # Linhas de origem cujo valor calculado é zero (adiantamentos, entradas,
        # descontos sem comissão) não devem virar linha de fechamento: ficam
        # escondidas na tela e só poluem a lista. Filtrar aqui evita também
        # criar uma liquidação vazia quando todas as linhas do período são zero.
        lines = lines.filtered(
            lambda line: not self._is_zero_settlement_amount(
                line, self._get_settlement_line_amount(line)
            )
        )
        return lines

    def _exclude_already_settled_invoice_lines(self, agent_lines):
        """Drop invoice lines that already have a settlement line.

        ``settled`` (OCA) is computed from the settlement lines and cannot be
        trusted as the only guard: when an invoice line is recomputed its
        agent rows are deleted/recreated, the settlement loses the link and
        the new row is born with ``settled=False``. Looking at the invoice
        line itself closes that hole and lets an orphan settlement line be
        re-linked to its current agent row instead of paying it again.
        """
        self.ensure_one()
        if not agent_lines:
            return agent_lines
        SettlementLine = self.env["commission.settlement.line"]
        # Backfill the stable invoice-line reference on old rows before using
        # it as the dedup key (it used to be a related field that vanished
        # together with the agent row).
        legacy_lines = SettlementLine.search(
            [
                ("invoice_line_id", "=", False),
                ("invoice_agent_line_id", "in", agent_lines.ids),
            ]
        )
        for settlement_line in legacy_lines:
            settlement_line.invoice_line_id = (
                settlement_line.invoice_agent_line_id.object_id
            )
        existing = SettlementLine.search(
            [
                ("settlement_id.settlement_type", "=", "sale_invoice"),
                ("settlement_id.state", "!=", "cancel"),
                "|",
                ("invoice_agent_line_id", "in", agent_lines.ids),
                ("invoice_line_id", "in", agent_lines.mapped("object_id").ids),
            ]
        )
        by_agent_line = {
            settlement_line.invoice_agent_line_id.id: settlement_line
            for settlement_line in existing
            if settlement_line.invoice_agent_line_id
        }
        by_invoice_line = {}
        for settlement_line in existing:
            if not settlement_line.invoice_line_id:
                continue
            key = (settlement_line.invoice_line_id.id, settlement_line.agent_id.id)
            by_invoice_line.setdefault(key, settlement_line)
        skipped = self.env["account.invoice.line.agent"]
        for agent_line in agent_lines:
            if agent_line.id in by_agent_line:
                skipped |= agent_line
                continue
            settlement_line = by_invoice_line.get(
                (agent_line.object_id.id, agent_line.agent_id.id)
            )
            if not settlement_line:
                continue
            # The invoice line was already closed, but its agent row was
            # recreated. Re-link the old settlement line (restoring the
            # source) and skip the new row. Only settlements still open to
            # editing are relinked; invoiced ones are left untouched but the
            # new row is skipped all the same.
            if (
                not settlement_line.invoice_agent_line_id
                and settlement_line.settlement_id.state == "settled"
            ):
                settlement_line.invoice_agent_line_id = agent_line.id
            skipped |= agent_line
        return agent_lines - skipped

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

        return target._calculate_crm_performance_commission()

    def _prepare_settlement_line_vals(self, settlement, line):
        values = super()._prepare_settlement_line_vals(settlement, line)
        if self.settlement_type == "sale_invoice":
            # The line date follows the payment date, so the settlement line
            # and its period tell when the commission was actually earned.
            values["date"] = self._get_settlement_date(line)
            # Keep the invoice line reference independent from the agent row:
            # recomputing the invoice agents deletes/recreates them and the
            # related field used to disappear, allowing the same commission
            # to be closed twice.
            values["invoice_line_id"] = line.object_id.id
            base_amount = line._get_settlement_base_amount()
            values["invoice_base_amount"] = base_amount
            values["settled_amount"] = self._get_invoice_settlement_amount(
                line, base_amount
            )
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
        else:
            # Fechamentos manuais também não podem nascer com valor zero.
            values["settled_amount"] = self._get_settlement_line_amount(line)
        return values

    def _get_invoice_settlement_amount(self, agent_line, base_amount):
        """Commission amount proportional to the amount actually received."""
        invoice = agent_line.invoice_id
        if (
            invoice
            and invoice.payment_state == "partial"
            and invoice.amount_total
        ):
            amount_paid = invoice.amount_total - (invoice.amount_residual or 0.0)
            ratio = max(0.0, min(amount_paid / invoice.amount_total, 1.0))
            return base_amount * ratio
        return base_amount

    def _get_settlement_line_amount(self, line):
        """Valor que a linha de origem fecharia, antes de ser criada.

        Usado para descartar linhas de valor zero. Mantém o mesmo cálculo de
        ``_prepare_settlement_line_vals`` para todos os tipos de fechamento.
        """
        if line._name == "account.invoice.line.agent":
            base_amount = line._get_settlement_base_amount()
            return self._get_invoice_settlement_amount(line, base_amount)
        if self.settlement_type == "crm_performance":
            return self._calculate_crm_performance_commission(line)
        if self.settlement_type == "crm_quarterly_recovery":
            return line.lost_commission_recovered or 0.0
        return getattr(line, "amount", 0.0) or 0.0

    @api.model
    def _is_zero_settlement_amount(self, line, amount):
        """Compara o valor com zero usando a moeda da linha de origem."""
        currency = getattr(line, "currency_id", False) or self.env.company.currency_id
        return currency.is_zero(amount or 0.0)

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
                        if settlement.id not in settlement_ids:
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
