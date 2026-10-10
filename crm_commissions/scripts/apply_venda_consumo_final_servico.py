"""
Aplica, em TODOS os pedidos de venda e cotacoes da empresa:

  PEDIDOS (sale.order)
    Operacao (fiscal_operation_id)          = Venda   (l10n_br_fiscal.fo_venda)
    Operacao de Consumo Final (ind_final)   = Sim     ('1')

  LINHAS DE PEDIDO (sale.order.line, somente display_type vazio)
    Linha de Operacao (fiscal_operation_line_id) = Prestacao de Servico
                                                   (l10n_br_fiscal.fo_venda_servico)
    Operacao (fiscal_operation_id)               = Venda  (l10n_br_fiscal.fo_venda)
    Consumo Final (ind_final)                    = Sim    ('1')

DIFERENCA em relacao ao apply_fiscal_operation.py (2026-10-08):
  - O script anterior so gravava fiscal_operation_id nas linhas e deixava o
    l10n_br_fiscal RESOLVER a linha de operacao pelo NCM / fiscal_type do
    produto (mercadoria -> "Venda", servico -> "Prestacao de Servico").
  - Este script GRAVA a linha de operacao "Prestacao de Serviço" (fo_venda_servico)
    explicitamente em TODAS as linhas, independente de NCM/produto. O
    fo_venda_servico tem tax_icms_or_issqn='issqn' e documento SE (NFS-e),
    entao as linhas de mercadoria passam a ser tratadas como servico.

POR QUE TAMBEM OS PARCEIROS:
  - ind_final do pedido e CALCULADO a partir do parceiro (_compute_ind_final
    em l10n_br_fiscal.models.document_mixin); sem gravar no parceiro ele
    volta para "Nao" no proximo calculo (ex.: ao trocar o cliente).
  - ind_final da linha copia o do pedido, por isso tambem e gravado nas linhas.

POR QUE GRAVAR A LINHA DE OPERACAO EM DUAS PASSADAS:
  - fiscal_operation_line_id e um campo calculado e ARMAZENADO que depende
    de fiscal_operation_id / partner_id / product_id. Gravar operacao e linha
    de operacao num mesmo write funciona (Odoo protege o valor explicito),
    mas aqui sao duas passadas + verificacao final, para nao correr o risco
    de o recalculo sobrescrever o valor forcado.

Escopo definido pelo usuario:
  - Pedidos: TODOS os pedidos de venda e cotacoes da empresa (todos os
    estados, inclusive rascunhos, confirmados, faturados e cancelados).
  - Linhas: TODAS as linhas de pedido (inclusive adiantamentos/down payment).

RESULTADO (aplicado e commitado em 2026-10-10 02:38, verificado no banco):
  - 820 de 820 pedidos com Operacao='Venda' e Consumo Final='Sim';
  - 1520 de 1520 linhas com Operacao='Venda' e Linha de Operacao=
    'Prestacao de Servico' (0 linhas fora do padrao);
  - 753 de 753 parceiros com Consumo Final='Sim';
  - Backup pre-execucao: backup_20261010_023437_pre_venda_servico.dump.

Efeitos fiscais e numericos (medidos no DRY-RUN de 2026-10-10 e confirmados
na aplicacao):
  - 820 de 820 pedidos e 753 de 753 parceiros alterados;
  - 1520 de 1520 linhas ficam com Linha de Operacao = "Prestacao de Servico".
    ANTES: 1518 linhas estavam SEM linha de operacao (faturamento travado
    nelas), 1 ja era "Prestacao de Servico" e 1 era "Venda nao Contribuinte";
  - Linhas por imposto DEPOIS: 1478 issqn / 42 icms (os 42 continuam 'icms'
    porque o campo vem do PRODUTO mercadoria; a operacao forcada e de
    servico, entao os impostos mapeados sao de ISSQN);
  - Soma amount_total: R$ 5.737.432,39 -> R$ 5.719.815,47 (delta R$ -17.616,92).
    E a carga de ISSQN passando a incidir (inclusive nas 42 linhas de
    mercadoria e nas 14 linhas de adiantamento, que agora tambem recebem
    linha de operacao e impostos).

ATENCAO: linhas de ADIANTAMENTO (down payment, 14 no total) tambem recebem a
linha de operacao e, por consequencia, impostos fiscais. Se nao quiser esse
efeito, filtre lines antes do PASSO 4 com:
    lines = lines.filtered(lambda l: not l.is_downpayment)

Modo de usar no servidor de producao (usar o MESMO python do servidor;
rodar da raiz do repo, com o odoo.conf do servidor):
  /home/iomr/venv/bin/python /home/iomr/odoo/odoo-bin shell \
      -c /home/iomr/odoo/odoo.conf -d odoo18_prod --log-level=info --no-http \
      < crm_commissions/scripts/apply_venda_consumo_final_servico.py

DRY-RUN: mude DRY_RUN = True para medir o impacto sem gravar (as gravacoes sao
feitas na transacao e revertidas por rollback no final). Mude DRY_RUN = False
para aplicar. Sempre faca backup antes:
  pg_dump -h 10.84.10.51 -U odoo18 -Fc -f backup_$(date +%Y%m%d)_pre_venda_servico.dump odoo18_prod
"""

