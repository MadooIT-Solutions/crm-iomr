# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.

"""Invoice commissions must be closed by the invoice payment date.

The OCA ``invoice_state`` field decides whether an invoice commission is
settled when the invoice is issued (``open``) or when it is paid (``paid``).
Some commissions were still configured as ``open``, so the closing settled
invoices that the patient had not paid yet.

From this version on the closing always waits for the payment (the rule is
enforced in ``account.invoice.line.agent._skip_settlement``) and uses the
payment date as the settlement date. This migration aligns the configuration
with the rule so the commission form shows the real behaviour.

Also recomputes ``settled_amount`` of existing invoice settlement lines so
that invoices paid in part (``partial``) get a prorated commission instead of
the full invoiced amount (or zero for lines closed before the fix).
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    commissions = (
        env["commission"]
        .with_context(active_test=False)
        .search(
            [
                ("settlement_type", "=", "sale_invoice"),
                ("invoice_state", "!=", "paid"),
            ]
        )
    )
    if commissions:
        commissions.write({"invoice_state": "paid"})
    _logger.info(
        "Comissoes por fatura: %s regra(s) passaram a ser fechadas pela data "
        "de pagamento.",
        len(commissions),
    )

    # Recompute amount de todas as linhas de agente de faturas postadas e
    # pagas (paid, in_payment, partial, reversed). O amount pode ter ficado
    # zerado se o compute foi executado antes da fatura ser postada.
    agent_lines = env["account.invoice.line.agent"].search(
        [
            ("invoice_id.state", "=", "posted"),
            ("invoice_id.payment_state", "in", ("in_payment", "paid", "partial", "reversed")),
        ]
    )
    if agent_lines:
        env.add_to_compute(
            agent_lines._fields["amount"], agent_lines
        )
        env.flush_all()
        env.invalidate_all()
        _logger.info(
            "Amount recomputado para %s linha(s) de agente de fatura paga.",
            len(agent_lines),
        )

    # Recalculate settled_amount of existing invoice settlement lines.
    # Lines closed before this fix may have settled_amount = 0 or the full
    # invoiced amount instead of the prorated value for partial payments.
    lines = env["commission.settlement.line"].search(
        [
            ("settlement_id.settlement_type", "=", "sale_invoice"),
            ("invoice_agent_line_id", "!=", False),
        ]
    )
    recomputed = 0
    for line in lines:
        agent_line = line.invoice_agent_line_id
        invoice = agent_line.invoice_id
        base_amount = agent_line.amount or 0.0
        if invoice and invoice.payment_state == "partial" and invoice.amount_total:
            amount_paid = invoice.amount_total - (invoice.amount_residual or 0.0)
            ratio = amount_paid / invoice.amount_total
            new_amount = base_amount * ratio
        else:
            new_amount = base_amount
        if abs(line.settled_amount - new_amount) >= 0.005:
            line.settled_amount = new_amount
            recomputed += 1
    if recomputed:
        _logger.info(
            "Liquidacoes de fatura recalculadas: %s linha(s) com settled_amount "
            "ajustado para pagamento proporcional.",
            recomputed,
        )
    cr.commit()
