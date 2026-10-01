# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date

from odoo import fields
from odoo.tests.common import TransactionCase


class TestLegacyTargetIndicators(TransactionCase):
    """The Metas menu mirrors the fields of "Metas Mensais" (CRM).

    ``commission.target`` must expose month, achieved amount, performance,
    IS-CRM, quarterly target and sales team, either from the linked CRM target
    or computed from the period sales of the member.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.CrmTarget = cls.env["crm.commission.target"]
        cls.LegacyTarget = cls.env["commission.target"]
        cls.Sale = cls.env["commission.sale"]
        cls.team = cls.env["crm.team"].create({"name": "Equipe Metas"})
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Orientadora Metas",
                "type_partner": "orientadora",
                "agent": True,
                "agent_type": "orientadora",
                "crm_team_id": cls.team.id,
            }
        )
        cls.member = cls.env["commission.member"].create(
            {
                "name": "Orientadora Metas",
                "member_type": "orientadora",
                "partner_id": cls.partner.id,
            }
        )

    def _create_sale(self, period_date, amount, crm_pct=100.0, status="confirmed"):
        return self.Sale.create(
            {
                "owner_member_id": self.member.id,
                "date": period_date,
                "patient_name": "Paciente Metas",
                "sale_category": "particular",
                "hospital_gross_amount": amount,
                "crm_pct": crm_pct,
                "status": status,
            }
        )

    def _create_crm_target(self, target_date, amount=1000.0):
        return self.CrmTarget.create(
            {
                "target_scope": "salesperson",
                "agent_id": self.partner.id,
                "target_date": target_date,
                "target_amount": amount,
                "is_crm_score": 97.0,
            }
        )

    def test_01_crm_target_projects_indicators_on_legacy_target(self):
        crm_target = self._create_crm_target(date(2026, 2, 1), amount=2000.0)
        crm_target.write({"achieved_amount": 500.0})
        legacy_target = self.LegacyTarget.search(
            [("crm_target_id", "=", crm_target.id)]
        )

        self.assertEqual(len(legacy_target), 1)
        self.assertEqual(legacy_target.target_date, date(2026, 2, 1))
        self.assertEqual(legacy_target.quarter, "Q1/2026")
        self.assertEqual(legacy_target.achieved_amount, 500.0)
        self.assertEqual(legacy_target.performance_pct, 25.0)
        self.assertEqual(legacy_target.is_crm_score, 97.0)
        self.assertTrue(legacy_target.is_crm_ok)
        self.assertEqual(legacy_target.team_id, self.team)

    def test_02_manual_target_computes_month_and_quarterly_amount(self):
        self.env["commission.target"].with_context(
            crm_commissions_skip_legacy_target_sync=True
        ).create(
            [
                {
                    "member_id": self.member.id,
                    "year": 2026,
                    "month": "1",
                    "individual_target_amount": 1000.0,
                },
                {
                    "member_id": self.member.id,
                    "year": 2026,
                    "month": "2",
                    "individual_target_amount": 2000.0,
                },
                {
                    "member_id": self.member.id,
                    "year": 2026,
                    "month": "5",
                    "individual_target_amount": 4000.0,
                },
            ]
        )
        target = self.LegacyTarget.search(
            [("member_id", "=", self.member.id), ("month", "=", "2")]
        )

        self.assertEqual(target.target_date, date(2026, 2, 1))
        self.assertEqual(target.quarter, "Q1/2026")
        self.assertEqual(target.quarterly_target_amount, 3000.0)

    def test_03_manual_target_uses_period_sales(self):
        target = (
            self.env["commission.target"]
            .with_context(crm_commissions_skip_legacy_target_sync=True)
            .create(
                {
                    "member_id": self.member.id,
                    "year": 2026,
                    "month": "3",
                    "individual_target_amount": 1000.0,
                }
            )
        )
        self._create_sale(date(2026, 3, 10), 400.0, crm_pct=94.0)
        self._create_sale(date(2026, 3, 20), 600.0, crm_pct=98.0)
        self._create_sale(date(2026, 3, 25), 9999.0, status="draft")

        self.assertEqual(target.achieved_amount, 1000.0)
        self.assertEqual(target.performance_pct, 100.0)
        self.assertEqual(target.is_crm_score, 94.0)
        self.assertFalse(target.is_crm_ok)

    def test_04_period_without_sales_is_fully_achieved_zero(self):
        target = (
            self.env["commission.target"]
            .with_context(crm_commissions_skip_legacy_target_sync=True)
            .create(
                {
                    "member_id": self.member.id,
                    "year": 2026,
                    "month": "4",
                    "individual_target_amount": 1500.0,
                }
            )
        )

        self.assertEqual(target.achieved_amount, 0.0)
        self.assertEqual(target.performance_pct, 0.0)
        self.assertEqual(target.is_crm_score, 100.0)
        self.assertTrue(target.is_crm_ok)

    def test_05_metas_views_expose_the_crm_indicators(self):
        tree_arch = self.env.ref("crm_commissions.commission_target_tree").arch
        form_arch = self.env.ref("crm_commissions.commission_target_form").arch
        for field_name in (
            "target_date",
            "individual_target_amount",
            "achieved_amount",
            "performance_pct",
            "is_crm_score",
            "is_crm_ok",
            "quarterly_target_amount",
            "quarter",
            "team_id",
            "state",
        ):
            with self.subTest(field=field_name, view="list"):
                self.assertIn(f'name="{field_name}"', tree_arch)
            with self.subTest(field=field_name, view="form"):
                self.assertIn(f'name="{field_name}"', form_arch)

    def test_06_indicators_are_computed_for_the_whole_period(self):
        for month in ("1", "2", "3"):
            self._create_crm_target(fields.Date.to_date(f"2026-{int(month):02d}-01"))

        targets = self.LegacyTarget.search([("member_id", "=", self.member.id)])
        self.assertEqual(len(targets), 3)
        for target in targets:
            with self.subTest(month=target.month):
                self.assertTrue(target.target_date)
                self.assertEqual(target.quarter, "Q1/2026")
                self.assertEqual(target.quarterly_target_amount, 3000.0)
                self.assertEqual(target.team_id, self.team)
