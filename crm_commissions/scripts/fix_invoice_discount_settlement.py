# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Recalcula fechamentos de fatura com a nova regra de rateio.

A correção ``18.0.2.10.0`` muda a base do fechamento de ``sale_invoice``:
em vez de ``comissão_do_pedido × total_da_fatura / total_do_pedido``, usa a
comissão do agente no pedido rateada pelo valor efetivamente faturado **das
linhas do agente**. É o que faz o desconto aplicado só na fatura reduzir
também os repasses fixos (médicos) e o que absorve corretamente as entradas.

Este script aplica a nova regra nos fechamentos já gravados, sem migração
automática. Ele é idempotente e nunca toca em fechamentos faturados
(``state == "invoiced"``): só considera linhas ``sale_invoice`` com
``state == "settled"``.

Uso (odoo shell, da raiz do repo), depois de subir o código novo:

    /home/iomr/venv/bin/python /home/iomr/odoo/odoo-bin shell \
        -c /home/iomr/odoo/odoo.conf -d <banco> --log-level=info --no-http \
        < crm_commissions/scripts/fix_invoice_discount_settlement.py

Por segurança o padrão é ``DRY_RUN = True``: nada é gravado e o relatório
mostra, por pedido/agente/fatura, a base atual, a base nova, o delta e o
valor liquidado. Confira o relatório, ajuste as opções e rode de novo.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

DRY_RUN = True
# Quando True, corrige apenas os fechamentos em que a base nova é MAIOR que a
# atual (subpagamento). Deixe False para também reduzir os casos de
# superpagamento (ex.: S00859 / Dr. Rafael), sempre em fechamentos ainda não
# faturados.
ONLY_INCREASES = False


def _payment_ratio(invoice):
    """Percentual da fatura efetivamente recebido (1.0 se quitada)."""
    if (
        invoice
        and invoice.payment_state == "partial"
        and invoice.amount_total
    ):
        amount_paid = invoice.amount_total - (invoice.amount_residual or 0.0)
        return max(0.0, min(amount_paid / invoice.amount_total, 1.0))
    return 1.0


def _current_base(line):
    """Base atual da linha, mesmo nas antigas sem ``invoice_base_amount``."""
    if line.invoice_base_amount:
        return line.invoice_base_amount
    ratio = _payment_ratio(line.invoice_agent_line_id.invoice_id)
    if not ratio:
        return 0.0
    return (line.settled_amount or 0.0) / ratio


def run(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})

    lines = env["commission.settlement.line"].search(
        [
            ("settlement_id.settlement_type", "=", "sale_invoice"),
            ("settlement_id.state", "=", "settled"),
            ("invoice_agent_line_id", "!=", False),
        ],
        order="agent_id, date, id",
    )

    updated = 0
    increased = 0
    decreased = 0
    unchanged = 0
    skipped = 0
    total_current = 0.0
    total_new = 0.0

    _logger.info("=" * 96)
    _logger.info(
        "RECALCULO DO FECHAMENTO DE FATURA (DRY_RUN=%s, ONLY_INCREASES=%s)",
        DRY_RUN,
        ONLY_INCREASES,
    )
    _logger.info(
        "%-12s %-28s %-18s %12s %12s %12s",
        "Pedido",
        "Agente",
        "Fatura",
        "Base atual",
        "Base nova",
        "Delta",
    )
    for line in lines:
        agent_line = line.invoice_agent_line_id
        invoice = agent_line.invoice_id
        new_base = agent_line._get_settlement_base_amount()
        current_base = _current_base(line)
        delta = new_base - current_base
        if abs(delta) < 0.01:
            unchanged += 1
            continue
        if ONLY_INCREASES and delta < 0:
            skipped += 1
            continue

        ratio = _payment_ratio(invoice)
        new_settled = new_base * ratio
        order = agent_line._get_settlement_sale_orders()[:1]
        _logger.info(
            "%-12s %-28s %-18s %12.2f %12.2f %12.2f",
            order.name or "-",
            line.agent_id.display_name[:28],
            invoice.name or "-",
            current_base,
            new_base,
            delta,
        )
        if delta > 0:
            increased += 1
        else:
            decreased += 1
        updated += 1
        total_current += current_base
        total_new += new_base
        if not DRY_RUN:
            line.write(
                {
                    "invoice_base_amount": new_base,
                    "settled_amount": new_settled,
                }
            )

    _logger.info("-" * 96)
    _logger.info("  linhas analisadas: %s", len(lines))
    _logger.info("  linhas alteradas: %s", updated)
    _logger.info("  aumentos: %s | reduções: %s", increased, decreased)
    _logger.info(
        "  sem alteração: %s | puladas por ONLY_INCREASES: %s", unchanged, skipped
    )
    _logger.info(
        "  base total: %.2f -> %.2f (delta %.2f)",
        total_current,
        total_new,
        total_new - total_current,
    )
    _logger.info("=" * 96)
    if DRY_RUN:
        cr.rollback()
        _logger.info("DRY_RUN: nenhuma alteração gravada (rollback).")
    else:
        cr.commit()
        _logger.info("Alterações gravadas.")


try:
    run(env.cr)  # noqa: F821 - provided by odoo shell
except Exception:
    _logger.exception("Falha no recálculo do fechamento de fatura")
    env.cr.rollback()  # noqa: F821 - provided by odoo shell
    raise
