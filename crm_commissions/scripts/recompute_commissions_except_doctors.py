# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Recalcula as comissoes de TODOS os agentes, exceto os medicos.

Motivo: a base de calculo da comissao "Comissao Progressiva LIOs" foi alterada
(2026-10-30) e o ``amount`` das linhas de agente e um campo calculado e
ARMAZENADO. O ``@api.depends`` dele nao inclui os campos da comissao, entao
gravar a politica nao dispara o recalculo dos valores ja existentes. Este
script forca o recalculo.

Escopo:
  * ``sale.order.line.agent`` de pedidos e orcamentos da empresa 1, em
    qualquer estado.
  * ``account.invoice.line.agent`` de faturas/notas de saida (rascunho e
    postadas, pagas ou nao) da empresa 1.
  * ``commission.settlement.line`` e ``commission.settlement`` das linhas de
    fatura ja liquidadas, para que o valor liquidado acompanhe a comissao.
  * Agentes com ``type_partner`` em ('doctorint', 'doctorext') NAO sao
    tocados, em pedidos, faturas ou settlements.

Linhas de fatura com ``settled=True`` sao protegidas pelo OCA
("You can't modify a settled line"), entao a constraint
``_check_settle_integrity`` e suspensa apenas durante o recalculo, no
processo do shell, e restaurada em seguida. Depois o ``settled_amount`` do
settlement line e o ``total`` do settlement sao recalculados pelo ORM,
mantendo os dois lados coerentes.

Linhas antigas que ainda apontam para a Progressiva LIOs em categorias fora
do escopo (MAT/MED, Taxa de Sala, ...) seriam zeradas pela restricao de
categoria, nao pela mudanca de base. Elas sao preservadas e apenas
reportadas, para nao apagar comissao historica.

Tambem forca o recalculo de ``sale.order.commission_total`` e
``account.move.commission_total`` dos documentos afetados.

Uso (odoo shell, da raiz do repo):
    /home/iomr/venv/bin/python /home/iomr/odoo/odoo-bin shell \
        -c /home/iomr/odoo/odoo.conf -d odoo18_prod --log-level=info --no-http \
        < crm_commissions/scripts/recompute_commissions_except_doctors.py

