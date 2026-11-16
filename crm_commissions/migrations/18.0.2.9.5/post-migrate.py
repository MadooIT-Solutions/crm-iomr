# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Repara os fechamentos de comissão já gravados.

Três problemas deixavam o fechamento com linhas repetidas e valores fora da
proporção dos pagamentos:

1. ``invoice_line_id`` era um campo *related* de ``invoice_agent_line_id``.
   Como a FK do agente é ``ON DELETE SET NULL``, recalcular os agentes de uma
   fatura apagava a origem da linha de fechamento e a comissão podia ser
   fechada de novo. O campo passa a ser independente; aqui ele é preenchido
   nas linhas antigas e as linhas órfãs são religadas quando existe um único
   agente correspondente.
2. As linhas de CRM Performance foram criadas com valor zero quando a base
   de ``commission.sale`` ainda não tinha linhas de detalhe. A base é
   reconstruída a partir dos pedidos de venda e as linhas ainda não faturadas
   são recalculadas.
3. A base da comissão de fatura é congelada em ``invoice_base_amount`` para
   que o rateio por pagamento não dependa do ``amount`` atual do agente.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def _backfill_invoice_line(env):
    lines = (
        env["commission.settlement.line"]
        .sudo()
        .search(
            [
                ("invoice_line_id", "=", False),
                ("invoice_agent_line_id", "!=", False),
            ]
        )
    )
    for line in lines:
        line.invoice_line_id = line.invoice_agent_line_id.object_id
    return len(lines)


def _backfill_invoice_base(env):
    lines = (
        env["commission.settlement.line"]
        .sudo()
        .search(
            [
                ("settlement_id.settlement_type", "=", "sale_invoice"),
                ("invoice_base_amount", "=", 0.0),
                ("invoice_agent_line_id", "!=", False),
            ]
        )
    )
    updated = 0
    for line in lines:
        base = line.invoice_agent_line_id._get_settlement_base_amount()
        if not base and line.settled_amount:
            # Historical value whose source amount is no longer computable:
            # freeze the closed value itself instead of letting a later
            # recompute overwrite it with zero.
            base = line.settled_amount
        if base:
            line.invoice_base_amount = base
            updated += 1
    return updated


def _relink_orphan_settlement_lines(env):
    """Re-link orphan invoice settlement lines to their current agent row.

    Only when the (invoice line, agent) pair has exactly one current agent row
    and no other settlement line already uses it -- otherwise it is reported,
    not guessed.
    """
    SettlementLine = env["commission.settlement.line"].sudo()
    Agent = env["account.invoice.line.agent"].sudo()
    orphans = SettlementLine.search(
        [
            ("settlement_id.settlement_type", "=", "sale_invoice"),
            ("settlement_id.state", "=", "settled"),
            ("invoice_agent_line_id", "=", False),
            ("invoice_line_id", "!=", False),
        ]
    )
    relinked = 0
    ambiguous = 0
    for line in orphans:
        candidates = Agent.search(
            [
                ("object_id", "=", line.invoice_line_id.id),
                ("agent_id", "=", line.agent_id.id),
            ]
        )
        if len(candidates) != 1:
            ambiguous += 1
            _logger.warning(
                "Linha de fechamento %s sem agente de origem único "
                "(fatura %s, valor %s): revisar manualmente.",
                line.id,
                line.invoice_line_id.move_id.name,
                line.settled_amount,
            )
            continue
        already_used = SettlementLine.search_count(
            [
                ("invoice_agent_line_id", "=", candidates.id),
                ("settlement_id.state", "!=", "cancel"),
            ]
        )
        if already_used:
            ambiguous += 1
            _logger.warning(
                "Linha de fechamento %s (fatura %s, valor %s) tem agente "
                "candidato %s já usado por outra linha; revisar manualmente.",
                line.id,
                line.invoice_line_id.move_id.name,
                line.settled_amount,
                candidates.id,
            )
            continue
        line.invoice_agent_line_id = candidates.id
        relinked += 1
    return relinked, ambiguous


