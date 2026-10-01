from . import models
from . import controllers
from . import wizards
from . import wizard


def _ensure_commission_manager_implication(env):
    """Keep CRM managers aligned with the legacy commission manager group.

    The CRM manager group no longer exists (it was dropped together with the
    pre-OCA roles) and this hook runs on every install, so both refs must
    tolerate its absence the same way ``res.users`` does. Resolving them
    strictly made a fresh install of this module crash in post_init_hook.
    """
    crm_manager = env.ref(
        "crm_commissions.group_crm_commission_manager", raise_if_not_found=False
    )
    commission_manager = env.ref(
        "crm_commissions.group_commission_manager", raise_if_not_found=False
    )
    if not crm_manager or not commission_manager:
        return
    if commission_manager not in crm_manager.implied_ids:
        crm_manager.write({"implied_ids": [(4, commission_manager.id)]})


def post_init_hook(env):
    """Initialize group implications and backfill commission aggregates."""
    _ensure_commission_manager_implication(env)
    env["commission.member"]._sync_team_from_partner()
    env["crm.commission.target"]._sync_all_legacy_targets()
    env["crm.commission.quarterly.bonus"]._cron_sync_and_finalize_quarterly_bonuses()
