# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Fixes the commission base of the repasse: real taxes, and no fee payout.

Two defects, both on the doctor repasse, corrected together because the
second cancelled part of the first.

1. The deduction of "impostos" was a fixed percentage stored on the
   commission (16,33% / 11,73%) summed with the card fee and applied over
   the untaxed ``price_subtotal``. That number had to be kept in sync by
   hand and the card fee was discounted over a base smaller than the one
   the acquirer actually charges, so the deduction never matched the money
   that left the account. The repasse commissions now carry
   ``deduct_taxes``: the taxes come from the line's own ``tax_ids``
   (``price_total - price_subtotal``) and the card fee is taken over
   ``price_total``, the same base ``sale_credit_card_fee`` uses.

2. ``sale_credit_card_fee`` writes its fee onto the invoice as a plain
   service product, indistinguishable from a sale. The line carries no
   ``sale_line_ids``, so ``_compute_agent_ids`` fell through to the
   customer agents and paid the orientadora and the coordenadora a
   commission *on the very fee that had just been discounted from their
   base* -- the cost was coming back in as income. The agents on those
   lines are removed here and the products are flagged commission free.

This runs as a *post*-migration: the ``commission`` records written by
``data/crm_commission_data.xml`` only exist once the module is loaded, and the
agent amounts are recomputed with the models already in place.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

_REPASSE_XMLIDS = (
    "crm_commissions.commission_doctor_consulta",
    "crm_commissions.commission_doctor_exame",
    "crm_commissions.commission_doctor_cirurgia",
)

# Kept in sync with ``models/commission_mixin.py``: a pre-migration script
# cannot rely on the models of this module being loaded yet.
_CARD_FEE_PRODUCT_XMLIDS = (
    "sale_credit_card_fee.product_credit_card_fee",
    "l10n_br_sale_credit_card_fee.product_credit_card_fee",
)


def switch_commissions_to_line_taxes(env):
    """Turn on the real-tax deduction on the repasse commissions."""
    switched = []
    for xmlid in _REPASSE_XMLIDS:
        commission = env.ref(xmlid, raise_if_not_found=False)
        if not commission:
            continue
        if commission.deduct_taxes and not commission.tax_deduction_pct:
            continue
        commission.write({"deduct_taxes": True, "tax_deduction_pct": 0.0})
        switched.append(commission.name)
    return switched


def recompute_agent_amounts(env, AgentModel, domain):
    """Refresh the stored commission amount of the matching agent lines.

    ``amount`` is stored and its ``@api.depends`` does not include the new
    ``deduct_taxes`` flag, so upgrading the module leaves the old figures in
    the database. Touching ``commission_id`` is enough to trigger a recompute.

    Lines held by an invoiced settlement are skipped: ``account.invoice.line.agent``
    refuses to write a settled line ("You can't modify a settled line"), so
    they are reported instead of being silently left behind.
    """
    agent_lines = AgentModel.sudo().search(domain)
    if not agent_lines:
        return 0, 0
    blocked = agent_lines.filtered(lambda line: any(line.mapped("settled")))
    recomputable = agent_lines - blocked
    if recomputable:
        recomputable.modified(["commission_id"])
    return len(recomputable), len(blocked)


def get_card_fee_product_ids(env):
    """Ids of the products that bill the card administrator fee."""
    products = env["product.product"].browse()
    for xmlid in _CARD_FEE_PRODUCT_XMLIDS:
        product = env.ref(xmlid, raise_if_not_found=False)
        if product:
            products |= product
    return products.ids


def get_card_fee_invoice_line_ids(env, product_ids):
    """Invoice lines carrying the card fee, in customer invoices."""
    if not product_ids:
        return []
    return (
        env["account.move.line"]
        .sudo()
        .search(
            [
                ("move_id.move_type", "in", ("out_invoice", "out_refund")),
                ("product_id", "in", product_ids),
            ]
        )
        .ids
    )