def _resync_commission_sales(env):
    """Rebuild the ``commission.sale.line`` details of historical sales.

    The month base used by the performance closing reads these details; older
    records were synchronized before the details existed, so their base was
    zero. Re-running the idempotent sync restores the detail lines from the
    source orders. Only sales without any detail line are touched, so header
    values that were adjusted by hand are preserved.
    """
    Sale = env["commission.sale"].sudo()
    sales = Sale.search(
        [
            ("source_order_id", "!=", False),
            ("source_order_id.state", "!=", "cancel"),
            ("status", "!=", "cancelled"),
            ("line_ids", "=", False),
        ]
    )
    synced = 0
    failed = 0
    for sale in sales:
        order = sale.source_order_id.exists()
        member = sale.owner_member_id.exists()
        if not order or not member:
            continue
        try:
            order._sync_commission_sale_for_member(member)
            synced += 1
        except Exception:
            failed += 1
            _logger.exception(
                "Falha ao ressincronizar a venda de comissão %s (pedido %s)",
                sale.id,
                order.id,
            )
    return synced, failed


def _recompute_invoice_lines(env):
    """Recompute invoice settlement lines whose base was wrong.

    This covers two cases:
    * agent rows whose ``amount`` was 0 (compute ran before the invoice was
      posted);
    * partial-billing invoices (downpayments) where the commission was
      computed on the full product price instead of being prorated by the
      invoice share of the order.
    Only settlements still in ``settled`` state are touched, so invoiced
    commissions are never rewritten silently.
    """
    SettlementLine = env["commission.settlement.line"].sudo()
    lines = SettlementLine.search(
        [
            ("settlement_id.state", "=", "settled"),
            ("settlement_id.settlement_type", "=", "sale_invoice"),
            ("invoice_agent_line_id", "!=", False),
        ]
    )
    updated = 0
    for line in lines:
        agent_line = line.invoice_agent_line_id
        invoice = agent_line.invoice_id
        base_amount = agent_line._get_settlement_base_amount()
        if base_amount <= 0.0:
            continue
        if (
            invoice
            and invoice.payment_state == "partial"
            and invoice.amount_total
        ):
            amount_paid = invoice.amount_total - (invoice.amount_residual or 0.0)
            ratio = max(0.0, min(amount_paid / invoice.amount_total, 1.0))
            new_amount = base_amount * ratio
        else:
            new_amount = base_amount
        line.invoice_base_amount = base_amount
        if abs(line.settled_amount - new_amount) >= 0.005:
            line.settled_amount = new_amount
            updated += 1
    return updated


def _recompute_crm_lines(env):
    wizard = env["commission.make.settle"].new(
        {"settlement_type": "crm_performance"}
    )
    SettlementLine = env["commission.settlement.line"].sudo()
    lines = SettlementLine.search(
        [
            ("settlement_id.state", "=", "settled"),
            ("settlement_id.settlement_type", "in",
             ("crm_performance", "crm_quarterly_recovery")),
            # Only zero lines are healed automatically: a nonzero historical
            # value may have been manually adjusted and must not be rewritten
            # by an upgrade. The list/form button can recalculate any line.
            ("settled_amount", "=", 0.0),
        ]
    )
    updated = 0
    for line in lines:
        if line.target_id:
            new_amount = wizard._calculate_crm_performance_commission(
                line.target_id
            )
        elif line.quarterly_bonus_id:
            new_amount = line.quarterly_bonus_id.lost_commission_recovered
        else:
            continue
        if abs(line.settled_amount - new_amount) >= 0.005:
            line.settled_amount = new_amount
            updated += 1
    return updated


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    invoice_lines = _backfill_invoice_line(env)
    invoice_base = _backfill_invoice_base(env)
    relinked, ambiguous = _relink_orphan_settlement_lines(env)
    synced, failed = _resync_commission_sales(env)
    invoice_updated = _recompute_invoice_lines(env)
    crm_updated = _recompute_crm_lines(env)
    _logger.info(
        "Fechamento de comissões: invoice_line_id preenchido em %s linha(s); "
        "base congelada em %s; %s linha(s) religada(s) e %s ambígua(s); "
        "%s/%s venda(s) de comissão ressincronizada(s), %s falha(s); "
        "%s linha(s) de fatura recalculada(s); "
        "%s linha(s) de CRM zeradas recalculadas.",
        invoice_lines,
        invoice_base,
        relinked,
        ambiguous,
        synced,
        synced + failed,
        failed,
        invoice_updated,
        crm_updated,
    )
    cr.commit()
