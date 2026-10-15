#!/usr/bin/env python3
"""
Script para recalcular comissões da Coordenadora e atualizar linhas de vendas.

Após a migração para o cálculo individualizado da Coordenadora, este script:
1. Recalcula todos os commission.result de coordenadoras com a nova lógica
2. Atualiza as linhas sale.order.line.agent com os novos valores
3. Recalcula os bônus trimestrais das equipes (incluindo coordenadoras)

Uso:
    odoo-bin shell -c /home/rodrigo/odoo18/odoo/odoo.conf -d <database> < scripts/recompute_coordinator_commissions.py
"""

import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


def recompute_all(env):
    """Função principal - executa todo o recálculo."""

    _logger.info("=" * 70)
    _logger.info("RECÁLCULO DE COMISSÕES DA COORDENADORA - Política 2026")
    _logger.info("=" * 70)

    # ================================================================
    # ETAPA 1: Recalcular commission.result de coordenadoras
    # ================================================================
    _logger.info("")
    _logger.info("[ETAPA 1/3] Recalculando resultados de comissão...")

    coordinator_results = env["commission.result"].search([
        ("member_id.member_type", "=", "coordenadora"),
        ("state", "in", ("draft", "calculated")),
    ])

    total = len(coordinator_results)
    _logger.info("  %d resultados de coordenadora encontrados", total)

    success = 0
    errors = 0

    for idx, result in enumerate(coordinator_results, 1):
        name = result.member_id.name
        period = result.period_code
        _logger.info("  [%d/%d] %s - %s", idx, total, name, period)

        try:
            # Recalcula com a nova lógica individualizada
            result.action_calculate()
            success += 1

            _logger.info(
                "      Base: R$ %10.2f | Rate: %5.2f%% | Amount: R$ %10.2f",
                result.commission_base_amount,
                result.base_rate,
                result.commission_amount,
            )
        except Exception as e:
            errors += 1
            _logger.error("      ERRO: %s", str(e))

    env.cr.commit()
    _logger.info("  ✅ Resultados recalculados: %d sucesso, %d erros", success, errors)

    # ================================================================
    # ETAPA 2: Atualizar sale.order.line.agent (linhas de venda)
    # ================================================================
    _logger.info("")
    _logger.info("[ETAPA 2/3] Atualizando linhas de venda...")

    # Busca coordenadoras que são agentes
    coordinators = env["res.partner"].search([
        ("type_partner", "=", "coordenadora"),
        ("agent", "=", True),
    ])

    total_coord = len(coordinators)
    _logger.info("  %d coordenadoras encontradas", total_coord)

    total_lines = 0

    for idx, coordinator in enumerate(coordinators, 1):
        # Busca linhas de venda onde a coordenadora é agente
        sale_lines = env["sale.order.line"].search([
            ("agent_ids.agent_id", "=", coordinator.id),
        ])

        count = len(sale_lines)
        if count == 0:
            continue

        _logger.info("  [%d/%d] %s: %d linhas", idx, total_coord, coordinator.name, count)

        # Força recálculo do campo computado amount
        sale_lines.modified(["agent_ids"])
        total_lines += count

    env.cr.commit()
    _logger.info("  ✅ %d linhas de venda atualizadas", total_lines)

    # ================================================================
    # ETAPA 3: Recalcular bônus trimestrais (inclui coordenadoras)
    # ================================================================
    _logger.info("")
    _logger.info("[ETAPA 3/3] Recalculando bônus trimestrais...")

    target_model = env["crm.commission.target"].sudo()
    target_model._sync_all_quarterly_bonuses()
    target_model._sync_all_legacy_targets()

    # Busca bônus de coordenadoras
    coordinator_bonuses = env["crm.commission.quarterly.bonus"].search([
        ("agent_id.type_partner", "=", "coordenadora"),
    ])

    _logger.info("  ✅ Bônus trimestrais recalculados (%d de coordenadoras)", len(coordinator_bonuses))

    env.cr.commit()

    # ================================================================
    # RELATÓRIO FINAL
    # ================================================================
    _logger.info("")
    _logger.info("=" * 70)
    _logger.info("RELATÓRIO FINAL")
    _logger.info("=" * 70)

    # Estatísticas por período
    stats = env["commission.result"].read_group(
        domain=[
            ("member_id.member_type", "=", "coordenadora"),
            ("state", "=", "calculated"),
        ],
        fields=["commission_amount", "commission_base_amount"],
        groupby=["period_code"],
    )

    _logger.info("  Período | Coord. | Base Total      | Comissão Total")
    _logger.info("  " + "-" * 55)

    grand_base = 0.0
    grand_amount = 0.0
    for stat in stats:
        period = stat.get("period_code", "N/A")
        count = stat.get("__count", 0)
        base = stat.get("commission_base_amount", 0.0) or 0.0
        amount = stat.get("commission_amount", 0.0) or 0.0
        grand_base += base
        grand_amount += amount
        _logger.info("  %s | %5d | R$ %12.2f | R$ %12.2f", period, count, base, amount)

    _logger.info("  " + "-" * 55)
    _logger.info("  TOTAL   |       | R$ %12.2f | R$ %12.2f", grand_base, grand_amount)
    _logger.info("")
    _logger.info("✅ RECÁLCULO CONCLUÍDO COM SUCESSO!")
    _logger.info("=" * 70)


# ================================================================
# PONTO DE ENTRADA
# ================================================================
# Este bloco é executado automaticamente quando o script é carregado
# via odoo-bin shell. A variável `env` já está disponível no escopo.
# ================================================================
try:
    recompute_all(env)
except NameError:
    _logger.error("Este script deve ser executado via odoo-bin shell:")
    _logger.error("  odoo-bin shell -c /home/rodrigo/odoo18/odoo/odoo.conf -d <db> < %s", __file__)
except Exception as e:
    _logger.error("Erro durante execução: %s", str(e))
    import traceback
    traceback.print_exc()
