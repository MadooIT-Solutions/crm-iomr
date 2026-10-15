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