def release_fee_settlements(env, invoice_line_ids):
    """Cancel and delete the settlements built on the card fee lines.

    Same reasoning as the honorário rebuild in ``18.0.1.6.0``: a settlement
    is a projection of the invoice agent lines, which are deleted right
    after, and a settlement left in place would keep its agent lines
    settled and abort the deletion ("You can't modify a settled line").
    Settlements already invoiced carry generated invoice lines, so they
    are kept and reported.
    """
    if not invoice_line_ids:
        return 0, 0
    settlements = (
        env["commission.settlement"].sudo().search([("state", "!=", "cancel")])
    )
    if not settlements:
        return 0, 0
    affected = settlements.filtered(
        lambda s: s.line_ids.filtered(
            lambda line: line.invoice_agent_line_id.object_id.id in invoice_line_ids
        )
    )
    if not affected:
        return 0, 0
    invoiced = affected.filtered(lambda s: s.state == "invoiced")
    if invoiced:
        _logger.warning(
            "Card fee cleanup: %s invoiced settlement(s) kept and must be "
            "reviewed by hand, their invoice lines will not be recomputed: %s",
            len(invoiced),
            ", ".join(invoiced.mapped("name")) or str(invoiced.ids),
        )
    removable = affected - invoiced
    # Cancel first: 'settled' on the invoice agent lines is derived from
    # the settlement state, and a settled line cannot be deleted.
    removable.write({"state": "cancel"})
    removed = len(removable)
    removable.unlink()
    return removed, len(invoiced)


def drop_fee_agent_lines(env, product_ids):
    """Delete the agents wrongly attached to the card fee invoice lines.

    ``_compute_agent_ids`` no longer builds them, but the stored ones would
    survive the upgrade and keep paying the orientadora and the coordenadora
    on the fee.
    """
    invoice_line_ids = get_card_fee_invoice_line_ids(env, product_ids)
    if not invoice_line_ids:
        return 0, 0
    agent_lines = (
        env["account.invoice.line.agent"]
        .sudo()
        .search([("object_id", "in", invoice_line_ids)])
    )
    if not agent_lines:
        return 0, 0
    blocked = agent_lines.filtered(lambda line: any(line.mapped("settled")))
    skipped = len(blocked)
    (agent_lines - blocked).unlink()
    return len(agent_lines) - skipped, skipped


def clear_fee_product_flag(env, product_ids):
    """Flag the card fee products as commission free.

    Defence in depth: ``_compute_agent_ids`` already skips these lines, and
    the flag also short-circuits ``_get_commission_amount``, so a commission
    attached to one of them by any other path pays zero.
    """
    products = env["product.product"].browse(product_ids)
    if not products:
        return 0
    to_flag = products.filtered(lambda product: not product.commission_free)
    to_flag.write({"commission_free": True})
    return len(to_flag)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    switched = switch_commissions_to_line_taxes(env)
    if not switched:
        _logger.info("Repasse commissions already deduct the real line taxes")
    else:
        _logger.info("Switched to real line taxes on: %s", ", ".join(switched))
    env.flush_all()

    base_domain = [("commission_id.amount_base_type", "=", "net_amount_deduction")]
    sale_done, sale_skipped = recompute_agent_amounts(
        env, env["sale.order.line.agent"], base_domain
    )
    invoice_done, invoice_skipped = recompute_agent_amounts(
        env, env["account.invoice.line.agent"], base_domain
    )
    _logger.info(
        "Repasse amounts recomputed on %s sale line agent(s) and %s invoice "
        "line agent(s)",
        sale_done,
        invoice_done,
    )
    skipped = sale_skipped + invoice_skipped
    if skipped:
        _logger.warning(
            "%s agent line(s) held by a settled settlement were skipped and "
            "still show the old fixed-percentage base: review them by hand",
            skipped,
        )

    card_fee_product_ids = get_card_fee_product_ids(env)
    if not card_fee_product_ids:
        _logger.info("No card fee product installed, nothing to clean up")
        return
    invoice_line_ids = get_card_fee_invoice_line_ids(env, card_fee_product_ids)
    _logger.info(
        "Card fee cleanup: %s invoice line(s) found on %s product(s)",
        len(invoice_line_ids),
        len(card_fee_product_ids),
    )
    settlements, kept = release_fee_settlements(env, invoice_line_ids)
    dropped, fee_skipped = drop_fee_agent_lines(env, card_fee_product_ids)
    flagged = clear_fee_product_flag(env, card_fee_product_ids)
    _logger.info(
        "Card fee cleanup done: %s settlement(s) removed, %s agent line(s) "
        "dropped, %s product(s) flagged commission free",
        settlements,
        dropped,
        flagged,
    )
    if kept or fee_skipped:
        _logger.warning(
            "Card fee cleanup incomplete: %s invoiced settlement(s) kept and "
            "%s agent line(s) still settled: review them by hand",
            kept,
            fee_skipped,
        )