import logging

_logger = logging.getLogger(__name__)

# === CONFIG ===
DRY_RUN = False  # Aplicado em 2026-10-10 (backup_20261010_023437_pre_venda_servico.dump)
COMPANY_ID = 1  # Instituto De Oftalmologia Marco Rey

try:
    company = env["res.company"].browse(COMPANY_ID)
    if not company.exists():
        raise Exception("Empresa ID %s nao encontrada." % COMPANY_ID)

    operation = env.ref("l10n_br_fiscal.fo_venda", raise_if_not_found=False)
    if not operation:
        raise Exception("Operacao fiscal 'Venda' (l10n_br_fiscal.fo_venda) nao encontrada.")

    operation_line = env.ref("l10n_br_fiscal.fo_venda_servico", raise_if_not_found=False)
    if not operation_line:
        raise Exception(
            "Linha de operacao 'Prestacao de Servico' (l10n_br_fiscal.fo_venda_servico) nao encontrada."
        )
    if operation_line.fiscal_operation_id != operation:
        raise Exception(
            "A linha '%s' pertence a operacao '%s' e nao a 'Venda'."
            % (operation_line.name, operation_line.fiscal_operation_id.name)
        )

    orders = env["sale.order"].search([("company_id", "=", COMPANY_ID)])
    partners = orders.mapped("partner_id")
    lines = orders.order_line.filtered(lambda l: not l.display_type)
    adiantamentos = lines.filtered("is_downpayment")

    _logger.info("=" * 78)
    _logger.info("OPERACAO 'VENDA' + CONSUMO FINAL + LINHA 'PRESTACAO DE SERVICO' - %s", company.name)
    _logger.info("=" * 78)
    _logger.info("  Operacao:        %s (ID %s)", operation.name, operation.id)
    _logger.info("  Linha operacao:  %s (ID %s, doc %s)",
                 operation_line.name, operation_line.id,
                 operation_line.document_type_id.code or "(sem documento)")
    _logger.info("  Pedidos:         %s", len(orders))
    _logger.info("  Linhas:          %s (sendo %s de adiantamento)", len(lines), len(adiantamentos))
    _logger.info("  Parceiros:       %s", len(partners))

    by_state = {}
    for o in orders:
        by_state[(o.state, o.invoice_status)] = by_state.get((o.state, o.invoice_status), 0) + 1
    for k in sorted(by_state):
        _logger.info("    state=%-6s invoice_status=%-10s %s pedidos", k[0], k[1], by_state[k])

    total_antes = sum(orders.mapped("amount_total"))
    _logger.info("  Soma amount_total ANTES: R$ %.2f", total_antes)

    def _dist(recs, field):
        d = {}
        for r in recs:
            name = r[field].name or "(vazio)"
            d[name] = d.get(name, 0) + 1
        return d

    _logger.info("")
    _logger.info("  Distribuicao ANTES - Linha de Operacao das linhas:")
    for k, v in sorted(_dist(lines, "fiscal_operation_line_id").items(), key=lambda x: -x[1]):
        _logger.info("      %-52s %s", k, v)

    # ------------------------------------------------------------------
    # 1. Parceiros: ind_final = '1' (Sim)
    #    Feito ANTES dos pedidos para o gravado ficar coerente.
    # ------------------------------------------------------------------
    partners_fix = partners.filtered(lambda p: p.ind_final != "1")
    _logger.info("")
    _logger.info("=" * 78)
    _logger.info("[PASSO 1] PARCEIROS: ind_final = '1' (Sim)")
    _logger.info("=" * 78)
    _logger.info("  A alterar: %s de %s", len(partners_fix), len(partners))
    if partners_fix:
        partners_fix.write({"ind_final": "1"})
        if DRY_RUN:
            _logger.info("  [DRY-RUN] %s parceiro(s) atualizados na transacao (rollback no final).",
                         len(partners_fix))
        else:
            env.cr.commit()
            _logger.info("  OK %s parceiro(s) atualizado(s).", len(partners_fix))
    else:
        _logger.info("  Todos os parceiros ja estao como 'Sim'.")

    # ------------------------------------------------------------------
    # 2. Pedidos: Operacao = Venda e Consumo Final = Sim
    # ------------------------------------------------------------------
    _logger.info("")
    _logger.info("=" * 78)
    _logger.info("[PASSO 2] PEDIDOS: Operacao = 'Venda' / Consumo Final = 'Sim'")
    _logger.info("=" * 78)
    orders_fix = orders.filtered(
        lambda o: o.fiscal_operation_id != operation or o.ind_final != "1"
    )
    _logger.info("  A alterar: %s de %s", len(orders_fix), len(orders))
    if orders_fix:
        orders_fix.write({"fiscal_operation_id": operation.id, "ind_final": "1"})
        if DRY_RUN:
            _logger.info("  [DRY-RUN] %s pedido(s) atualizados na transacao (rollback no final).",
                         len(orders_fix))
        else:
            env.cr.commit()
            _logger.info("  OK %s pedido(s) atualizado(s).", len(orders_fix))
    else:
        _logger.info("  Todos os pedidos ja estao corretos.")

    # ------------------------------------------------------------------
    # 3. Linhas - passada 1: Operacao = Venda e Consumo Final = Sim
    # ------------------------------------------------------------------
    _logger.info("")
    _logger.info("=" * 78)
    _logger.info("[PASSO 3] LINHAS (passada 1): Operacao = 'Venda' / Consumo Final = 'Sim'")
    _logger.info("=" * 78)
    lines_op_fix = lines.filtered(
        lambda l: l.fiscal_operation_id != operation or l.ind_final != "1"
    )
    _logger.info("  A alterar: %s de %s", len(lines_op_fix), len(lines))
    if lines_op_fix:
        lines_op_fix.write({"fiscal_operation_id": operation.id, "ind_final": "1"})
        if DRY_RUN:
            _logger.info("  [DRY-RUN] %s linha(s) atualizadas na transacao (rollback no final).",
                         len(lines_op_fix))
        else:
            env.cr.commit()
            _logger.info("  OK %s linha(s) atualizada(s).", len(lines_op_fix))
    else:
        _logger.info("  Todas as linhas ja estao com operacao 'Venda' e consumo final 'Sim'.")

    # ------------------------------------------------------------------
    # 4. Linhas - passada 2: Linha de Operacao = 'Prestacao de Servico'
    #    (grava o valor explicito; o compute so recalcula quando algo
    #     que ele depende muda, entao a passada 1 ja foi commitada antes)
    # ------------------------------------------------------------------
    _logger.info("")
    _logger.info("=" * 78)
    _logger.info("[PASSO 4] LINHAS (passada 2): Linha de Operacao = 'Prestacao de Servico'")
    _logger.info("=" * 78)
    lines_sol_fix = lines.filtered(lambda l: l.fiscal_operation_line_id != operation_line)
    _logger.info("  A alterar: %s de %s", len(lines_sol_fix), len(lines))
    if lines_sol_fix:
        lines_sol_fix.write({"fiscal_operation_line_id": operation_line.id})
        env.flush_all()
        if DRY_RUN:
            _logger.info("  [DRY-RUN] %s linha(s) atualizadas na transacao (rollback no final).",
                         len(lines_sol_fix))
        else:
            env.cr.commit()
            _logger.info("  OK %s linha(s) atualizada(s).", len(lines_sol_fix))
    else:
        _logger.info("  Todas as linhas ja estao com 'Prestacao de Servico'.")

    # ------------------------------------------------------------------
    # 5. Verificacao final (apos flush; no DRY-RUN nada mudou de fato)
    # ------------------------------------------------------------------
    env.flush_all()
    env.invalidate_all()
    orders = env["sale.order"].search([("company_id", "=", COMPANY_ID)])
    lines = orders.order_line.filtered(lambda l: not l.display_type)

    _logger.info("")
    _logger.info("=" * 78)
    _logger.info("VERIFICACAO")
    _logger.info("=" * 78)
    _logger.info("  Pedidos com Operacao='Venda'        : %s de %s",
                 len(orders.filtered(lambda o: o.fiscal_operation_id == operation)), len(orders))
    _logger.info("  Pedidos com Consumo Final='Sim'     : %s de %s",
                 len(orders.filtered(lambda o: o.ind_final == "1")), len(orders))
    _logger.info("  Parceiros com Consumo Final='Sim'   : %s de %s",
                 len(partners.filtered(lambda p: p.ind_final == "1")), len(partners))
    _logger.info("  Linhas com Operacao='Venda'         : %s de %s",
                 len(lines.filtered(lambda l: l.fiscal_operation_id == operation)), len(lines))
    _logger.info("  Linhas com Linha Operacao='Prestacao de Servico' : %s de %s",
                 len(lines.filtered(lambda l: l.fiscal_operation_line_id == operation_line)),
                 len(lines))

    _logger.info("")
    _logger.info("  Distribuicao DEPOIS - Linha de Operacao das linhas:")
    for k, v in sorted(_dist(lines, "fiscal_operation_line_id").items(), key=lambda x: -x[1]):
        _logger.info("      %-52s %s", k, v)

    impostos = {}
    for ln in lines:
        key = ln.tax_icms_or_issqn or "(vazio)"
        impostos[key] = impostos.get(key, 0) + 1
    _logger.info("")
    _logger.info("  Linhas por imposto (tax_icms_or_issqn) DEPOIS:")
    for k in sorted(impostos, key=lambda x: -impostos[x]):
        _logger.info("      %-52s %s", k, impostos[k])

    total_depois = sum(orders.mapped("amount_total"))
    _logger.info("")
    _logger.info("  Soma amount_total DEPOIS: R$ %.2f (delta R$ %.2f)",
                 total_depois, total_depois - total_antes)

    if DRY_RUN:
        _logger.info("")
        _logger.info("=" * 78)
        _logger.info("RESUMO DRY-RUN: as gravacoes foram feitas NA TRANSACAO e revertidas")
        _logger.info("pelo rollback - nada foi persistido no banco.")
        _logger.info("Para aplicar, edite o script e mude DRY_RUN = False.")
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
