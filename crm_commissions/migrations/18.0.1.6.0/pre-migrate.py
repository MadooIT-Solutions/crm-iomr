# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Releases the settlements built on the HONORARIO/PROCEDIMENTO agent lines.

The rule is that those categories only commission the order's doctor
(``sale.order.doctor_id``), reached exclusively through
``_add_medical_agents``. Until this version the filter was a deny-list that
removed only ``orientadora`` and ``sdr`` agents, so every other agent type
(``employee``, ``others``, ``coordenadora``, the salesperson added through
``salesman_as_agent`` and non-doctor referrals) kept earning commission on
those lines, and the error propagated to the invoice lines and to the
settlements generated out of them.

Settlements of *every* agent on those lines are released, doctors included.
It is not enough to release only the wrong ones: ``account.invoice.line.agent``
refuses any write while a settlement references it ("You can't modify a
settled line") and ``settled`` is derived from the settlement state, so a
doctor settlement left in place would abort the recompute. The doctor
settlements are rebuilt by ``post-migrate.py`` right after, which is the
"update all doctor settlements" part.

This runs as a *pre*-migration: Odoo calls the 'pre' scripts before
``load_openerp_module``, so the models of this module are not available yet and
this script must stay self-contained.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# Hardcoded on purpose: at pre-migrate time the models of this module are not
# loaded yet, so this script cannot rely on ResPartner.MEDICAL_AGENT_TYPES nor
# on sale.order.line._get_excluded_orientadora_categ_ids.
_MEDICAL_TYPES = ("doctorint", "doctorext")
_CATEGORY_TERMS = ("HONORARIO", "PROCEDIMENTO")


def get_excluded_category_ids(env):
    """Category ids of HONORARIO/PROCEDIMENTO and all their children."""
    categories = env["product.category"].browse()
    for term in _CATEGORY_TERMS:
        categories |= env["product.category"].search([("name", "ilike", term)])
    if not categories:
        return []
    return env["product.category"].search([("id", "child_of", categories.ids)]).ids


def get_affected_invoice_line_ids(env, excluded_category_ids):
    """Invoice lines whose product sits in an excluded category."""
    return env["account.move.line"].sudo().search(
        [
            ("move_id.move_type", "in", ("out_invoice", "out_refund")),
            ("product_id.categ_id", "in", excluded_category_ids),
        ]
    ).ids


def release_settlements(env, affected_invoice_line_ids):
    """Cancel and delete the settlements built on the affected invoice lines.

    Deleting them is safe here: the module is still in test and a settlement is
    a derived projection of the invoice agent lines, which are rebuilt right
    after this script. Settlements already invoiced are kept, because
    ``unlink`` refuses them and they carry generated invoice lines; they are
    reported so they can be reviewed by hand.
    """
    if not affected_invoice_line_ids:
        return 0, 0
    settlements = env["commission.settlement"].sudo().search(
        [("state", "!=", "cancel")]
    )
    if not settlements:
        return 0, 0
    affected = settlements.filtered(
        lambda s: s.line_ids.filtered(
            lambda line: line.invoice_agent_line_id.object_id.id
            in affected_invoice_line_ids
        )
    )
    if not affected:
        return 0, 0
    invoiced = affected.filtered(lambda s: s.state == "invoiced")
    if invoiced:
        _logger.warning(
            "Settlement cleanup: %s invoiced settlement(s) kept and must be "
            "reviewed by hand, their invoice lines will not be recomputed: %s",
            len(invoiced),
            ", ".join(invoiced.mapped("name")) or str(invoiced.ids),
        )
    removable = affected - invoiced
    # Cancel first: 'settled' on the invoice agent lines is derived from the
    # settlement state, and a settled line cannot be recomputed.
    removable.write({"state": "cancel"})
    removed = len(removable)
    removable.unlink()
    return removed, len(invoiced)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    excluded_category_ids = get_excluded_category_ids(env)
    if not excluded_category_ids:
        _logger.info("No HONORARIO/PROCEDIMENTO category found, nothing to do")
        return
    medical_count = env["res.partner"].sudo().search_count(
        [("type_partner", "in", list(_MEDICAL_TYPES))]
    )
    affected_invoice_line_ids = get_affected_invoice_line_ids(
        env, excluded_category_ids
    )
    _logger.info(
        "Releasing settlements on %s honorário invoice line(s) "
        "(%s category(ies), %s doctor(s))",
        len(affected_invoice_line_ids),
        len(excluded_category_ids),
        medical_count,
    )
    removed, kept = release_settlements(env, affected_invoice_line_ids)
    _logger.info(
        "Settlement release done: %s settlement(s) removed, %s kept (invoiced)",
        removed,
        kept,
    )
