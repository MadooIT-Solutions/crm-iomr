# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Re-applies the 50/50 split between the order's doctor and its indication.

Two defects let a sale pay the medical commission twice, both on the
``commission_split_percent`` of the two doctor rows of a line:

1. ``SaleOrderLine._add_medical_agents`` only applied the split to the
   doctors it was adding. A doctor that had already reached the line --
   listed among the customer's agents -- kept the 100% default, so the
   order's doctor and the doctor that indicated the patient were both paid
   the whole amount (or 150% of it when only the first one was already
   there).

2. ``order_id.referred_partner`` was missing from ``_compute_agent_ids``'s
   ``@api.depends``. The field is a stored computed one2many, so the web
   client only refreshes it when a listed dependency changes: picking the
   indicating doctor on an order that already had its lines left the agents
   exactly as they were.

The stored rows keep whatever the old code produced -- the split and the
amount derived from it -- so they are corrected here, on the sale lines and
on the invoice lines, which is where the repasse is actually settled.

This runs as a *post*-migration: ``_get_medical_commission_parties`` and
``_apply_medical_split_rule`` live in the models of this module, and the
``amount`` of each row is a stored compute over the split being fixed.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# Orders that can be affected at all: a doctor to commission and at least
# one indication. Everything else is a no-op in the rule, so it is not even
# loaded.
_ORDER_DOMAIN = [
    ("doctor_id", "!=", False),
    ("referred_partner", "!=", False),
]


def repair_medical_split(env, AgentModel, line_ids):
    """Fix the split of the agent rows of ``line_ids``.

    Returns ``(fixed, blocked)``. ``amount`` is a stored compute over
    ``commission_split_percent``, so correcting the split corrects the money
    with it. Rows that may not be rewritten -- an invoice line held by a
    settlement, which OCA refuses to modify -- are counted as ``blocked``
    and left for a human.
    """
    if not line_ids:
        return 0, 0
    agent_lines = AgentModel.search([("object_id", "in", list(line_ids))])
    if not agent_lines:
        return 0, 0
    blocked = agent_lines.filtered(lambda line: not line._can_change_split())
    to_fix = agent_lines - blocked
    fixed = 0
    if to_fix:
        before = {line: line.commission_split_percent for line in to_fix}
        to_fix._apply_medical_split_rule()
        fixed = sum(
            1 for line in to_fix if line.commission_split_percent != before[line]
        )
    return fixed, len(blocked)


def get_affected(env):
    """The sale lines, and the invoice lines, of the orders that can be wrong."""
    orders = env["sale.order"].sudo().search(_ORDER_DOMAIN)
    if not orders:
        return env["sale.order.line"], env["account.move.line"]
    sale_lines = orders.order_line.filtered(lambda line: not line.display_type)
    invoice_lines = (
        env["account.move.line"]
        .sudo()
        .search([("sale_line_ids", "in", sale_lines.ids)])
    )
    return sale_lines, invoice_lines


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    sale_lines, invoice_lines = get_affected(env)
    if not sale_lines and not invoice_lines:
        _logger.info("No order carries a doctor and an indication, nothing to fix")
        return

    sale_fixed, sale_blocked = repair_medical_split(
        env, env["sale.order.line.agent"], sale_lines.ids
    )
    invoice_fixed, invoice_blocked = repair_medical_split(
        env, env["account.invoice.line.agent"], invoice_lines.ids
    )
    _logger.info(
        "Medical split re-applied on %s sale line agent(s) and %s invoice line "
        "agent(s)",
        sale_fixed,
        invoice_fixed,
    )
    blocked = sale_blocked + invoice_blocked
    if blocked:
        _logger.warning(
            "%s agent line(s) held by a settled settlement were skipped and "
            "still pay the full amount to both doctors: review them by hand",
            blocked,
        )
