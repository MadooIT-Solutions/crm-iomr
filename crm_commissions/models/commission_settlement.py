# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class CommissionSettlement(models.Model):
    _inherit = "commission.settlement"

    settlement_type = fields.Selection(
        selection_add=[
            ("crm_performance", "CRM Performance"),
            ("crm_quarterly_recovery", "CRM Quarterly Recovery"),
        ],
        ondelete={
            "crm_performance": "set default",
            "crm_quarterly_recovery": "set default",
        },
    )
    target_id = fields.Many2one(
        "crm.commission.target",
        string="Related target",
    )
    is_crm_score = fields.Float(string="IS-CRM score")
    performance_pct = fields.Float(string="Performance (%)")
    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Pedido de venda",
        compute="_compute_sale_order_info",
        readonly=True,
        help="Pedido de venda relacionado às linhas desta liquidação "
        "(quando houver um único pedido).",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Paciente",
        compute="_compute_sale_order_info",
        readonly=True,
    )
    prontuario = fields.Char(
        string="Prontuário",
        compute="_compute_sale_order_info",
        readonly=True,
        help="Prontuário do cliente no pedido de venda relacionado.",
    )


    @api.depends("line_ids.sale_order_id", "line_ids.sale_order_id.prontuario")
    def _compute_sale_order_info(self):
        for settlement in self:
            orders = settlement.line_ids.mapped("sale_order_id")
            settlement.sale_order_id = orders[:1] if len(orders) == 1 else False
            settlement.prontuario = (
                settlement.sale_order_id.prontuario
                if settlement.sale_order_id
                else False
            )
            settlement.partner_id = (
                settlement.sale_order_id.partner_id
                if settlement.sale_order_id
                else False
            )

