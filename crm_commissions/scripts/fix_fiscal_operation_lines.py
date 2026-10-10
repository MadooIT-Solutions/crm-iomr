"""
Pendencia: 35 linhas de pedido de venda ficaram SEM fiscal_operation_line_id.

Causa: tanto o NCM da LINHA (campo gravado, calculado a partir do produto)
quanto o fiscal_operation_line_id dependem apenas de "product_id" no
@api.depends. Ou seja: cadastrar/atualizar o NCM no PRODUTO nunca propaga
para as linhas ja existentes. E preciso forcar o recalculo.

Este script:
  1. Forca o recalculo dos campos fiscais vindos do produto nas linhas
     (ncm_id, cest_id, nbm_id, fiscal_type, tax_icms_or_issqn, ...).
  2. Forca o recalculo do fiscal_operation_line_id.
  3. Deixa os impostos fiscais (fiscal_tax_ids) e os valores recalcularem.
  4. Relata o que continua sem operacao e por que.

Escopo: todas as linhas de produto que ja tem Operacao Fiscal.

RESULTADO (aplicado em 2026-10-08):
  - 11 linha(s) passaram a resolver a operacao (1453 -> 1464 de 1488).
    As 11 foram para "Venda nao Contribuinte", pois o parceiro dessas linhas
    e nao contribuinte (ind_ie_dest=9).
  - Nenhum valor total mudou (delta R$ 0,00): o NCM dos produtos nao altera
    os valores, apenas a classificacao fiscal (CFOP/NCM) do documento.

PENDENCIA REAL RESTANTE: 10 linha(s) de 2 produtos "LENTE DE CONTATO
TERAPEUTICA" (product.product 5678 e 5679 / product.template 5689 e 5691),
que estao com NCM e fiscal_type VAZIOS. Sem o NCM o domain da Operacao
Fiscal nao casa com nenhuma linha da operacao "Venda". Preencher NCM +
Fiscal Type (04 = mercadoria) nesses 2 produtos e rodar este script de novo.

As 14 linhas de "sem produto" sao linhas de ADIANTAMENTO (is_downpayment),
que por natureza nao tem produto e NAO precisam de operacao fiscal: o
l10n_br_sale inclui as linhas de adiantamento na fatura mesmo sem
fiscal_operation_line_id.

Modo de usar (rodar da raiz do repo, com o odoo.conf do servidor):
  /home/iomr/venv/bin/python /home/iomr/odoo/odoo-bin shell \
      -c /home/iomr/odoo/odoo.conf -d odoo18_prod --log-level=info --no-http \
      < crm_commissions/scripts/fix_fiscal_operation_lines.py
"""

import logging

_logger = logging.getLogger(__name__)

# === CONFIG ===
DRY_RUN = True  # Mude para False para aplicar
COMPANY_ID = 1

# Campos cujo recalculo e disparado por qualquer um destes metodos
RECOMPUTE_METHODS = (
    "_compute_product_fiscal_fields",
    "_compute_city_taxation_code_id",
)


def forcar_recalculo(records, methods):
    """Marca os campos calculados indicados para recalculo nos registros."""
    model = records.browse()
    marcados = 0
    for fname, field in model._fields.items():
        if field.compute in methods:
            env.add_to_compute(field, records)
            marcados += 1
    return marcados


