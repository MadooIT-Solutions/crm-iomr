"""Recompute sale order line agents after new SDR 1% commission."""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    try:
        from odoo import api, SUPERUSER_ID

        env = api.Environment(cr, SUPERUSER_ID, {})
    except Exception:
        return
    lines = env["sale.order.line"].search([])
    for line in lines:
        try:
            line._compute_agent_ids()
        except Exception as e:
            _logger.warning("Failed to recompute agents for line %s: %s", line.id, e)
    cr.commit()
