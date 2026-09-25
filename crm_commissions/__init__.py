from . import models
from . import controllers
from . import wizards
from . import wizard


def post_init_hook(env):
    """Backfill monthly targets and quarterly bonuses on install/upgrade."""
    env["crm.commission.target"]._sync_all_legacy_targets()
    env["crm.commission.quarterly.bonus"]._cron_sync_and_finalize_quarterly_bonuses()
