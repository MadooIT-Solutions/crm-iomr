# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestRepassesMenuSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_sale_salesman = cls.env.ref("sales_team.group_sale_salesman")
        cls.group_commission_user = cls.env.ref(
            "crm_commissions.group_crm_commission_user"
        )

        cls.agent_own = cls.env["res.partner"].create(
            {
                "name": "Sales Agent Own",
                "type_partner": "orientadora",
                "agent": True,
                "agent_type": "orientadora",
            }
        )
        cls.agent_other = cls.env["res.partner"].create(
            {
                "name": "Sales Agent Other",
                "type_partner": "orientadora",
                "agent": True,
                "agent_type": "orientadora",
            }
        )
        cls.salesman_user = cls.env["res.users"].create(
            {
                "name": "Salesman Menu Test",
                "login": "salesman_menu_test",
                "partner_id": cls.agent_own.id,
                "groups_id": [(6, 0, [cls.group_sale_salesman.id])],
            }
        )
        cls.salesman_env = cls.env(user=cls.salesman_user.id)

        cls.internal_user = cls.env["res.users"].create(
            {
                "name": "Internal Menu Test",
                "login": "internal_menu_test",
                "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
        cls.internal_env = cls.env(user=cls.internal_user.id)

        cls.target_own = cls.env["crm.commission.target"].create(
            {
                "agent_id": cls.agent_own.id,
                "target_date": date.today().replace(day=1),
                "target_amount": 1000.0,
            }
        )
        cls.target_other = cls.env["crm.commission.target"].create(
            {
                "agent_id": cls.agent_other.id,
                "target_date": date.today().replace(day=1),
                "target_amount": 1000.0,
            }
        )
        cls.bonus_own = cls.env["crm.commission.quarterly.bonus"].create(
            {
                "agent_id": cls.agent_own.id,
                "quarter": "Q1",
                "year": 2026,
            }
        )
        cls.bonus_other = cls.env["crm.commission.quarterly.bonus"].create(
            {
                "agent_id": cls.agent_other.id,
                "quarter": "Q1",
                "year": 2026,
            }
        )
        cls.settlement_own = cls.env["commission.settlement"].create(
            {
                "agent_id": cls.agent_own.id,
                "date_from": date(2026, 1, 1),
                "date_to": date(2026, 1, 31),
            }
        )
        cls.settlement_other = cls.env["commission.settlement"].create(
            {
                "agent_id": cls.agent_other.id,
                "date_from": date(2026, 1, 1),
                "date_to": date(2026, 1, 31),
            }
        )

    def _visible_menu_ids(self, env):
        return set(env["ir.ui.menu"].search([]).ids)

    def test_01_salesman_sees_root_and_dashboard(self):
        root = self.env.ref("crm_commissions.menu_crm_commission_root")
        dashboard = self.env.ref("crm_commissions.menu_crm_commission_dashboard")

        self.assertIn(self.group_sale_salesman, root.groups_id)
        self.assertIn(self.group_commission_user, root.groups_id)

        visible = self._visible_menu_ids(self.salesman_env)
        self.assertIn(root.id, visible)
        self.assertIn(dashboard.id, visible)

    def test_02_internal_user_without_sales_does_not_see_root(self):
        root = self.env.ref("crm_commissions.menu_crm_commission_root")
        dashboard = self.env.ref("crm_commissions.menu_crm_commission_dashboard")

        visible = self._visible_menu_ids(self.internal_env)
        self.assertNotIn(root.id, visible)
        self.assertNotIn(dashboard.id, visible)

    def test_03_salesman_does_not_see_targets_menu(self):
        targets = self.env.ref("crm_commissions.menu_crm_commission_targets")

        visible = self.salesman_env["ir.ui.menu"].search(
            [("id", "=", targets.id)]
        )
        self.assertFalse(visible)

    def test_04_salesman_can_read_own_dashboard_records(self):
        target = self.salesman_env["crm.commission.target"].browse(
            self.target_own.id
        )
        bonus = self.salesman_env["crm.commission.quarterly.bonus"].browse(
            self.bonus_own.id
        )
        settlement = self.salesman_env["commission.settlement"].browse(
            self.settlement_own.id
        )

        # Odoo 18: check_access()/has_access() replace the V17-era
        # check_access_rights/check_access_rule API. check_access() raises
        # AccessError when forbidden and returns None when allowed.
        self.assertTrue(target.has_access("read"))
        target.check_access("read")
        self.assertTrue(bonus.has_access("read"))
        bonus.check_access("read")
        self.assertTrue(settlement.has_access("read"))
        settlement.check_access("read")

    def test_05_salesman_cannot_read_other_agent_dashboard_records(self):
        target = self.salesman_env["crm.commission.target"].browse(
            self.target_other.id
        )
        bonus = self.salesman_env["crm.commission.quarterly.bonus"].browse(
            self.bonus_other.id
        )
        settlement = self.salesman_env["commission.settlement"].browse(
            self.settlement_other.id
        )

        with self.assertRaises(AccessError):
            target.check_access("read")
        with self.assertRaises(AccessError):
            bonus.check_access("read")
        with self.assertRaises(AccessError):
            settlement.check_access("read")
