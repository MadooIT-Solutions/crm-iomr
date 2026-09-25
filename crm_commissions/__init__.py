from . import models
from . import controllers
from . import wizards
from . import wizard


def _ensure_commission_manager_implication(env):
    """Keep CRM managers aligned with the legacy commission manager group."""
    crm_manager = env.ref("crm_commissions.group_crm_commission_manager")
    commission_manager = env.ref("crm_commissions.group_commission_manager")
    if commission_manager not in crm_manager.implied_ids:
        crm_manager.write({"implied_ids": [(4, commission_manager.id)]})


def post_init_hook(env):
    """Initialize group implications and backfill commission aggregates."""
    _ensure_commission_manager_implication(env)
    env["commission.member"]._sync_team_from_partner()
    env["crm.commission.target"]._sync_all_legacy_targets()
    env["crm.commission.quarterly.bonus"]._cron_sync_and_finalize_quarterly_bonuses()
