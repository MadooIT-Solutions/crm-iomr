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
                settlement.sale_order_id.prontuario if settlement.sale_order_id else False
            )


class CommissionSettlementLine(models.Model):
    _inherit = "commission.settlement.line"

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
        help="Pedido de venda que originou esta linha de comissão.",
    )
    prontuario = fields.Char(
        string="Prontuário",
        compute="_compute_prontuario",
        readonly=True,
        help="Prontuário do cliente no pedido de venda relacionado.",
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

    @api.depends(
        "invoice_agent_line_id",
        "invoice_agent_line_id.amount",
        "invoice_agent_line_id.invoice_id.payment_state",
        "invoice_agent_line_id.invoice_id.amount_total",
        "invoice_agent_line_id.invoice_id.amount_residual",
        "settlement_id.settlement_type",
    )
    def _compute_settled_amount(self):
        """Valor liquidado da linha de fechamento.

        Para fechamentos de fatura (``sale_invoice``) o valor segue o
        pagamento da fatura, não o valor faturado:

        * Fatura quitada (``paid``, ``in_payment``, ``reversed``): o
          ``settled_amount`` é o ``amount`` completo da linha de agente.
        * Fatura paga parcialmente (``partial``): a comissão é rateada
          proporcionalmente ao valor efetivamente recebido
          (``amount_total - amount_residual``) sobre o total da fatura.
        * Fatura não paga: não chega aqui porque ``_skip_settlement`` a
          afasta antes de ser incluída num fechamento.

        Para outros tipos de fechamento (CRM performance, recuperação
        trimestral, manual) o valor é o que foi gravado na criação da linha
        (herdado do OCA), sem rateio.
        """
        for line in self:
            if (
                line.settlement_id.settlement_type == "sale_invoice"
                and line.invoice_agent_line_id
            ):
                agent_line = line.invoice_agent_line_id
                invoice = agent_line.invoice_id
                base_amount = agent_line.amount or 0.0
                if invoice and invoice.payment_state == "partial" and invoice.amount_total:
                    amount_paid = invoice.amount_total - (invoice.amount_residual or 0.0)
                    ratio = amount_paid / invoice.amount_total
                    line.settled_amount = base_amount * ratio
                else:
                    line.settled_amount = base_amount
            else:
                # Tipos não-fatura: preserva o valor gravado na criação
                # (behavior padrão do OCA, que não tem _compute_settled_amount
                # efetivo). Não sobrescrevemos se o usuário editou manualmente.
                if not line.invoice_agent_line_id:
                    continue

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
