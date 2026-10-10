"""
Validacao POS-restart (somente leitura, rollback): o patch que adiciona
``object_id.order_id.credit_card_fee_amount`` ao @api.depends do
sale.order.line.agent.amount esta de fato carregado no registry que esta
rodando? Roda em memoria, nao grava nada.

  /home/iomr/venv/bin/python /home/iomr/odoo/odoo-bin shell \
      -c /home/iomr/odoo/odoo.conf -d odoo18_prod --log-level=warn --no-http \
      < crm_commissions/scripts/verify_card_fee_depends.py
"""

import logging

_logger = logging.getLogger(__name__)

try:
    # Em Odoo 18 o field._depends fica None; os depends efetivos vem do
    # METODO compute resolvido no registry (o override da classe final).
    field = env["sale.order.line.agent"]._fields["amount"]
    metodo = env.registry["sale.order.line.agent"]._compute_amount
    deps = list(getattr(metodo, "_depends", None) or [])
    tem_taxa = any("credit_card_fee_amount" in d for d in deps)

    _logger.info("=" * 78)
    _logger.info("VALIDACAO POS-RESTART - dependencia da taxa de cartao")
    _logger.info("=" * 78)
    _logger.info("  Campo: sale.order.line.agent.amount (store=%s)", field.store)
    _logger.info("  Depends do metodo compute efetivo:")
    for d in deps:
        marca = "   <== PATCH NOVO" if "credit_card_fee_amount" in d else ""
        _logger.info("      - %s%s", d, marca)
    _logger.info("")
    _logger.info("  Patch carregado? %s", "SIM" if tem_taxa else "NAO (codigo antigo ainda no ar)")

    # Sanidade: o metodo da deducao da taxa existe e e o novo.
    agent = env["sale.order.line.agent"]
    tem_metodo = hasattr(agent, "_get_card_fee_amount")
    _logger.info("  Metodos novos do mixin: _get_card_fee_amount=%s", tem_metodo)

    # Bate-papo: mostra o S00219 ja consistente (dado ja corrigido antes).
    order = env["sale.order"].search([("name", "=", "S00219")], limit=1)
    if order:
        soma = sum(order.order_line.mapped("agent_ids.amount"))
        _logger.info("")
        _logger.info("  S00219: commission_total gravado R$ %.4f | soma real R$ %.4f",
                     order.commission_total, soma)
        _logger.info("          taxa de cartao R$ %.2f", order.credit_card_fee_amount)

    env.cr.rollback()
    if not tem_taxa:
        _logger.warning("  ATENCAO: dependencia NO ESTADO ANTIGO - reinicio nao pegou o patch.")

except Exception as e:
    _logger.error("Erro: %s", e)
    import traceback
    _logger.error(traceback.format_exc())
    env.cr.rollback()
