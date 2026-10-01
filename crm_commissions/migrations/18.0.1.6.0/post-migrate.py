# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Rebuilds the commissions of HONORARIO/PROCEDIMENTO lines.

Companion of ``pre-migrate.py``: the settlements built on those lines are
released there, and here the agent lines are recomputed with the new
``_compute_agent_ids`` (which only keeps the order's doctor) and the doctor
settlements are regenerated.

The recompute is needed because ``_compute_agent_ids`` only depends on
``order_id.partner_id``, ``order_id.doctor_id`` and ``order_id.user_id``:
upgrading the module never refreshes existing lines on its own, so the wrongly
computed values would stay in the database.
"""

import logging

from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

_CATEGORY_TERMS = ("HONORARIO", "PROCEDIMENTO")


def get_excluded_category_ids(env):
    """Category ids of HONORARIO/PROCEDIMENTO and all their children."""
    categories = env["product.category"].browse()
    for term in _CATEGORY_TERMS:
        categories |= env["product.category"].search([("name", "ilike", term)])
    if not categories:
        return []
    return env["product.category"].search([("id", "child_of", categories.ids)]).ids


def get_medical_partner_ids(env):
    ResPartner = env["res.partner"]
    return ResPartner.search(
        [("type_partner", "in", list(ResPartner.MEDICAL_AGENT_TYPES))]
    ).ids


def recompute_sale_lines(env, excluded_category_ids):
    """Recompute the agents of every HONORARIO/PROCEDIMENTO order line."""
    lines = env["sale.order.line"].sudo().search(
        [("product_id.categ_id", "in", excluded_category_ids)]
    )
    if not lines:
        return 0
    lines._compute_agent_ids()
    return len(lines)


def recompute_invoice_lines(env, excluded_category_ids):
    """Recompute the agents of the invoice lines on those categories.

    ``account.move.line._compute_agent_ids`` copies the agents of the related
    sale line, so this is what drops the wrong agents from the invoices the
    settlements are generated from. Lines still held by an invoiced settlement
    are skipped: writing a settled agent line raises a ValidationError.
    """
    lines = env["account.move.line"].sudo().search(
        [
            ("move_id.move_type", "in", ("out_invoice", "out_refund")),
            ("product_id.categ_id", "in", excluded_category_ids),
        ]
    )
    if not lines:
        return 0, 0
    blocked = lines.filtered(lambda line: any(line.agent_ids.mapped("settled")))
    skipped = len(blocked)
    recomputable = lines - blocked
    if recomputable:
        recomputable._compute_agent_ids()
    return len(recomputable), skipped


def collect_doctors_to_settle(env, excluded_category_ids):
    """Doctors that must get their settlement back, with their period end.

    Read before regenerating: the settle wizard only picks up the agent lines
    that are not settled yet, which is exactly the rebuilt set.
    """
    agent_lines = env["account.invoice.line.agent"].sudo().search(
        [
            ("object_id.move_id.move_type", "in", ("out_invoice", "out_refund")),
            ("object_id.product_id.categ_id", "in", excluded_category_ids),
            ("settled", "=", False),
        ]
    )
    if not agent_lines:
        return env["res.partner"], None
    doctor_ids = get_medical_partner_ids(env)
    doctors = agent_lines.filtered(
        lambda agent_line: agent_line.agent_id.id in doctor_ids
    ).agent_id
    return doctors, _settlement_cutoff(agent_lines)


def _settlement_cutoff(agent_lines):
    """First day of the period after the latest invoice, for the settle wizard.

    ``_get_period_start`` returns the *start* of the period holding ``date_to``
    and the wizard only takes lines with ``invoice_date < date_to_agent``. The
    cutoff therefore has to sit in a later period than the invoices, otherwise
    the rebuilt lines are silently skipped and no settlement is created.
    """
    if not agent_lines:
        return None
    last = max(agent_lines.mapped("invoice_date"))
    return last + relativedelta(months=1, day=1)


def regenerate_settlements(env, doctors, date_to):
    """Rebuild the doctor settlements with the regular settle wizard."""
    if not doctors or not date_to:
        return 0
    wizard = env["commission.make.settle"].sudo().create(
        {
            "date_to": date_to,
            "settlement_type": "sale_invoice",
            "agent_ids": [(6, 0, doctors.ids)],
        }
    )
    wizard.action_settle()
    return len(
        env["commission.settlement"].sudo().search(
            [("agent_id", "in", doctors.ids), ("state", "!=", "cancel")]
        )
    )


def count_stale_agents(env, excluded_category_ids):
    """Non-doctor agents still sitting on the honorário lines, for the log."""
    sale_lines = env["sale.order.line"].sudo().search(
        [("product_id.categ_id", "in", excluded_category_ids)]
    )
    medical_partner_ids = get_medical_partner_ids(env)
    stale = sale_lines.mapped("agent_ids").filtered(
        lambda agent_line: agent_line.agent_id.id not in medical_partner_ids
    )
    return len(stale)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    excluded_category_ids = get_excluded_category_ids(env)
    if not excluded_category_ids:
        _logger.info("No HONORARIO/PROCEDIMENTO category found, nothing to do")
        return
    _logger.info(
        "Rebuilding commissions on %s category(ies)", len(excluded_category_ids)
    )
    doctors, date_to = collect_doctors_to_settle(env, excluded_category_ids)
    sale_lines = recompute_sale_lines(env, excluded_category_ids)
    invoice_lines, skipped = recompute_invoice_lines(env, excluded_category_ids)
    settlements = regenerate_settlements(env, doctors, date_to)
    env.invalidate_all()
    env.registry.clear_cache()
    _logger.info(
        "Commission rebuild done: %s sale line(s) and %s invoice line(s) "
        "recomputed, %s doctor settlement(s) regenerated",
        sale_lines,
        invoice_lines,
        settlements,
    )
    if skipped:
        _logger.warning(
            "%s invoice line(s) held by an invoiced settlement were skipped and "
            "still need a manual review",
            skipped,
        )
    stale = count_stale_agents(env, excluded_category_ids)
    if stale:
        # Should not happen: a leftover means a non-doctor still earns
        # commission on honorário and the rule is not fully applied.
        _logger.error(
            "Commission rebuild incomplete: %s non-doctor agent line(s) remain on "
            "HONORARIO/PROCEDIMENTO lines and need review",
            stale,
        )
    else:
        _logger.info("Verified: only doctors remain on HONORARIO/PROCEDIMENTO lines")
