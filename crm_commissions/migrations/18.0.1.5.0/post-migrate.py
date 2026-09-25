# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api


_logger = logging.getLogger(__name__)

_LEGACY_MANAGER_GROUPS = (
    "crm_commissions.group_crm_commission_manager",
    "crm_commissions.group_commission_manager",
)
_LEGACY_USER_GROUPS = ("crm_commissions.group_crm_commission_user",)
_LEGACY_GROUPS = _LEGACY_MANAGER_GROUPS + _LEGACY_USER_GROUPS


def _groups(env, xmlids):
    result = env["res.groups"].browse()
    for xmlid in xmlids:
        group = env.ref(xmlid, raise_if_not_found=False)
        if group:
            result |= group
    return result


def _detach_group_links(env, groups):
    """Remove legacy group links from objects that restrict on delete."""
    if not groups:
        return
    group_ids = groups.ids
    unlink_commands = [(3, group_id) for group_id in group_ids]

    rules = env["ir.rule"].search([("groups", "in", group_ids)])
    if rules:
        rules.write({"groups": unlink_commands})

    menus = env["ir.ui.menu"].search([("groups_id", "in", group_ids)])
    if menus:
        menus.write({"groups_id": unlink_commands})

    views = env["ir.ui.view"].search([("groups_id", "in", group_ids)])
    if views:
        views.write({"groups_id": unlink_commands})

    for action_model in ("ir.actions.act_window", "ir.actions.server"):
        actions = env[action_model].search([("groups_id", "in", group_ids)])
        if actions:
            actions.write({"groups_id": unlink_commands})

    embedded_actions = env["ir.embedded.actions"].search(
        [("groups_ids", "in", group_ids)]
    )
    if embedded_actions:
        embedded_actions.write({"groups_ids": unlink_commands})

    fields = env["ir.model.fields"].search([("groups", "in", group_ids)])
    if fields:
        fields.write({"groups": unlink_commands})

    users = env["res.users"].search([("groups_id", "in", group_ids)])
    if users:
        users.write({"groups_id": unlink_commands})

    implied_groups = env["res.groups"].search([("implied_ids", "in", group_ids)])
    if implied_groups:
        implied_groups.write({"implied_ids": unlink_commands})


def _remap_access_rows(env, groups, manager_group, user_group):
    """Move any ACL that still points at a legacy group to its OCA target."""
    if not groups:
        return
    manager_ids = _groups(env, _LEGACY_MANAGER_GROUPS).ids
    user_ids = _groups(env, _LEGACY_USER_GROUPS).ids
    access_rows = env["ir.model.access"].search([("group_id", "in", groups.ids)])
    for access in access_rows:
        if access.group_id.id in manager_ids:
            access.group_id = manager_group
        elif access.group_id.id in user_ids:
            access.group_id = user_group


def migrate(cr, version):
    """Remove the obsolete CRM User/Manager groups after data has been rewritten."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    legacy_groups = _groups(env, _LEGACY_GROUPS)
    if not legacy_groups:
        return

    manager_group = env.ref(
        "commission_oca.group_commission_manager", raise_if_not_found=False
    )
    user_group = env.ref(
        "commission_oca.group_commission_user", raise_if_not_found=False
    )
    if not manager_group or not user_group:
        return

    _remap_access_rows(env, legacy_groups, manager_group, user_group)
    _detach_group_links(env, legacy_groups)

    # ACL rows are ondelete='restrict'; do not leave a group that cannot be
    # removed because of a stale record from an older module version.
    remaining_access = env["ir.model.access"].search(
        [("group_id", "in", legacy_groups.ids)]
    )
    if remaining_access:
        _logger.warning(
            "CRM commission legacy groups kept: %s access rows still reference them",
            len(remaining_access),
        )
        return

    legacy_groups.unlink()
    env.invalidate_all()
    env.registry.clear_cache()
