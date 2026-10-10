"""
Recalcula as comissoes gravadas que ficaram DEFASADAS em relacao a taxa de
cartao.

CAUSA (corrigida no codigo em crm_commissions/models/sale_order.py):
  sale.order.line.agent.amount e um campo calculado e ARMAZENADO. O Odoo so
  o recalcula quando um dos campos do @api.depends muda, e a taxa de cartao
  (object_id.order_id.credit_card_fee_amount) nao estava na lista. Assim,
  editar a taxa de um pedido alterava o valor cobrado do paciente, mas as
  comissoes continuavam com o valor de quando foram calculadas da ultima vez
  (S00219: R$ 8.561,35 gravado em vez de R$ 8.318,77).

  O patch do codigo resolve daqui para FREnte (edicao da taxa passa a
  disparar o recalculo). Este script conserta o PASSADO: as linhas ja
  gravadas com o valor antigo.

Escopo: linhas de agente de PEDIDOS (empresa 1) com taxa de cartao > 0 cuja
politica de comissao deduz a taxa (deduct_card_fee + base net_amount_deduction)
- que sao exatamente as linhas cujo valor pode estar desatualizado.

O lado da fatura (account.invoice.line.agent) NAO e tocado: as faturas ja
liquidadas nao podem ter a comissao alterada (o OCA levanta "You can't modify
a settled line") e a fatura e um fato contabil fechado. Como as faturas sao
geradas a partir do pedido, o fluxo novo ja sai correto.

Modo de usar (dry-run por padrao; as gravacoes sao feitas na transacao e
revertidas por rollback; rodar da raiz do repo, com o odoo.conf do servidor):
  /home/iomr/venv/bin/python /home/iomr/odoo/odoo-bin shell \
      -c /home/iomr/odoo/odoo.conf -d odoo18_prod --log-level=info --no-http \
      < crm_commissions/scripts/fix_card_fee_commission_recompute.py

Sempre faca backup antes de aplicar (DRY_RUN = False).
"""

import logging

_logger = logging.getLogger(__name__)

# === CONFIG ===
DRY_RUN = False  # Aplicado em 2026-10-10 (backup_20261010_035711_pre_comissao_taxa.dump)
COMPANY_ID = 1

try:
    Agent = env["sale.order.line.agent"]

    lines = Agent.search(
        [
            ("object_id.order_id.company_id", "=", COMPANY_ID),
            ("object_id.order_id.credit_card_fee_amount", ">", 0),
            ("commission_id.deduct_card_fee", "=", True),
            ("commission_id.amount_base_type", "=", "net_amount_deduction"),
        ],
        order="object_id, id",
    )
    orders = lines.mapped("object_id.order_id")

    _logger.info("=" * 78)
    _logger.info("RECALCULO DE COMISSAO x TAXA DE CARTAO")
    _logger.info("=" * 78)
    _logger.info("  Pedidos com taxa de cartao e politica que deduz: %s", len(orders))
    _logger.info("  Linhas de agente no escopo: %s", len(lines))

    antes = {line.id: line.amount for line in lines}
    soma_antes = sum(antes.values())
    por_pedido_antes = {o.id: sum(o.order_line.mapped("agent_ids.amount")) for o in orders}
    _logger.info("  Soma das comissoes ANTES: R$ %.4f", soma_antes)

    # ------------------------------------------------------------------
    # Forca o recalculo (o campo e stored; add_to_compute marca para
    # recalcular e o flush executa o compute de verdade)
    # ------------------------------------------------------------------
    _logger.info("")
    _logger.info("=" * 78)
    _logger.info("Forcando o recalculo do amount das linhas de agente")
    _logger.info("=" * 78)
    env.add_to_compute(Agent._fields["amount"], lines)
    env.flush_all()
    env.invalidate_all()

    lines = Agent.browse(sorted(antes))
    orders = lines.mapped("object_id.order_id")
    soma_depois = sum(lines.mapped("amount"))
    por_pedido_depois = {o.id: sum(o.order_line.mapped("agent_ids.amount")) for o in orders}

    alteradas = [line for line in lines if abs(line.amount - antes[line.id]) >= 0.005]
    _logger.info("  Linhas com valor alterado: %s de %s", len(alteradas), len(lines))
    for line in alteradas:
        _logger.info(
            "      pedido %-9s linha SO %-6s %-24s %-12s R$ %10.2f -> R$ %10.2f (delta R$ %8.2f)",
            line.object_id.order_id.name,
            line.object_id.id,
            line.agent_id.name[:24],
            line.commission_id.commission_type,
            antes[line.id],
            line.amount,
            line.amount - antes[line.id],
        )

    _logger.info("")
    _logger.info("  Pedidos com commission_total alterado:")
    for order in orders:
        delta = por_pedido_depois[order.id] - por_pedido_antes[order.id]
        if abs(delta) >= 0.005:
            _logger.info("      %-9s R$ %10.4f -> R$ %10.4f (delta R$ %9.2f)",
                         order.name, por_pedido_antes[order.id], por_pedido_depois[order.id], delta)

    _logger.info("")
    _logger.info("  Soma das comissoes DEPOIS: R$ %.4f (delta R$ %.4f)",
                 soma_depois, soma_depois - soma_antes)

    # ------------------------------------------------------------------
    # Pendencias: faturas ja emitidas desses pedidos
    # ------------------------------------------------------------------
    invoices = env["account.move"].search(
        [
            ("invoice_user_id", "!=", False),
            ("state", "!=", "cancel"),
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("line_ids.sale_line_ids.order_id", "in", orders.ids),
        ]
    )
    invoice_agents = env["account.invoice.line.agent"].search(
        [("object_id.move_id", "in", invoices.ids)]
    )
    _logger.info("")
    _logger.info("=" * 78)
    _logger.info("PENDENCIA (nao alterada por este script)")
    _logger.info("=" * 78)
    _logger.info("  Faturas ja emitidas dos pedidos com taxa: %s", len(invoices))
    _logger.info("  Linhas de agente de fatura: %s (nao recalculadas; a fatura e", len(invoice_agents))
    _logger.info("  fato contabil fechado e o OCA bloqueia alteracao de comissao")
    _logger.info("  ja liquidada). As faturas novas saem corretas, pois copiam")
    _logger.info("  as linhas do pedido ja recalculadas.")

    if DRY_RUN:
        _logger.info("")
        _logger.info("=" * 78)
        _logger.info("RESUMO DRY-RUN: as gravacoes foram feitas NA TRANSACAO e revertidas")
        _logger.info("pelo rollback - nada foi persistido no banco.")
        _logger.info("Para aplicar, mude DRY_RUN = False.")
        _logger.info("=" * 78)
        env.cr.rollback()
    else:
        env.cr.commit()
        _logger.info("")
        _logger.info("=" * 78)
        _logger.info("CONCLUIDO e COMMITADO.")
        _logger.info("=" * 78)

except Exception as e:
    _logger.error("Erro: %s", e)
    import traceback
    _logger.error(traceback.format_exc())
    env.cr.rollback()
