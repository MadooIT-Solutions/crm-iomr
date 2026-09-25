# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase


class TestOdooS18ViewModes(TransactionCase):
    """Odoo 18 dropped the 'tree' view type (renamed to 'list').

    act_window actions whose view_mode still contains 'tree' make the web
    client throw: "View types not defined tree found in act_window action X".
    Keep every module action on 'list'.
    """

    def _get_module_actions(self):
        return self.env["ir.actions.act_window"].search([]).filtered(
            lambda action: self.env["ir.model.data"].search_count(
                [
                    ("model", "=", "ir.actions.act_window"),
                    ("res_id", "=", action.id),
                    ("module", "=", "crm_commissions"),
                ]
            )
        )

    def test_01_no_action_uses_tree_view_mode(self):
        actions = self._get_module_actions()
        self.assertTrue(actions)
        for action in actions:
            self.assertNotIn(
                "tree",
                action.view_mode.split(","),
                "act_window %s (%s) must use 'list' instead of 'tree' in "
                "view_mode (Odoo 17/18)" % (action.name, action.id),
            )

    def test_02_each_list_view_mode_has_a_list_view(self):
        actions = self._get_module_actions()
        for action in actions:
            if "list" not in action.view_mode.split(","):
                continue
            self.assertTrue(
                self.env["ir.ui.view"].search(
                    [
                        ("model", "=", action.res_model),
                        ("type", "=", "list"),
                    ],
                    limit=1,
                ),
                "act_window %s (%s) declares view_mode 'list' but no list "
                "view is defined for %s"
                % (action.name, action.id, action.res_model),
            )