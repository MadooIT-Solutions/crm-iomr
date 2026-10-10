"""
DIAGNOSTICO (somente leitura, transacao com rollback): por que a comissao do
pedido S00219 nao muda quando a taxa de cartao e alterada.

Compara o valor GRAVADO de cada linha de agente com o valor que o motor de
comissao calcula HOJE (com a taxa de cartao atual) e com o valor que ele
calcularia se a taxa fosse ZERO - tudo em memoria, sem gravar.

Rodar (somente leitura; da raiz do repo, com o odoo.conf do servidor):
  /home/iomr/venv/bin/python /home/iomr/odoo/odoo-bin shell \
      -c /home/iomr/odoo/odoo.conf -d odoo18_prod --log-level=warn --no-http \
      < crm_commissions/scripts/check_card_fee_commission.py
"""

import logging

_logger = logging.getLogger(__name__)

try:
    order = env["sale.order"].search([("name", "=", "S00219")], limit=1)
    if not order:
        raise Exception("Pedido S00219 nao encontrado.")

    _logger.info("=" * 78)
    _logger.info("PEDIDO %s (id %s) - taxa de cartao atual: R$ %.2f",
                 order.name, order.id, order.credit_card_fee_amount)
    _logger.info("=" * 78)
    for fl in order.credit_card_fee_line_ids:
        _logger.info("  Linha de taxa %-3s %-30s percent=%-6s amount=%10.2f fee_amount=%8.2f",
                     fl.id, fl.payment_method_id.name, fl.fee_percent,
                     fl.amount, fl.fee_amount)
    _logger.info("  commission_total gravado no pedido: R$ %.4f", order.commission_total)

    AgentCls = type(env["sale.order.line.agent"])
    taxa_original = AgentCls._get_card_fee_amount

    def calcular(ag):
        """O mesmo caminho do _compute_amount, sem gravar."""
        line = ag.object_id
        comm = ag.commission_id
        if comm.commission_type == "product":
            amount = ag._get_single_commission_amount(
                comm, line.price_subtotal, line.product_id, line.product_uom_qty
            )
        else:
            amount = ag._get_commission_amount(
                comm, line.price_subtotal, line.product_id, line.product_uom_qty
            )
        return amount * (ag.commission_split_percent or 100.0) / 100.0

    agents = env["sale.order.line.agent"].search(
        [("object_id.order_id", "=", order.id)], order="object_id, id"
    )

    # Cenario A: com a taxa de cartao atual (comportamento real do modulo)
    cenario_com = {ag.id: calcular(ag) for ag in agents}

    # Cenario B: taxa de cartao zerada (simula o "antes" da edicao da taxa)
    AgentCls._get_card_fee_amount = lambda self: 0.0
    cenario_sem = {ag.id: calcular(ag) for ag in agents}
    AgentCls._get_card_fee_amount = taxa_original

    _logger.info("")
    _logger.info("=" * 78)
    _logger.info("LINHAS DE AGENTE: gravado vs recalculado")
    _logger.info("=" * 78)
    _logger.info("  %-7s %-8s %-24s %-12s %10s %10s %10s",
                 "linha", "so_line", "agente", "politica", "gravado", "c/taxa", "s/taxa")
    soma_gravado = soma_com = soma_sem = 0.0
    for ag in agents:
        line = ag.object_id
        com = cenario_com[ag.id]
        sem = cenario_sem[ag.id]
        soma_gravado += ag.amount
        soma_com += com
        soma_sem += sem
        marca = "" if abs(ag.amount - com) < 0.005 else "  <<< DIVERGE do calculo atual"
        _logger.info("  %-7s %-8s %-24s %-12s %10.2f %10.2f %10.2f%s",
                     ag.id, line.id, ag.agent_id.name[:24],
                     ag.commission_id.commission_type, ag.amount, com, sem, marca)

    _logger.info("")
    _logger.info("  SOMA gravado (banco)      : R$ %.4f", soma_gravado)
    _logger.info("  SOMA recalc. COM a taxa   : R$ %.4f  (delta p/ gravado: R$ %.4f)",
                 soma_com, soma_com - soma_gravado)
    _logger.info("  SOMA recalc. SEM a taxa   : R$ %.4f", soma_sem)

    _logger.info("")
    _logger.info("=" * 78)
    _logger.info("POR QUE NAO RECALCULA SOZINHO")
    _logger.info("=" * 78)
    field = env["sale.order.line.agent"]._fields["amount"]
    _logger.info("  Campo 'amount' de sale.order.line.agent:")
    _logger.info("    compute = %s (store=True)", field.compute)
    _logger.info("    depends = %s", list(getattr(field, "depends", [])))
    _logger.info("    'credit_card_fee_amount' esta entre as dependencias? %s",
                 any("credit_card_fee" in d for d in getattr(field, "depends", [])))
    _logger.info("  Campo 'commission_total' de sale.order:")
    ofield = env["sale.order"]._fields["commission_total"]
    _logger.info("    depends = %s", list(getattr(ofield, "depends", [])))
    _logger.info("")
    _logger.info("  Ultima alteracao da linha de taxa: %s",
                 max(env["sale.order.credit.card.fee.line"].search(
                     [("sale_order_id", "=", order.id)]).mapped("write_date")))
    _logger.info("  Ultima alteracao das linhas de agente: %s",
                 max(agents.mapped("write_date")))

    env.cr.rollback()

except Exception as e:
    _logger.error("Erro: %s", e)
    import traceback
    _logger.error(traceback.format_exc())
    env.cr.rollback()
