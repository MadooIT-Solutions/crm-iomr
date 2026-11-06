# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

# OCA uses these states to decide whether an invoice is already paid enough
# to settle its commission. ``in_payment`` is a registered payment still on
# its way to the bank; ``reversed`` is kept for refunds, matching the OCA
# ``_skip_settlement`` rule. ``partial`` is included so that invoices paid in
# part can be settled proportionally to the amount actually received.
PAYMENT_STATES = ("in_payment", "paid", "reversed", "partial")


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _prepare_agent_vals_from_sale_line(self, sol_agent):
        """Valores do agente copiados da linha do pedido, preservando o split.

        Usado na reconstrução dos agentes da fatura a partir das linhas de
        venda vinculadas (incluindo adiantamento/entrada). Sem o
        ``commission_split_percent`` a comissão do SDR (25%) e do médico
        indicador (50%) seria paga integral no fechamento da fatura.
        """
        return {
            "agent_id": sol_agent.agent_id.id,
            "commission_id": sol_agent.commission_id.id,
            "commission_split_percent": sol_agent.commission_split_percent or 100.0,
        }

    @api.model
    def _downpayment_sale_line_agent_commands(self, line):
        """Comandos de agentes vindos das linhas de venda (com split)."""
        commands = [(5, 0, 0)]
        for sol in line.sale_line_ids:
            for agent in sol.agent_ids.filtered("commission_id"):
                commands.append((0, 0, self._prepare_agent_vals_from_sale_line(agent)))
        return commands

    @api.depends("move_id.partner_id", "sale_line_ids", "sale_line_ids.is_downpayment")
    def _compute_agent_ids(self):
        """Garante agentes (com rateio/split) nas linhas de adiantamento.

        O adiantamento (entrada) gera uma linha de fatura vinculada às linhas
        de venda com ``is_downpayment=True``; os agentes comissionados do pedido
        devem receber a comissão proporcional ao valor pago na entrada. Quando
        a linha vem de venda, os agentes são copiados das linhas de venda
        preservando o ``commission_split_percent`` (que a cópia padrão pode
        omitir). Linhas fiscais brasileiras sem repasse (CFOP financeiro) seguem
        sem agentes. A cópia inclui também as linhas de produto regular vindas
        de venda para manter o split correto nessas faturas.
        """
        sale_lines = self.filtered(lambda line: line.sale_line_ids)
        other_lines = self - sale_lines
        if other_lines:
            super(AccountMoveLine, other_lines)._compute_agent_ids()
        for line in sale_lines:
            cfop = getattr(line, "cfop_id", False)
            if line.commission_free or (cfop and not getattr(cfop, "finance_move", True)):
                line.agent_ids = False
            else:
                line.agent_ids = self._downpayment_sale_line_agent_commands(line)


class AccountInvoiceLineAgent(models.Model):
    _inherit = "account.invoice.line.agent"

    payment_date = fields.Date(
        string="Payment Date",
        compute="_compute_payment_date",
        help="Date on which the invoice was paid. It is the date used to "
        "close payment-based commissions.",
    )

    @api.depends(
        "invoice_id.state",
        "invoice_id.payment_state",
        "invoice_id.line_ids.matched_debit_ids.max_date",
        "invoice_id.line_ids.matched_credit_ids.max_date",
    )
    def _compute_payment_date(self):
        for line in self:
            line.payment_date = line._get_payment_date()

    def _get_payment_date(self):
        """Return the date the invoice was actually paid.

        The date of the payment itself wins over the reconciliation date:
        ``account.partial.reconcile.max_date`` is the *latest* of the invoice
        and payment dates, so a payment made before the invoice date (an
        advance) would otherwise be reported as if it happened on the invoice
        date. When the invoice was settled by something other than an
        ``account.payment`` (a credit note, for example), the reconciliation
        date is the best available answer.
        """
        self.ensure_one()
        invoice = self.invoice_id
        if (
            not invoice
            or invoice.state != "posted"
            or invoice.payment_state not in PAYMENT_STATES
        ):
            return False
        payment_dates = [
            payment.date
            for payment in invoice.reconciled_payment_ids
            if payment.date
        ]
        if payment_dates:
            return max(payment_dates)
        partials = (
            invoice.line_ids.matched_debit_ids
            | invoice.line_ids.matched_credit_ids
        )
        partial_dates = [partial.max_date for partial in partials if partial.max_date]
        return max(partial_dates) if partial_dates else False

    def _skip_settlement(self):
        """Never settle an invoice commission before the invoice is paid.

        Invoices paid in part (``partial``) are now settleable: the settled
        amount is then prorated to the amount actually received, computed in
        ``commission.settlement.line._compute_settled_amount``.
        """
        self.ensure_one()
        if self.invoice_id.state != "posted":
            return True
        if self.invoice_id.payment_state not in PAYMENT_STATES:
            return True
        # Fatura postada e em um estado de pagamento aceitavel: nao pulamos.
        # (A regra do OCA so adiciona a restricao de invoice_state == "paid"
        # com uma lista hardcoded que nao inclui "partial"; ja tratamos acima.)
        return False

    @api.depends(
        "object_id.price_subtotal",
        "object_id.commission_free",
        "object_id.quantity",
        "commission_id",
        "commission_split_percent",
        # Quando o pagamento da fatura muda (ex.: not_paid -> partial), o
        # amount da linha de agente precisa ser recomputado para refletir o
        # valor real da comissão sobre o pagamento efetivo.
        "invoice_id.payment_state",
    )
    def _compute_amount(self):
        """Apply the agent split to the invoice commission amount.

        The OCA computation only looks at the commission itself, so a row
        carrying 25% (SDR) or 50% (doctor referral) would otherwise be paid in
        full on the invoice even though the sale line holds the right share.
        """
        result = super()._compute_amount()
        for line in self:
            line.amount = line.amount or 0.0
            if line.commission_split_percent:
                line.amount *= line.commission_split_percent / 100.0
        return result
