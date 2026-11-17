# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Recria as linhas de agente de fatura que faltavam no fechamento.

Sintoma: o fechamento de comissões de uma orientadora (ex.: Thaisy) não traz
comissões de pedidos já faturados/pagos (ex.: S00580). Causa: quando a regra
de comissão é criada depois da fatura, só os agentes da linha do pedido são
recalculados; a linha da fatura fica sem agente e o fechamento, que lê apenas
os agentes da fatura, não vê a comissão.

A migração ``18.0.2.10.2`` faz a mesma reparação durante o upgrade do módulo.
Este script serve para aplicar a correção em produção sem precisar atualizar o
módulo e é idempotente: apenas cria agentes faltantes, nunca altera linhas já
existentes (em especial as liquidadas).

Uso (odoo shell, da raiz do repo):

    /home/iomr/venv/bin/python /home/iomr/odoo/odoo-bin shell \
        -c /home/iomr/odoo/odoo.conf -d odoo18_prod --log-level=info --no-http \
        < crm_commissions/scripts/fix_missing_invoice_agents.py

Por padrão é DRY_RUN: nada é gravado. Confira o relatório, mude ``DRY_RUN``
para ``False`` e rode de novo. Depois disso, refaça o fechamento do período
afetado para que as comissões recuperadas entrem na liquidação.
"""

import importlib.util
import logging
import os

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

DRY_RUN = True
MIGRATION_VERSION = "18.0.2.10.2"
# Pedido usado apenas como conferência no relatório (opcional).
CHECK_ORDER = "S00580"


def _load_migration():
    """Carrega a função de reparo que está na migração do módulo."""
    from odoo.addons import crm_commissions

    path = os.path.join(
        os.path.dirname(crm_commissions.__file__),
        "migrations",
        MIGRATION_VERSION,
        "post-migrate.py",
    )
    spec = importlib.util.spec_from_file_location("crm_commissions_fix_agents", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(env, order_name):
    """Mostra o estado dos agentes das faturas do pedido de conferência."""
    order = env["sale.order"].search([("name", "=", order_name)], limit=1)
    if not order:
        return
    lines = env["account.move.line"].search(
        [
            ("sale_line_ids", "in", order.order_line.ids),
            ("display_type", "=", "product"),
        ]
    )
    agents = env["account.invoice.line.agent"].search(
        [("object_id", "in", lines.ids)]
    )
    print(f"  {order_name}: {len(agents)} agente(s) em {len(lines)} linha(s) de fatura")
    for agent in agents:
        print(
            f"    {(agent.agent_id.name or '-')[:24]:24} "
            f"{(agent.commission_id.name or '-')[:40]:40} "
            f"amount={agent.amount:10.4f} settled={agent.settled}"
        )


def run(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})
    migration = _load_migration()
    created = migration._backfill_missing_invoice_agents(env)

    print("=" * 78)
    print(f"REPARO DAS LINHAS DE AGENTE DE FATURA (DRY_RUN={DRY_RUN})")
    print(f"  linhas de agente criadas: {created}")
    if CHECK_ORDER:
        _report(env, CHECK_ORDER)
    print("=" * 78)
    if DRY_RUN:
        cr.rollback()
        print("DRY_RUN: nenhuma alteração gravada (rollback).")
    else:
        cr.commit()
        print("Alterações gravadas. Refaça o fechamento do período afetado.")


try:
    run(env.cr)  # noqa: F821 - provided by odoo shell
except Exception:
    _logger.exception("Falha no reparo das linhas de agente de fatura")
    env.cr.rollback()  # noqa: F821 - provided by odoo shell
    raise
