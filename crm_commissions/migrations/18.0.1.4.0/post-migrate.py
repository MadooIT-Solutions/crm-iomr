from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Backfill targets and refresh quarterly bonuses when upgrading."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["crm.commission.target"]._sync_all_legacy_targets()
    env["crm.commission.quarterly.bonus"]._cron_sync_and_finalize_quarterly_bonuses()
