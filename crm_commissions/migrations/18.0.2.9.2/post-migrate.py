# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Aplica a Comissão Fixa 1% nas categorias extras das orientadoras.

A comissão progressiva foi restringida à categoria LIO. Sem uma regra
``commission.agent.rule`` ligando cada orientadora às categorias extras
(TAXA DE SALA, MAT/MED, COLA ORGANICA e TAXA DE EQUIPAMENTO), as linhas
dessas categorias passariam a não pagar nada. Esta migração:

1. Cria/atualiza a regra de cada orientadora para a comissão fixa de 1%;
2. Recalcula todas as linhas de pedido de venda, para que as linhas já
   existentes passem a usar a comissão correta de cada categoria;
3. Atualiza o total de comissão dos pedidos afetados.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def recompute_sale_order_lines(env):
    """Rebuild the agents of every product line of every sale order."""
    lines = env["sale.order.line"].search(
        [("display_type", "=", False), ("product_id", "!=", False)]
    )
    recomputed = 0
    failed = 0
    for line in lines:
        try:
            line._compute_agent_ids()
            recomputed += 1
        except Exception as exc:  # noqa: BLE001 - one bad line must not abort
            failed += 1
            _logger.warning(
                "Orientadora extras: falha ao recalcular a linha %s do pedido "
                "%s: %s",
                line.id,
                line.order_id.name,
                exc,
            )
    env.flush_all()

    orders = lines.order_id
    if orders:
        env.add_to_compute(
            env["sale.order"]._fields["commission_total"], orders
        )
        env.flush_all()
        env.invalidate_all()
    return {
        "lines": len(lines),
        "recomputed": recomputed,
        "failed": failed,
        "orders": len(orders),
    }


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    rules = env["commission.agent.rule"]._ensure_orientadora_extras_rules()
    env.flush_all()
    result = recompute_sale_order_lines(env)
    _logger.info(
        "Orientadora extras: %(created)s regra(s) criada(s), "
        "%(updated)s atualizada(s), %(categories)s categoria(s); "
        "%(recomputed)s/%(lines)s linha(s) de venda recalculada(s) em "
        "%(orders)s pedido(s), %(failed)s falha(s)",
        {**rules, **result},
    )
    cr.commit()
