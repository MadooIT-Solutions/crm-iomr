# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Fill the sales team of the members from their related contact."""
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    members = env["commission.member"].search([("team_id", "=", False)])
    if not members:
        return
    members._sync_team_from_partner()
    _logger.info("Filled sales team for %s commission member(s)", len(members))
