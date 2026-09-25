# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date

from odoo.exceptions import AccessError
from odoo.tests.common import HttpCase, TransactionCase


class TestRepassesMenuSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_sale_salesman = cls.env.ref("sales_team.group_sale_salesman")
        cls.group_sale_manager = cls.env.ref("sales_team.group_sale_manager")
        cls.group_commission_user = cls.env.ref(
            "crm_commissions.group_crm_commission_user"
        )
        cls.group_commission_manager = cls.env.ref(
            "crm_commissions.group_commission_manager"
        )
        cls.group_crm_commission_manager = cls.env.ref(
            "crm_commissions.group_crm_commission_manager"
        )
        cls.group_sdr = cls.env.ref("crm_commissions.group_crm_commission_sdr")

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

        cls.sale_manager_user = cls.env["res.users"].create(
            {
                "name": "Sales Manager Line Test",
                "login": "sale_manager_line_test",
                "partner_id": cls.agent_other.id,
                "groups_id": [(6, 0, [cls.group_sale_manager.id])],
            }
        )
        cls.sale_manager_env = cls.env(user=cls.sale_manager_user.id)

        cls.internal_user = cls.env["res.users"].create(
            {
                "name": "Internal Menu Test",
                "login": "internal_menu_test",
                "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
        cls.internal_env = cls.env(user=cls.internal_user.id)

        cls.sdr_partner = cls.env["res.partner"].create(
            {
                "name": "SDR Menu Test",
                "type_partner": "sdr",
                "agent": True,
                "agent_type": "sdr",
            }
        )
        cls.sdr_user = cls.env["res.users"].create(
            {
                "name": "SDR Menu Test",
                "login": "sdr_menu_test",
                "partner_id": cls.sdr_partner.id,
                "groups_id": [(6, 0, [cls.group_sdr.id])],
            }
        )
        cls.sdr_env = cls.env(user=cls.sdr_user.id)

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
        cls.sdr_target_own = cls.env["crm.commission.target"].create(
            {
                "agent_id": cls.sdr_partner.id,
                "target_date": date(2026, 2, 1),
                "target_amount": 500.0,
            }
        )
        cls.sdr_bonus_own = cls.env["crm.commission.quarterly.bonus"].search(
            [("agent_id", "=", cls.sdr_partner.id)],
            limit=1,
        )
        cls.sdr_settlement_own = cls.env["commission.settlement"].create(
            {
                "agent_id": cls.sdr_partner.id,
                "date_from": date(2026, 2, 1),
                "date_to": date(2026, 2, 28),
            }
        )
        cls.commission = cls.env["commission"].create(
            {
                "name": "Comissão de teste de acesso",
                "commission_type": "fixed",
                "amount_base_type": "gross_amount",
                "fix_qty": 10.0,
            }
        )
        cls.sdr_settlement_line_own = cls.env["commission.settlement.line"].create(
            {
                "settlement_id": cls.sdr_settlement_own.id,
                "date": date(2026, 2, 1),
                "commission_id": cls.commission.id,
                "settled_amount": 100.0,
            }
        )
        cls.settlement_line_other = cls.env["commission.settlement.line"].create(
            {
                "settlement_id": cls.settlement_other.id,
                "date": date(2026, 1, 1),
                "commission_id": cls.commission.id,
                "settled_amount": 100.0,
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
        crm_root = self.env.ref("crm_commissions.menu_crm_commission_root")
        crm_dashboard = self.env.ref("crm_commissions.menu_crm_commission_dashboard")
        top_root = self.env.ref("crm_commissions.menu_commission_root")
        top_dashboard = self.env.ref("crm_commissions.menu_commission_dashboard")

        visible = self._visible_menu_ids(self.internal_env)
        self.assertNotIn(crm_root.id, visible)
        self.assertNotIn(crm_dashboard.id, visible)
        self.assertNotIn(top_root.id, visible)
        self.assertNotIn(top_dashboard.id, visible)

    def test_03_salesman_does_not_see_targets_menu(self):
        targets = self.env.ref("crm_commissions.menu_crm_commission_targets")

        visible = self.salesman_env["ir.ui.menu"].search([("id", "=", targets.id)])
        self.assertFalse(visible)

    def test_04_salesman_can_read_own_dashboard_records(self):
        target = self.salesman_env["crm.commission.target"].browse(self.target_own.id)
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
        target = self.salesman_env["crm.commission.target"].browse(self.target_other.id)
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

    def test_06_sdr_sees_repasse_and_dashboard_menus(self):
        crm_root = self.env.ref("crm_commissions.menu_crm_commission_root")
        crm_dashboard = self.env.ref("crm_commissions.menu_crm_commission_dashboard")
        top_root = self.env.ref("crm_commissions.menu_commission_root")
        top_dashboard = self.env.ref("crm_commissions.menu_commission_dashboard")

        self.assertIn(self.group_sdr, crm_root.groups_id)
        self.assertIn(self.group_sdr, crm_dashboard.groups_id)
        self.assertIn(self.group_sdr, top_root.groups_id)
        self.assertIn(self.group_sdr, top_dashboard.groups_id)

        visible = self._visible_menu_ids(self.sdr_env)
        self.assertIn(crm_root.id, visible)
        self.assertIn(crm_dashboard.id, visible)
        self.assertIn(top_root.id, visible)
        self.assertIn(top_dashboard.id, visible)

    def test_07_sdr_is_authorized_for_dashboard(self):
        from ..controllers.dashboard import _dashboard_user_allowed

        self.assertTrue(_dashboard_user_allowed(self.sdr_env))

    def test_08_sdr_can_read_own_dashboard_records(self):
        target = self.sdr_env["crm.commission.target"].browse(self.sdr_target_own.id)
        bonus = self.sdr_env["crm.commission.quarterly.bonus"].browse(
            self.sdr_bonus_own.id
        )
        settlement = self.sdr_env["commission.settlement"].browse(
            self.sdr_settlement_own.id
        )
        settlement_line = self.sdr_env["commission.settlement.line"].browse(
            self.sdr_settlement_line_own.id
        )

        target.check_access("read")
        bonus.check_access("read")
        settlement.check_access("read")
        settlement_line.check_access("read")

    def test_09_crm_commission_manager_implies_commission_manager(self):
        self.assertIn(
            self.group_commission_manager,
            self.group_crm_commission_manager.implied_ids,
        )

    def test_10_sdr_cannot_read_other_agent_dashboard_records(self):
        target = self.sdr_env["crm.commission.target"].browse(self.target_other.id)
        bonus = self.sdr_env["crm.commission.quarterly.bonus"].browse(
            self.bonus_other.id
        )
        settlement = self.sdr_env["commission.settlement"].browse(
            self.settlement_other.id
        )
        settlement_line = self.sdr_env["commission.settlement.line"].browse(
            self.settlement_line_other.id
        )

        with self.assertRaises(AccessError):
            target.check_access("read")
        with self.assertRaises(AccessError):
            bonus.check_access("read")
        with self.assertRaises(AccessError):
            settlement.check_access("read")
        with self.assertRaises(AccessError):
            settlement_line.check_access("read")

    def test_11_legacy_own_rules_include_sdr_after_upgrade(self):
        rule_xmlids = (
            "crm_commissions.rule_commission_member_orientadora_own",
            "crm_commissions.rule_commission_target_orientadora_own",
            "crm_commissions.rule_commission_sale_orientadora_own",
            "crm_commissions.rule_commission_sale_line_orientadora_own",
            "crm_commissions.rule_commission_result_orientadora_own",
            "crm_commissions.rule_commission_recovery_orientadora_own",
        )
        for rule_xmlid in rule_xmlids:
            with self.subTest(rule=rule_xmlid):
                rule = self.env.ref(rule_xmlid)
                self.assertIn(self.group_sdr, rule.groups)

    def test_12_sales_manager_can_read_all_settlement_lines(self):
        settlement_line = self.sale_manager_env["commission.settlement.line"].browse(
            self.settlement_line_other.id
        )

        settlement_line.check_access("read")


class TestCommissionDashboardRoute(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sdr_user = cls.env["res.users"].create(
            {
                "name": "SDR Dashboard Route Test",
                "login": "sdr_dashboard_route_test",
                "groups_id": [
                    (
                        6,
                        0,
                        [cls.env.ref("crm_commissions.group_crm_commission_sdr").id],
                    )
                ],
            }
        )

    def test_01_sdr_can_open_and_render_dashboard(self):
        self.authenticate(self.sdr_user.login, "dashboard-route-test")

        response = self.url_open(
            "/dashboard/commission?date_from=2026-02-01&date_to=2026-02-28"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Dashboard de Repasses", response.text)
        self.assertIn(self.sdr_user.partner_id.name, response.text)
