# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

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
        seen_agent_ids = set()
        for sol in line.sale_line_ids:
            for agent in sol.agent_ids.filtered("commission_id"):
                if agent.agent_id.id not in seen_agent_ids:
                    seen_agent_ids.add(agent.agent_id.id)
                    commands.append(
                        (0, 0, self._prepare_agent_vals_from_sale_line(agent))
                    )
        return commands

    @api.depends(
        "move_id.partner_id",
        "sale_line_ids",
        "sale_line_ids.is_downpayment",
        # Commission rules are often created/changed *after* the invoice was
        # issued (e.g. the 1% extras rule added in October). The agents of a
        # confirmed order are then recomputed, but the invoice kept the old
        # set and the closing silently lost those commissions (order S00580 /
        # Thaisy: MAT/MED had no invoice agent row). Depending on the source
        # agents keeps both sides in sync; lines already closed are protected
        # by the ``locked`` filter below.
        "sale_line_ids.agent_ids",
        "sale_line_ids.agent_ids.agent_id",
        "sale_line_ids.agent_ids.commission_id",
        "sale_line_ids.agent_ids.commission_split_percent",
    )
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

        Duas proteções evitam que o fechamento perca a origem da comissão:

        * linhas que já têm agente fechado por um *settlement* não são
          recalculadas -- apagar e recriar o agente zeraria o vínculo
          ``commission.settlement.line.invoice_agent_line_id`` (a FK é
          ``ON DELETE SET NULL``) e a mesma comissão seria fechada de novo;
        * somente linhas de produto recebem agentes. Notas, seções, impostos
          e condições de pagamento não têm comissão e geravam linhas de
          agente com valor zero no fechamento.
        """
        locked = self.filtered(lambda line: line.agent_ids.filtered("settled"))
        todo = self - locked
        sale_lines = todo.filtered(
            lambda line: line.display_type == "product" and line.sale_line_ids
        )
        other_lines = todo - sale_lines
        if other_lines:
            super(AccountMoveLine, other_lines)._compute_agent_ids()
        for line in sale_lines:
            cfop = getattr(line, "cfop_id", False)
            if line.commission_free or (
                cfop and not getattr(cfop, "finance_move", True)
            ):
                line.agent_ids = False
            else:
                line.agent_ids = self._downpayment_sale_line_agent_commands(line)

    def _backfill_missing_agents_from_sale_lines(self):
        """Create invoice agent rows that the linked sale lines owe.

        Rules created after an invoice was posted (or a manual edit of the
        order's agents) used to leave the invoice without the corresponding
        agent row, so the commission was never picked up by the closing. This
        only *adds* missing rows: existing agents -- especially the ones
        already closed by a settlement -- are never changed, which keeps the
        repair idempotent and safe for historical invoices.

        Returns the number of created rows.
        """
        Agent = self.env["account.invoice.line.agent"].sudo()
        existing = Agent.search([("object_id", "in", self.ids)])
        existing_by_line = {}
        for agent in existing:
            existing_by_line.setdefault(agent.object_id.id, set()).add(
                agent.agent_id.id
            )

        created = 0
        for line in self.sudo():
            if line.display_type != "product" or not line.sale_line_ids:
                continue
            cfop = getattr(line, "cfop_id", False)
            if line.commission_free or (
                cfop and not getattr(cfop, "finance_move", True)
            ):
                continue
            present = existing_by_line.get(line.id, set())
            for command in self._downpayment_sale_line_agent_commands(line):
                if command[0] != 0:
                    continue
                vals = command[2]
                agent_id = vals.get("agent_id")
                if not agent_id or agent_id in present:
                    continue
                Agent.create(dict(vals, object_id=line.id))
                present.add(agent_id)
                created += 1
        return created


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

    def _has_active_settlement(self):
        """Whether this agent row was already closed by a settlement."""
        self.ensure_one()
        return any(
            line.settlement_id.state != "cancel"
            for line in self.settlement_line_ids
        )

    def unlink(self):
        """Block deleting a commission row that is already closed.

        ``commission.settlement.line.invoice_agent_line_id`` is an
        ``ON DELETE SET NULL`` foreign key. Recomputing the agents of an
        invoice line deletes/recreates its rows; when that happens after the
        commission was closed, the settlement line loses its origin and the
        recreated row looks unsettled -- so the next closing pays the same
        commission again. Protecting the closed rows keeps the history and
        the closing idempotent.
        """
        protected = self.filtered(lambda line: line._has_active_settlement())
        if protected and not self.env.context.get(
            "crm_commissions_allow_settled_agent_unlink"
        ):
            raise UserError(
                _(
                    "Não é possível excluir agentes de comissão já fechados "
                    "por um fechamento. Cancele o fechamento antes de alterar "
                    "os agentes da fatura."
                )
            )
        return super().unlink()

    def _get_settlement_sale_orders(self):
        """Pedidos de venda que a linha da fatura está faturando.

        A origem confiável é a linha de venda vinculada à linha da fatura
        (``sale_line_ids``), que cobre também adiantamentos e faturas
        parciais. ``invoice_origin`` é o fallback para linhas antigas ou
        digitadas sem vínculo. O resultado pode ter mais de um pedido quando
        a fatura cobre vários pedidos.
        """
        self.ensure_one()
        source_line = self.object_id
        if source_line and source_line.sale_line_ids:
            return source_line.sale_line_ids.order_id
        invoice = self.invoice_id
        if invoice and invoice.invoice_origin:
            names = [
                name.strip()
                for name in invoice.invoice_origin.split(",")
                if name.strip()
            ]
            if len(names) == 1:
                return self.env["sale.order"].search(
                    [("name", "=", names[0])], limit=1
                )
        return self.env["sale.order"]

    def _get_agent_order_lines(self, sale_order):
        """Linhas do pedido que carregam comissão para este agente.

        Adiantamentos (``is_downpayment``) não entram: o valor deles é uma
        antecipação das linhas de produto e seria contado duas vezes. Linhas
        de seção/nota também não têm comissão própria. Linhas de valor zero
        entram quando têm comissão: um repasse fixo pode existir em uma linha
        de cortesia e precisa ser pago quando o pedido for faturado.
        """
        self.ensure_one()
        return sale_order.order_line.filtered(
            lambda line: not line.display_type
            and not line.is_downpayment
            and any(
                agent.agent_id == self.agent_id for agent in line.agent_ids
            )
        )

    def _get_agent_order_commission(self, sale_order):
        """Comissão total do agente no pedido (com o split já aplicado)."""
        self.ensure_one()
        commission = 0.0
        for line in self._get_agent_order_lines(sale_order):
            for agent in line.agent_ids:
                if agent.agent_id == self.agent_id:
                    commission += agent.amount or 0.0
        return commission

    def _get_agent_ordered_base(self, sale_order):
        """Valor de produto das linhas do agente no pedido."""
        self.ensure_one()
        return sum(
            line.price_subtotal or 0.0
            for line in self._get_agent_order_lines(sale_order)
        )

    def _get_sale_order_invoices(self, sale_order):
        """Faturas postadas que cobrem o pedido, em ordem cronológica."""
        invoices = sale_order.order_line.invoice_lines.move_id
        invoices = invoices.filtered(
            lambda move: move.state == "posted"
            and move.move_type in ("out_invoice", "out_refund")
        )
        if not invoices and sale_order.name:
            invoices = self.env["account.move"].search(
                [
                    ("invoice_origin", "=", sale_order.name),
                    ("state", "=", "posted"),
                    ("move_type", "in", ("out_invoice", "out_refund")),
                ]
            )
        return invoices.sorted(
            lambda move: (move.invoice_date or date.min, move.id)
        )

    def _order_has_commissioned_advances(self, sale_order):
        """Whether an adiantamento invoice of the order carries this agent.

        Adiantamentos sem agente nunca receberam comissão; nesse caso as
        linhas de adiantamento (a positiva na entrada e a negativa na fatura
        final) não podem entrar no valor faturado, senão a fatia seria
        descontada duas vezes. Quando o adiantamento tem o agente, as duas
        pontas entram e o acumulado fecha exatamente no valor do pedido.
        """
        self.ensure_one()
        for invoice in self._get_sale_order_invoices(sale_order):
            for line in invoice.invoice_line_ids:
                if line.display_type != "product":
                    continue
                sale_lines = line.sale_line_ids.filtered(
                    lambda sol: sol.order_id == sale_order
                )
                if not sale_lines:
                    continue
                if not any(sol.is_downpayment for sol in sale_lines):
                    continue
                if any(
                    agent.agent_id == self.agent_id for agent in line.agent_ids
                ):
                    return True
        return False

    def _get_invoice_agent_billed_value(
        self, invoice, sale_order, include_downpayments
    ):
        """Valor faturado da fatura que pertence a este agente.

        Linhas de produto vinculadas ao pedido entram pelo ``price_subtotal``
        (já líquido de ``discount``/``discount_fixed``). Linhas de
        adiantamento entram rateadas pela participação do agente no pedido:
        o adiantamento não tem produto do agente, mas reduz proporcionalmente
        o valor de todas as linhas. Sem esse rateio, um adiantamento maior
        que a base do agente estouraria o acumulado e a fatura final ficaria
        negativa.
        """
        self.ensure_one()
        direct = 0.0
        downpayment = 0.0
        for line in invoice.invoice_line_ids:
            if line.display_type != "product":
                continue
            sale_lines = line.sale_line_ids.filtered(
                lambda sol: sol.order_id == sale_order
            )
            if not sale_lines:
                continue
            # Uma linha de adiantamento representa valor de todas as linhas
            # do pedido, não de um produto específico: entra pelo rateio.
            if any(sol.is_downpayment for sol in sale_lines):
                if include_downpayments:
                    downpayment += line.price_subtotal or 0.0
            elif any(agent.agent_id == self.agent_id for agent in line.agent_ids):
                direct += line.price_subtotal or 0.0
        order_base = self._get_agent_ordered_base(sale_order)
        order_total = sale_order.amount_total or 0.0
        share = order_base / order_total if order_total else 0.0
        return direct + downpayment * share

    def _get_billed_slice(self, sale_order):
        """Fatia do pedido que esta fatura representa para o agente.

        A fatia é acumulada: cada fatura usa o faturado até ela, descontado o
        que as faturas anteriores já consumiram. Entradas sem agente contam
        para o acumulado, então a fatura final absorve a parte delas em vez de
        perder a comissão. O acumulado é limitado ao valor do agente para que
        o total fechado nunca passe da comissão do pedido. Faturas de
        devolução podem gerar fatia negativa (estorno proporcional).

        Retorna ``None`` quando a fatura atual não pertence ao pedido.
        """
        self.ensure_one()
        invoices = self._get_sale_order_invoices(sale_order)
        if self.invoice_id not in invoices:
            return None
        order_base = self._get_agent_ordered_base(sale_order)
        if order_base <= 0.0:
            return None
        include_downpayments = self._order_has_commissioned_advances(sale_order)
        before = 0.0
        through = 0.0
        for invoice in invoices:
            billed = self._get_invoice_agent_billed_value(
                invoice, sale_order, include_downpayments
            )
            if invoice == self.invoice_id:
                through = before + billed
                break
            before += billed
        before = min(max(before, 0.0), order_base)
        through = min(max(through, 0.0), order_base)
        return through - before

    def _distribute_invoice_base(self, base_amount, sale_order):
        """Divide a base da fatura entre as linhas do mesmo agente.

        O rateio é por pedido/agente, não por linha: se o agente tiver mais de
        uma linha na fatura (vários produtos, adiantamento e linha negativa),
        repetir a base em cada linha multiplicaria a comissão. O peso é o
        ``amount`` da linha, que já carrega o split e a regra de cada produto;
        se todas estiverem zeradas, usa o valor de produto. Linhas de outros
        pedidos na mesma fatura ficam de fora, para a base de um pedido não
        vazar para o outro.

        Linhas de adiantamento ficam de fora do rateio quando há linhas de
        produto na mesma fatura: a entrada já recebeu a sua fatia na própria
        fatura de adiantamento e a linha negativa da fatura final só corrige
        o acumulado. Sem isso, o valor final seria dividido entre o produto e
        a linha negativa, pagando a menos no produto e "devolvendo" comissão
        na linha de entrada.
        """
        self.ensure_one()
        invoice = self.invoice_id
        if not invoice:
            return base_amount
        siblings = invoice.invoice_line_ids.agent_ids.filtered(
            lambda line: line.agent_id == self.agent_id
            and sale_order in line.object_id.sale_line_ids.order_id
        )
        if self not in siblings:
            return base_amount
        product_siblings = siblings.filtered(
            lambda line: not any(
                sol.is_downpayment for sol in line.object_id.sale_line_ids
            )
        )
        if product_siblings:
            if self not in product_siblings:
                return 0.0
            siblings = product_siblings
        if len(siblings) <= 1:
            return base_amount
        weights = [abs(line.amount or 0.0) for line in siblings]
        if not sum(weights):
            weights = [
                abs(line.object_id.price_subtotal or 0.0) for line in siblings
            ]
        total = sum(weights)
        if not total:
            return base_amount / len(siblings)
        index = siblings.ids.index(self.id)
        return base_amount * weights[index] / total

    def _is_single_full_invoice(self, sale_order):
        """Whether this is the only invoice and it bills the whole order."""
        self.ensure_one()
        invoices = self._get_sale_order_invoices(sale_order)
        return (
            len(invoices) == 1
            and invoices == self.invoice_id
            and abs(
                (self.invoice_id.amount_total or 0.0)
                - (sale_order.amount_total or 0.0)
            )
            <= 0.01
        )

    def _get_settlement_base_amount(self):
        """Base da comissão quando esta linha de fatura é fechada.

        A comissão do agente no pedido é rateada pelo valor efetivamente
        faturado das linhas do agente, não pelo total do pedido/fatura::

            base = comissão_do_pedido × faturado_do_agente / valor_do_agente

        O faturado é acumulado por fatura, então o total fechado nunca passa
        da comissão do pedido e um desconto aplicado só na fatura reduz todas
        as comissões (inclusive repasses fixos) na mesma proporção. Entradas
        sem agente entram no acumulado; entradas com agente são descontadas
        na fatura final para não pagar duas vezes.

        Exceção: a fatura única que cobre o pedido inteiro preserva o
        ``amount`` calculado na fatura. Faturas com mais de um pedido, ou
        linhas sem pedido de origem, também usam o ``amount`` -- o rateio
        entre pedidos não é trivial e não pode alterar o valor.
        """
        self.ensure_one()
        amount = self.amount or 0.0
        invoice = self.invoice_id
        if not invoice:
            return amount
        if not self.object_id or self.object_id.display_type != "product":
            return amount

        orders = self._get_settlement_sale_orders()
        if len(orders) > 1:
            _logger.warning(
                "Fatura %s cobre mais de um pedido; a comissão do agente %s "
                "usará o valor da linha da fatura.",
                invoice.name,
                self.agent_id.display_name,
            )
            return amount
        if not orders:
            return amount
        sale_order = orders

        if self._is_single_full_invoice(sale_order) and amount:
            return amount

        order_base = self._get_agent_ordered_base(sale_order)
        order_commission = self._get_agent_order_commission(sale_order)
        if order_base <= 0.0 or not order_commission:
            if amount:
                _logger.warning(
                    "Pedido %s sem base/comissão calculável para o agente "
                    "%s; mantendo o valor da fatura %s.",
                    sale_order.name,
                    self.agent_id.display_name,
                    invoice.name,
                )
            return amount

        billed_slice = self._get_billed_slice(sale_order)
        if billed_slice is None:
            return amount
        base_amount = order_commission * billed_slice / order_base
        return self._distribute_invoice_base(base_amount, sale_order)

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
        "invoice_id.state",
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
            # Se a fatura esta postada e paga (ou parcialmente paga), mas o
            # amount ficou zerado (compute executado antes da fatura ser
            # postada, ou linha sem produto), forca o recalculo com base no
            # price_subtotal atual.
            if (
                line.amount == 0.0
                and line.invoice_id.state == "posted"
                and line.invoice_id.payment_state in PAYMENT_STATES
            ):
                inv_line = line.object_id
                # Quando nao há produto na linha da fatura, nao e possivel
                # aplicar regras de categoria ou deducao de produto. Nesses
                # casos usa-se o price_subtotal como base direta da comissao,
                # aplicando a taxa fixa da comissao configurada no agente.
                if inv_line.product_id:
                    recomputed = line._get_commission_amount(
                        line.commission_id,
                        inv_line.price_subtotal,
                        inv_line.product_id,
                        inv_line.quantity,
                    )
                else:
                    recomputed = line._compute_amount_without_product(
                        line.commission_id, inv_line.price_subtotal
                    )
                if line.invoice_id.move_type and "refund" in line.invoice_id.move_type:
                    recomputed = -recomputed
                line.amount = recomputed or 0.0
            if line.commission_split_percent:
                line.amount *= line.commission_split_percent / 100.0
        return result

    def _compute_amount_without_product(self, commission, subtotal):
        """Calcula a comissao quando a linha da fatura nao tem produto.

        Usa o subtotal como base direta e aplica a taxa da comissao
        configurada (fixq ou section), sem deducao de produto.
        """
        self.ensure_one()
        if not commission:
            return 0.0
        if commission.commission_type == "fixed":
            return subtotal * (commission.fix_qty or 0.0) / 100.0
        elif commission.commission_type == "section":
            return commission.calculate_section(subtotal)
        elif commission.commission_type == "product":
            # Politica por item: nao há produto, entao nao há item aplicavel
            return 0.0
        elif commission.commission_type == "progressive":
            # Progressive precisa de produto para a regra de categoria
            return 0.0
        elif commission.commission_type == "coordinator":
            return 0.0
        return 0.0
