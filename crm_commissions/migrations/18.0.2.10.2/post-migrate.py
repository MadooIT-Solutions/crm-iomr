# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Recria linhas de agente de fatura que faltavam no fechamento.

Quando uma regra de comissão é criada/alterada depois que a fatura já foi
emitida (ex.: a fixa de 1% das categorias extras, criada em 27/10, para a
fatura do pedido S00580 de 16/10), os agentes da linha do pedido são
recalculados, mas os da linha da fatura não. O fechamento lê apenas os agentes
da fatura e, sem a linha, a comissão desaparece silenciosamente.

O código passa a depender também dos agentes das linhas de venda vinculadas,
o que corrige faturas novas. Esta migração cobre as faturas já gravadas: ela
apenas ADICIONA as linhas de agente faltantes, sem alterar ou apagar linhas
existentes (em especial as já liquidadas), e é idempotente.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def _backfill_missing_invoice_agents(env):
    """Cria as linhas de agente de fatura faltantes a partir dos pedidos."""
    lines = (
        env["account.move.line"]
        .sudo()
        .search(
            [
                ("move_id.move_type", "in", ("out_invoice", "out_refund")),
                ("move_id.state", "!=", "cancel"),
                ("display_type", "=", "product"),
                ("sale_line_ids", "!=", False),
            ]
        )
    )
    created = lines._backfill_missing_agents_from_sale_lines()
    _logger.info(
        "Linhas de agente de fatura recriadas a partir dos pedidos: %s "
        "(em %s linhas de fatura)",
        created,
        len(lines),
    )
    return created


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _backfill_missing_invoice_agents(env)
