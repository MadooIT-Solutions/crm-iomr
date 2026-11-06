# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.

"""Corrige settled_amount de liquidacoes de fatura ja fechadas.

Recalcula o valor liquidado aplicando o rateio proporcional para faturas
pagas parcialmente (payment_state == 'partial').

Uso (odoo shell, da raiz do repo):
    /home/iomr/odoo/odoo-bin shell \
        -c /home/iomr/odoo/odoo.conf -d odoo18_prod --log-level=info --no-http \
        < crm_commissions/scripts/fix_settled_amount_partial.py
"""

import logging

_logger = logging.getLogger(__name__)


def _fix(cr):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})

    # Recompute amount das linhas de agente de faturas pagas parcialmente,
    # pois o compute nao depende de invoice_id.payment_state e pode estar
    # defasado (zerado se foi computado antes do pagamento).
    agent_lines = env["account.invoice.line.agent"].search(
        [
            ("invoice_id.payment_state", "=", "partial"),
            ("settled", "=", False),
        ]
    )
    if agent_lines:
        env.add_to_compute(
            agent_lines._fields["amount"], agent_lines
        )
        env.flush_all()
        env.invalidate_all()
        _logger.info(
            "Amount recomputado para %s linha(s) de agente de fatura parcial.",
            len(agent_lines),
        )

    # Recalcula settled_amount das linhas de liquidacao de fatura ja fechadas.
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
            "Liquidacoes recalculadas: %s linha(s) com settled_amount ajustado.",
            recomputed,
        )
    cr.commit()


try:
    from odoo import SUPERUSER_ID, api

    _fix(env.cr)
    print("CORRECAO CONCLUIDA COM SUCESSO")
except Exception as exc:  # noqa: BLE01
    _logger.error("Erro: %s", exc)
    import traceback

    _logger.error(traceback.format_exc())
    try:
        env.cr.rollback()
    except Exception:  # noqa: BLE01
        pass
