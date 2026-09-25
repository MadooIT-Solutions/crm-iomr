# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Sincroniza commission.sale a partir dos pedidos de venda confirmados.

O menu Repasses/Vendas é alimentado por commission.sale. Sem registros o menu
fica vazio mesmo com o commission.member criado. Este script varre os pedidos
confirmados (state 'sale'/'done') onde a orientadora figura como agente
(sale.order.line.agent_ids) e cria/atualiza um commission.sale por
(membro orientadora, pedido).

A sincronização também acontece automaticamente no _action_confirm do
sale.order (override no módulo crm_commissions); este script serve para
retroalimentar os pedidos já existentes (idempotente, pode rodar à vontade).
O calculado é aproximado (categoria de venda, tipo de cirurgia e valores de
LIO por nome de categoria de produto) — os gestores podem ajustar os campos
manualmente na tela Vendas depois.

Uso (odoo shell):
    from sync_commission_sales import run
    run(env.cr)
"""

from odoo import SUPERUSER_ID, api

# Estados de pedido que entram na sincronização.
SYNC_STATES = ("sale", "done")


def run(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Sale = env["commission.sale"]

    orders = env["sale.order"].search(
        [
            ("state", "in", list(SYNC_STATES)),
            ("partner_agent_ids.type_partner", "=", "orientadora"),
        ],
        order="date_order",
    )
    total_orders = len(orders)
    total_sales = 0
    created = 0
    updated = 0
    for order in orders:
        before = Sale.search_count(
            [("source_order_id", "=", order.id)]
        )
        order._sync_commission_sales_from_orders()
        after = Sale.search_count([("source_order_id", "=", order.id)])
        if after > before:
            created += after - before
        elif after and after == before:
            updated += 1
        total_sales += after

    print("Pedidos com agente orientadora: %d" % total_orders)
    print("commission.sale vinculadas a pedidos: %d" % total_sales)
    print("Criadas agora: %d | Reatualizadas: %d" % (created, updated))

    members = env["commission.member"].search(
        [("member_type", "=", "orientadora")], order="name"
    )
    print("Vendas por orientadora (todas, inclusive manuais):")
    for m in members:
        cnt = Sale.search_count(
            [
                ("owner_member_id", "=", m.id),
                ("status", "in", ("confirmed", "invoiced")),
            ]
        )
        print("  - %s [%s]: %d vendas" % (m.name, m.user_id.login or "-", cnt))

    cr.commit()
    return {
        "orders_scanned": total_orders,
        "sales_total": total_sales,
        "sales_created": created,
        "sales_updated": updated,
    }