class CommissionSettlementLine(models.Model):
    _inherit = "commission.settlement.line"
    # Ordem padrão das linhas na liquidação: data do pagamento, número do
    # pedido de venda e, como desempate, a própria linha. ``sale_order_name``
    # é armazenada porque `_order` é SQL e não aceita campos computed.
    _order = "date, sale_order_name, id"

    target_id = fields.Many2one(
        "crm.commission.target",
        string="Related target",
        index=True,
        copy=False,
        readonly=True,
        ondelete="set null",
    )
    quarterly_bonus_id = fields.Many2one(
        "crm.commission.quarterly.bonus",
        string="Related quarterly bonus",
        index=True,
        copy=False,
        readonly=True,
        ondelete="set null",
        help="Bônus trimestral que originou esta linha de recuperação.",
    )
    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Pedido de venda",
        compute="_compute_sale_order_id",
        readonly=True,
        store=True,
        help="Pedido de venda que originou esta linha de comissão.",
    )
    sale_order_name = fields.Char(
        string="Número do pedido de venda",
        related="sale_order_id.name",
        readonly=True,
        store=True,
        index=True,
        help="Número do pedido de venda, usado para ordenar as linhas.",
    )
    prontuario = fields.Char(
        string="Prontuário",
        compute="_compute_prontuario",
        readonly=True,
        help="Prontuário do cliente no pedido de venda relacionado.",
    )

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Paciente",
        compute="_compute_partner_id",
        readonly=True,
    )
    # ``invoice_line_id`` was a stored related field on
    # ``invoice_agent_line_id.object_id``. The FK to the agent row is
    # ``ON DELETE SET NULL``, so recomputing the invoice agents erased the
    # origin of already-closed lines. Keeping it as an independent field,
    # written once when the settlement line is created, lets the closing
    # recognise an invoice line that was already closed even after its agent
    # row was recreated and avoid paying the commission twice.
    invoice_line_id = fields.Many2one(
        comodel_name="account.move.line",
        string="Source invoice line",
        index=True,
        readonly=True,
        copy=False,
        ondelete="set null",
        related=False,
    )
    invoice_base_amount = fields.Monetary(
        string="Commission base",
        readonly=True,
        copy=False,
        currency_field="currency_id",
        help="Commission base frozen when the line was closed. Keeping it "
        "separate from the source agent amount lets partial payments adjust "
        "only the paid ratio, without the historical value being zeroed when "
        "the source line is recomputed.",
    )
    invoice_amount = fields.Monetary(
        string="Valor da Fatura",
        compute="_compute_invoice_payment_amounts",
        readonly=True,
        currency_field="currency_id",
        help="Valor total da fatura de origem desta linha de comissão.",
    )
    amount_paid = fields.Monetary(
        string="Valor Pago",
        compute="_compute_invoice_payment_amounts",
        readonly=True,
        currency_field="currency_id",
        help="Valor efetivamente pago da fatura de origem desta linha.",
    )

    @api.depends(
        "invoice_agent_line_id",
        "invoice_agent_line_id.invoice_id",
        "invoice_agent_line_id.invoice_id.amount_total",
        "invoice_agent_line_id.invoice_id.amount_residual",
    )
    def _compute_invoice_payment_amounts(self):
        """Total e valor pago da fatura de origem da linha.

        O valor pago espelha o rateio usado em ``_compute_settled_amount``:
        ``amount_total - amount_residual`` da fatura. Linhas que não vêm de
        fatura (CRM, fechamentos manuais) ficam com os valores zerados.
        """
        for line in self:
            invoice = line.invoice_agent_line_id.invoice_id
            line.invoice_amount = invoice.amount_total if invoice else 0.0
            line.amount_paid = (
                invoice.amount_total - (invoice.amount_residual or 0.0)
                if invoice
                else 0.0
            )

    @api.depends(
        "invoice_agent_line_id",
        "invoice_agent_line_id.payment_date",
        "settlement_id.settlement_type",
    )
    def _compute_date(self):
        """Use the payment date on invoice settlements.

        The OCA compute takes ``invoice_date``; for a commission closed after
        payment, the meaningful date is when the invoice was paid.
        """
        super()._compute_date()
        for line in self:
            agent_line = line.invoice_agent_line_id
            if agent_line and line.settlement_id.settlement_type == "sale_invoice":
                line.date = agent_line.payment_date or agent_line.invoice_date

    @api.depends(
        "invoice_agent_line_id",
        "invoice_agent_line_id.object_id",
        "invoice_agent_line_id.object_id.sale_line_ids",
    )
    def _compute_sale_order_id(self):
        """Liga a linha fechada ao pedido de venda de onde ela veio.

        A linha de settlement nasce do agente da linha da fatura
        (``invoice_agent_line_id``), e ``_get_source_sale_order`` sobe dela
        até o pedido: a linha da fatura carrega o pedido quando foi gerada
        direto dele, ou alcança o pedido pelas linhas de venda
        (``sale_line_ids``) que a faturaram.

        As linhas de origem CRM (``target_id`` e ``quarterly_bonus_id``)
        fecham um período inteiro, com vendas de vários pedidos, então não
        têm um pedido único e ficam sem o campo.
        """
        for line in self:
            agent_line = line.invoice_agent_line_id
            line.sale_order_id = (
                agent_line._get_source_sale_order() if agent_line else False
            )

    @api.depends("sale_order_id.prontuario")
    def _compute_prontuario(self):
        for line in self:
            line.prontuario = line.sale_order_id.prontuario or False

    @api.depends("sale_order_id.partner_id")
    def _compute_prontuario(self):
        for line in self:
            line.partner_id = line.sale_order_id.partner_id or False

    @api.depends(
        "invoice_agent_line_id",
        "invoice_agent_line_id.amount",
        "invoice_agent_line_id.invoice_id.payment_state",
        "invoice_agent_line_id.invoice_id.amount_total",
        "invoice_agent_line_id.invoice_id.amount_residual",
        "invoice_base_amount",
        "settlement_id.settlement_type",
    )
    def _compute_settled_amount(self):
        """Valor liquidado da linha de fechamento.

        Para fechamentos de fatura (``sale_invoice``) a base é a comissão do
        agente no pedido rateada pelo valor faturado das linhas **desse
        agente** (ver ``account.invoice.line.agent._get_settlement_base_amount``),
        e o valor liquidado segue o pagamento da fatura:

        * Fatura quitada (``paid``, ``in_payment``, ``reversed``): o
          ``settled_amount`` é a base completa da linha de fechamento.
        * Fatura paga parcialmente (``partial``): a base é rateada
          proporcionalmente ao valor efetivamente recebido
          (``amount_total - amount_residual``) sobre o total da fatura.
        * Fatura não paga: não chega aqui porque ``_skip_settlement`` a
          afasta antes de ser incluída num fechamento.

        A base é congelada em ``invoice_base_amount`` na criação (e a
        migração faz o backfill das linhas antigas), de modo que um recálculo
        posterior do ``amount`` do agente não altera o valor já fechado, e um
        desconto aplicado só na fatura reduz a comissão na mesma proporção.

        Para outros tipos de fechamento (CRM performance, recuperação
        trimestral, manual) o valor é o que foi gravado na criação da linha
        (herdado do OCA), sem rateio.
        """
        for line in self:
            # A settlement that was already invoiced is a closed accounting
            # fact: later payments must not silently rewrite its value (the
            # commission invoice would be left behind). Keep its history.
            if line.settlement_id.state != "settled":
                line.settled_amount = line.settled_amount
                continue
            agent_line = line.invoice_agent_line_id
            if (
                line.settlement_id.settlement_type != "sale_invoice"
                or not agent_line
            ):
                # Tipos não-fatura: preserva o valor gravado na criação.
                line.settled_amount = line.settled_amount
                continue
            invoice = agent_line.invoice_id
            base_amount = (
                line.invoice_base_amount
                or agent_line._get_settlement_base_amount()
            )
            ratio = 1.0
            if (
                invoice
                and invoice.payment_state == "partial"
                and invoice.amount_total
            ):
                amount_paid = invoice.amount_total - (
                    invoice.amount_residual or 0.0
                )
                ratio = max(0.0, min(amount_paid / invoice.amount_total, 1.0))
            line.settled_amount = base_amount * ratio

    def action_recompute_settled_amount(self):
        """Recalcula o settled_amount de linhas de liquidacao e de fechamento.

        Usado para corrigir registros ja existentes que foram fechados antes
        das correcoes de rateio/origem ou com indicadores do CRM
        desatualizados. Somente fechamentos ainda nao faturados
        (``state == "settled"``) sao recalculados: um fechamento faturado e
        fato contabil e nao pode ser reescrito.

        * Fatura (``sale_invoice``): a base e refeita por
          ``_get_settlement_base_amount`` (comissao do agente no pedido
          rateada pelo valor faturado das linhas do agente) e congelada em
          ``invoice_base_amount``. Fatura quitada paga a base completa;
          fatura paga parcialmente rateia pelo percentual recebido
          (``valor_pago / total_fatura``).
        * Performance do CRM (``crm_performance``): recalcula a comissao a
          partir da meta, com os indicadores mais recentes (ultimo IS-CRM do
          mes de fechamento e performance (%) da meta).
        * Recuperacao trimestral (``crm_quarterly_recovery``): repoe a
          comissao perdida recuperada no bonus trimestral.
        """
        for line in self:
            if line.settlement_id.state != "settled":
                continue
            settlement_type = line.settlement_id.settlement_type
            if settlement_type == "crm_performance":
                if line.target_id:
                    line.settled_amount = (
                        line.target_id._calculate_crm_performance_commission()
                    )
                continue
            if settlement_type == "crm_quarterly_recovery":
                if line.quarterly_bonus_id:
                    line.settled_amount = (
                        line.quarterly_bonus_id.lost_commission_recovered
                    )
                continue
            if settlement_type != "sale_invoice" or not line.invoice_agent_line_id:
                continue
            agent_line = line.invoice_agent_line_id
            invoice = agent_line.invoice_id
            base_amount = agent_line._get_settlement_base_amount()
            if not base_amount:
                # Sem base confiável, não zera um valor histórico.
                continue
            line.invoice_base_amount = base_amount
            if (
                invoice
                and invoice.payment_state == "partial"
                and invoice.amount_total
            ):
                amount_paid = invoice.amount_total - (
                    invoice.amount_residual or 0.0
                )
                ratio = max(0.0, min(amount_paid / invoice.amount_total, 1.0))
                line.settled_amount = base_amount * ratio
            else:
                line.settled_amount = base_amount
        return True

    def action_open_sale_order(self):
        """Abre o pedido de venda relacionado a esta linha."""
        self.ensure_one()
        if not self.sale_order_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": self.sale_order_id.display_name,
            "res_model": "sale.order",
            "view_mode": "form",
            "res_id": self.sale_order_id.id,
            "target": "current",
        }
