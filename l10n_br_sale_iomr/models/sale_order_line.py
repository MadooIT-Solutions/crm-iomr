# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # No l10n_br_sale o campo abaixo é um Many2one simples, sem compute: a
    # operação do cabeçalho só chega à linha via contexto na criação. Linhas
    # criadas antes de marcar a operação no pedido (ou por outro caminho, como
    # importação) ficam sem operação e, consequentemente, sem "Linha de
    # operação". Aqui o campo passa a ser compute stored a partir do cabeçalho,
    # preenchendo apenas as linhas vazias -- valor digitado na linha é
    # respeitado.
    fiscal_operation_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.operation",
        compute="_compute_fiscal_operation_id",
        store=True,
        readonly=False,
        precompute=True,
    )

    @api.depends("order_id.fiscal_operation_id")
    def _compute_fiscal_operation_id(self):
        for line in self:
            # A leitura do próprio campo dentro do compute é segura para
            # stored fields: retorna o valor atual (vazio ou o digitado
            # manualmente) sem reentrar no compute.
            line.fiscal_operation_id = (
                line.fiscal_operation_id or line.order_id.fiscal_operation_id
            )
