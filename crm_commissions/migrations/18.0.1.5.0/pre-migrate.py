# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import SUPERUSER_ID, api


_LEGACY_MANAGER_GROUPS = (
    "crm_commissions.group_crm_commission_manager",
    "crm_commissions.group_commission_manager",
)
_LEGACY_USER_GROUPS = ("crm_commissions.group_crm_commission_user",)
_RESTRICTED_ROLE_GROUPS = (
    "crm_commissions.group_crm_commission_orientadora",
    "crm_commissions.group_crm_commission_sdr",
    "crm_commissions.group_crm_commission_doctor",
    "crm_commissions.group_commission_coordinator",
)


def _groups(env, xmlids):
    return [env.ref(xmlid, raise_if_not_found=False) for xmlid in xmlids]


def _users_in_groups(env, groups):
    group_ids = [group.id for group in groups if group]
    if not group_ids:
        return env["res.users"].browse()
    return env["res.users"].search([("groups_id", "in", group_ids)])


def migrate(cr, version):
    """Move legacy CRM commission memberships to the commission_oca groups.

    The CRM-specific roles (Orientadora, SDR, Doctor and Coordinator) are
    intentionally kept separate. Only the duplicated base User/Manager groups
    are migrated. A legacy User membership is not copied for a restricted role,
    because commission_oca's User rule exposes all settlements.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    oca_user = env.ref(
        "commission_oca.group_commission_user", raise_if_not_found=False
    )
    oca_manager = env.ref(
        "commission_oca.group_commission_manager", raise_if_not_found=False
    )
    if not oca_user or not oca_manager:
        return

    manager_groups = _groups(env, _LEGACY_MANAGER_GROUPS)
    user_groups = _groups(env, _LEGACY_USER_GROUPS)
    restricted_groups = _groups(env, _RESTRICTED_ROLE_GROUPS)

    manager_users = _users_in_groups(env, manager_groups)
    if manager_users:
        manager_users.write({"groups_id": [(4, oca_manager.id)]})

    restricted_users = _users_in_groups(env, restricted_groups)
    user_users = _users_in_groups(env, user_groups) - restricted_users
    migrated_user_users = user_users
    if migrated_user_users:
        migrated_user_users.write({"groups_id": [(4, oca_user.id)]})

    # Remove obsolete manager memberships. Keep a legacy User membership on a
    # restricted role during the transition; it carries no OCA rights and the
    # role selector cleans it up when the role is changed.
    for group in manager_groups:
        users = _users_in_groups(env, [group])
        if users:
            users.write({"groups_id": [(3, group.id)]})
    for group in user_groups:
        users = _users_in_groups(env, [group]) & migrated_user_users
        if users:
            users.write({"groups_id": [(3, group.id)]})

    env.invalidate_all()
    env.registry.clear_cache()