Sempre faca backup antes de aplicar (DRY_RUN = False).
"""

import logging

_logger = logging.getLogger(__name__)

# === CONFIG ===
# Aplicado em 2026-10-30
# (backup_20261030_192449_pre_comissoes_nao_medicos.dump)
DRY_RUN = False
COMPANY_ID = 1
MEDICAL_TYPES = ("doctorint", "doctorext")
MAX_DETALHE = 40


def _is_progressive_out_of_scope(line):
    """Linha cuja comissao e a Progressiva, mas a categoria nao esta no escopo.

    A Progressiva LIOs foi restringida a categoria LIO (2026-10-27). Linhas
    antigas de fatura que ainda apontam para ela em categorias extras
    (MAT/MED, TAXA DE SALA, ...) seriam zeradas pelo recalculo -- nao pelo
    cambio de base, mas pela restricao de categoria. Elas ficam de fora para
    nao apagar comissao historica; o script apenas informa quais sao.
    """
    commission = line.commission_id
    if commission.commission_type != "progressive" or not commission.categ_ids:
        return False
    product = line.object_id.product_id
    if not product or not product.categ_id:
        return False
    categ = product.categ_id
    categ_ids = set()
    while categ:
        categ_ids.add(categ.id)
        categ = categ.parent_id
    return not (categ_ids & set(commission.categ_ids.ids))


def _resumo_por_commission(lines, antes, depois):
    resumo = {}
    for line in lines:
        delta = depois[line.id] - antes[line.id]
        if abs(delta) < 0.005:
            continue
        key = (
            line.agent_id.type_partner,
            line.commission_id.name or "-",
        )
        item = resumo.setdefault(key, [0, 0.0])
        item[0] += 1
        item[1] += delta
    for key in sorted(resumo):
        qtd, delta = resumo[key]
        _logger.info(
            "      %-13s %-58s %5d linhas  delta R$ %12.2f",
            key[0],
            key[1][:58],
            qtd,
            delta,
        )


def _recompute(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})

    SaleAgent = env["sale.order.line.agent"]
    InvoiceAgent = env["account.invoice.line.agent"]
    SettlementLine = env["commission.settlement.line"]
    Settlement = env["commission.settlement"]
    SaleOrder = env["sale.order"]
    Invoice = env["account.move"]

    # ------------------------------------------------------------------
    # 1) Linhas de agente de PEDIDOS/ORCAMENTOS (exceto medicos)
    # ------------------------------------------------------------------
    sale_lines = SaleAgent.search(
        [
            ("object_id.order_id.company_id", "=", COMPANY_ID),
            ("agent_id.type_partner", "not in", list(MEDICAL_TYPES)),
        ],
        order="object_id, id",
    )
    sale_orders = sale_lines.mapped("object_id.order_id")

    sale_antes = {line.id: line.amount for line in sale_lines}
    sale_tot_antes = {o.id: o.commission_total for o in sale_orders}
    _logger.info("=" * 90)
    _logger.info("RECALCULO DE COMISSOES - EXCETO MEDICOS")
    _logger.info("=" * 90)
    _logger.info(
        "PEDIDOS/ORCAMENTOS: %s linhas de agente nao-medico em %s pedidos",
        len(sale_lines),
        len(sale_orders),
    )
    _logger.info("  Soma ANTES: R$ %.4f", sum(sale_antes.values()))

    env.add_to_compute(SaleAgent._fields["amount"], sale_lines)
    env.flush_all()
    env.invalidate_all()

    sale_lines = SaleAgent.browse(sorted(sale_antes))
    sale_orders = SaleOrder.browse(sorted(sale_tot_antes))
    sale_depois = {line.id: line.amount for line in sale_lines}
    _logger.info("  Soma DEPOIS: R$ %.4f (delta R$ %.4f)",
                 sum(sale_depois.values()),
                 sum(sale_depois.values()) - sum(sale_antes.values()))
    _logger.info("  Deltas por tipo/comissao:")
    _resumo_por_commission(sale_lines, sale_antes, sale_depois)

    env.add_to_compute(SaleOrder._fields["commission_total"], sale_orders)
    env.flush_all()
    env.invalidate_all()
    sale_orders = SaleOrder.browse(sorted(sale_tot_antes))
    _logger.info(
        "  commission_total dos pedidos: R$ %.4f -> R$ %.4f | %s pedidos alterados",
        sum(sale_tot_antes.values()),
        sum(o.commission_total for o in sale_orders),
        len(
            [
                o
                for o in sale_orders
                if abs(o.commission_total - sale_tot_antes[o.id]) >= 0.005
            ]
        ),
    )

    # ------------------------------------------------------------------
    # 2) Linhas de agente de FATURAS (exceto medicos)
    # ------------------------------------------------------------------
    inv_todas = InvoiceAgent.search(
        [
            ("object_id.move_id.company_id", "=", COMPANY_ID),
            ("object_id.move_id.move_type", "in", ("out_invoice", "out_refund")),
            ("object_id.move_id.state", "in", ("draft", "posted")),
            ("agent_id.type_partner", "not in", list(MEDICAL_TYPES)),
        ],
        order="object_id, id",
    )
    inv_liquidadas_todas = inv_todas.filtered("settled")
    inv_abertas_todas = inv_todas - inv_liquidadas_todas
    inv_liquidadas_skip = inv_liquidadas_todas.filtered(_is_progressive_out_of_scope)
    inv_abertas_skip = inv_abertas_todas.filtered(_is_progressive_out_of_scope)
    inv_liquidadas = inv_liquidadas_todas - inv_liquidadas_skip
    inv_abertas = inv_abertas_todas - inv_abertas_skip
    inv_lines = inv_todas
    # O total consolidado e recalculado em todas as faturas com linha
    # nao-medica: as preservadas nao mudam de valor, mas o total pode estar
    # defasado (inclusive por linhas medicas que nao tocamos).
    inv_moves = inv_todas.mapped("object_id.move_id")

    inv_antes = {line.id: line.amount for line in inv_lines}
    inv_tot_antes = {m.id: m.commission_total for m in inv_moves}
    _logger.info("")
    _logger.info(
        "FATURAS: %s linhas nao-medico (%s abertas + %s liquidadas) em %s faturas",
        len(inv_lines),
        len(inv_abertas_todas),
        len(inv_liquidadas_todas),
        len(inv_moves),
    )
    _logger.info(
        "  Legadas preservadas (Progressiva fora da categoria LIO): "
        "%s linhas, R$ %.2f (%s abertas + %s liquidadas)",
        len(inv_liquidadas_skip) + len(inv_abertas_skip),
        sum(inv_liquidadas_skip.mapped("amount"))
        + sum(inv_abertas_skip.mapped("amount")),
        len(inv_abertas_skip),
        len(inv_liquidadas_skip),
    )
    _logger.info("  Soma ANTES (todas): R$ %.4f", sum(inv_antes.values()))

    # 2a) Abertas: recalculo normal pelo ORM.
    if inv_abertas:
        env.add_to_compute(InvoiceAgent._fields["amount"], inv_abertas)
        env.flush_all()
        env.invalidate_all()

    # 2b) Liquidadas: o OCA bloqueia a gravacao ("You can't modify a settled
    # line"); a constraint e suspensa durante o compute/flush e restaurada
    # depois. O settlement e sincronizado pelo ORM em seguida.
    inv_depois = {}
    if inv_liquidadas:
        inv_liquidadas = InvoiceAgent.browse(sorted(inv_liquidadas.ids))
        # O OCA bloqueia qualquer gravacao em linha liquidada pela constraint
        # ``_check_settle_integrity``. O usuario pediu para atualizar tambem
        # essas linhas, entao a constraint e suspensa apenas durante este
        # recalculo, no processo do shell (o servidor nao e afetado), e
        # restaurada no ``finally``. O flush precisa acontecer DENTRO do
        # bloco: a gravacao fica em cache ate o flush e seria descartada por
        # um invalidate sem flush.
        constraint_methods = env["account.invoice.line.agent"]._constraint_methods
        original_constraints = list(constraint_methods)
        constraint_methods[:] = [
            check
            for check in constraint_methods
            if check.__name__ != "_check_settle_integrity"
        ]
        try:
            inv_liquidadas._compute_amount()
            env.flush_all()
        finally:
            constraint_methods[:] = original_constraints
        env.invalidate_all()
        for line in inv_liquidadas:
            inv_depois[line.id] = line.amount
        _logger.info(
            "  Liquidadas: %s linhas, %s alteradas, delta R$ %.2f",
            len(inv_liquidadas),
            len(
                [
                    line_id
                    for line_id in inv_liquidadas.ids
                    if abs(inv_depois[line_id] - inv_antes[line_id]) >= 0.005
                ]
            ),
            sum(inv_depois[i] - inv_antes[i] for i in inv_liquidadas.ids),
        )

    inv_lines = InvoiceAgent.browse(sorted(inv_antes))
    inv_depois.update({line.id: line.amount for line in inv_lines})
    inv_moves = Invoice.browse(sorted(inv_tot_antes))
    _logger.info("  Soma DEPOIS: R$ %.4f (delta R$ %.4f)",
                 sum(inv_depois.values()),
                 sum(inv_depois.values()) - sum(inv_antes.values()))
    _logger.info("  Deltas por tipo/comissao:")
    _resumo_por_commission(inv_lines, inv_antes, inv_depois)

    # 2c) Sincroniza os settlements das linhas liquidadas alteradas.
    liquidadas_alteradas = [
        line_id
        for line_id in inv_liquidadas.ids
        if abs(inv_depois[line_id] - inv_antes[line_id]) >= 0.005
    ]
    if liquidadas_alteradas:
        settlement_lines = SettlementLine.search(
            [("invoice_agent_line_id", "in", liquidadas_alteradas)]
        )
        settlements = settlement_lines.settlement_id
        tot_antes = {s.id: s.total for s in settlements}
        env.add_to_compute(SettlementLine._fields["settled_amount"], settlement_lines)
        env.flush_all()
        env.add_to_compute(Settlement._fields["total"], settlements)
        env.flush_all()
        env.invalidate_all()
        settlements = Settlement.browse(sorted(tot_antes))
        _logger.info(
            "  SETTLEMENTS: %s linhas liquidadas alteradas em %s settlements "
            "| total R$ %.4f -> R$ %.4f",
            len(liquidadas_alteradas),
            len(settlements),
            sum(tot_antes.values()),
            sum(s.total for s in settlements),
        )

    # 2d) Totais consolidados das faturas.
    env.add_to_compute(Invoice._fields["commission_total"], inv_moves)
    env.flush_all()
    env.invalidate_all()
    inv_moves = Invoice.browse(sorted(inv_tot_antes))
    _logger.info(
        "  commission_total das faturas: R$ %.4f -> R$ %.4f | %s faturas alteradas",
        sum(inv_tot_antes.values()),
        sum(m.commission_total for m in inv_moves),
        len(
            [
                m
                for m in inv_moves
                if abs(m.commission_total - inv_tot_antes[m.id]) >= 0.005
            ]
        ),
    )

    resultado = {
        "sale_lines": len(sale_lines),
        "sale_orders": len(sale_orders),
        "sale_delta": sum(sale_depois.values()) - sum(sale_antes.values()),
        "invoice_lines": len(inv_lines),
        "invoice_open": len(inv_abertas),
        "invoice_settled": len(inv_liquidadas),
        "invoice_skipped_legacy": len(inv_liquidadas_skip) + len(inv_abertas_skip),
        "invoice_settled_changed": len(liquidadas_alteradas),
        "invoice_moves": len(inv_moves),
        "invoice_delta": sum(inv_depois.values()) - sum(inv_antes.values()),
    }

    if DRY_RUN:
        _logger.info("")
        _logger.info("=" * 90)
        _logger.info("DRY-RUN: rollback - nada foi persistido.")
        _logger.info("=" * 90)
        env.cr.rollback()
    else:
        env.cr.commit()
        _logger.info("")
        _logger.info("=" * 90)
        _logger.info("CONCLUIDO e COMMITADO: %s", resultado)
        _logger.info("=" * 90)
    return resultado


try:
    from odoo import SUPERUSER_ID, api

    _recompute(env.cr)  # noqa: F821 - provided by odoo shell
except Exception as exc:  # noqa: BLE001 - odoo shell should print the traceback
    _logger.error("Erro: %s", exc)
    import traceback

    _logger.error(traceback.format_exc())
    try:
        env.cr.rollback()  # noqa: F821 - provided by odoo shell
    except Exception:
        _logger.exception("Falha ao desfazer a transação do recálculo")