try:
    lines = env["sale.order.line"].search([
        ("display_type", "=", False),
        ("company_id", "=", COMPANY_ID),
        ("fiscal_operation_id", "!=", False),
    ])

    resolvidas_antes = lines.filtered("fiscal_operation_line_id")
    sem_antes = lines - resolvidas_antes
    total_antes = sum(lines.mapped("order_id").mapped("amount_total"))

    _logger.info("=" * 78)
    _logger.info("PENDENCIA - fiscal_operation_line_id nas linhas de pedido")
    _logger.info("=" * 78)
    _logger.info("  Linhas de produto com Operacao Fiscal: %s", len(lines))
    _logger.info("  Resolvidas ANTES: %s", len(resolvidas_antes))
    _logger.info("  SEM resolucao ANTES: %s", len(sem_antes))
    _logger.info("  Soma amount_total dos pedidos: R$ %.2f", total_antes)

    # ------------------------------------------------------------------
    # 1. Campos fiscais do produto nas linhas
    # ------------------------------------------------------------------
    _logger.info("")
    _logger.info("=" * 78)
    _logger.info("[1] Forcando recalculo dos campos fiscais vindos do produto")
    _logger.info("=" * 78)
    n1 = forcar_recalculo(lines, RECOMPUTE_METHODS)
    env.flush_all()
    _logger.info("  %s campo(s) recalculado(s) em %s linha(s).", n1, len(lines))

    # ------------------------------------------------------------------
    # 2. fiscal_operation_line_id
    # ------------------------------------------------------------------
    _logger.info("")
    _logger.info("=" * 78)
    _logger.info("[2] Forcando recalculo do fiscal_operation_line_id")
    _logger.info("=" * 78)
    env.add_to_compute(lines._fields["fiscal_operation_line_id"], lines)
    env.flush_all()
    resolvidas_depois = lines.filtered("fiscal_operation_line_id")
    _logger.info("  Resolvidas DEPOIS: %s (antes %s)", len(resolvidas_depois), len(resolvidas_antes))
    _logger.info("  Ganho: %s linha(s)", len(resolvidas_depois) - len(resolvidas_antes))

    # ------------------------------------------------------------------
    # 3. Impostos fiscais e valores
    # ------------------------------------------------------------------
    _logger.info("")
    _logger.info("=" * 78)
    _logger.info("[3] Deixando impostos fiscais e valores recalcularem")
    _logger.info("=" * 78)
    env.flush_all()
    env.invalidate_all()
    lines = env["sale.order.line"].browse(lines.ids)
    env.flush_all()

    orders = lines.mapped("order_id")
    total_depois = sum(orders.mapped("amount_total"))
    _logger.info("  Soma amount_total DEPOIS: R$ %.2f (delta R$ %.2f)",
                 total_depois, total_depois - total_antes)

    # ------------------------------------------------------------------
    # 4. Relatorio
    # ------------------------------------------------------------------
    pendentes = lines - lines.filtered("fiscal_operation_line_id")
    _logger.info("")
    _logger.info("=" * 78)
    _logger.info("PENDENCIAS RESTANTES: %s linha(s) em %s pedido(s)",
                 len(pendentes), len(pendentes.mapped("order_id")))
    _logger.info("=" * 78)

    com_produto = pendentes.filtered("product_id")
    sem_produto = pendentes - com_produto
    adiantamentos = sem_produto.filtered("is_downpayment")
    sem_produto_real = sem_produto - adiantamentos

    _logger.info("")
    _logger.info("  (a) Linhas de ADIANTAMENTO (is_downpayment, sem produto por natureza): %s", len(adiantamentos))
    _logger.info("      Nao precisam de operacao fiscal: o l10n_br_sale inclui as linhas de")
    _logger.info("      adiantamento na fatura mesmo sem fiscal_operation_line_id.")
    if len(adiantamentos):
        _logger.info("      Pedidos: %s", ", ".join(sorted(adiantamentos.mapped("order_id").mapped("name"))[:20]))

    _logger.info("")
    _logger.info("  (b) COM produto, mas nenhuma linha de operacao da operacao 'Venda' casa: %s linha(s)",
                 len(com_produto))
    for p in com_produto.mapped("product_id"):
        _logger.info("      ID %-5s %-40s fiscal_type=%-6s ncm=%-14s tax_icms_or_issqn=%s",
                     p.id, (p.display_name or "")[:40],
                     p.fiscal_type or "(VAZIO)", p.ncm_id.code or "(SEM NCM)",
                     p.tax_icms_or_issqn)
        _logger.info("             -> linhas: %s | pedidos: %s",
                     len(com_produto.filtered(lambda l, p=p: l.product_id == p)),
                     ", ".join(sorted(com_produto.filtered(lambda l, p=p: l.product_id == p)
                                      .mapped("order_id").mapped("name"))[:15]))

    _logger.info("")
    _logger.info("  (c) SEM produto e que NAO sao adiantamento (dados a corrigir): %s linha(s) em %s pedido(s)",
                 len(sem_produto_real), len(sem_produto_real.mapped("order_id")))
    for l in sem_produto_real[:20]:
        _logger.info("      linha %-6s pedido %-9s descricao=%-30s qtd=%s preco=%.2f",
                     l.id, l.order_id.name, (l.name or "")[:30], l.product_uom_qty, l.price_unit)

    _logger.info("")
    _logger.info("  PENDENCIA REAL: %s linha(s) de produto com cadastro fiscal incompleto.",
                 len(com_produto) + len(sem_produto_real))

    if DRY_RUN:
        _logger.info("")
        _logger.info("=" * 78)
        _logger.info("RESUMO DRY-RUN: nada foi gravado (rollback automatico do shell).")
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
