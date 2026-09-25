# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date

from odoo import fields
from odoo.tests.common import TransactionCase


class TestTargetSync(TransactionCase):
    """Keep the monthly CRM targets and the legacy commission targets in sync."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.CrmTarget = cls.env["crm.commission.target"]
        cls.LegacyTarget = cls.env["commission.target"]
        cls.Partner = cls.env["res.partner"]
        cls.Member = cls.env["commission.member"]
        cls.partner = cls.Partner.create(
            {
                "name": "Orientadora Target Sync",
                "type_partner": "orientadora",
                "agent": True,
                "agent_type": "orientadora",
            }
        )
        cls.member = cls.Member.create(
            {
                "name": "Orientadora Target Sync",
                "member_type": "orientadora",
                "partner_id": cls.partner.id,
            }
        )

    def _create_target(self, partner=None, target_date=None, amount=1000.0):
        return self.CrmTarget.create(
            {
                "target_scope": "salesperson",
                "agent_id": (partner or self.partner).id,
                "target_date": target_date or fields.Date.to_date("2026-09-01"),
                "target_amount": amount,
            }
        )

    def test_01_crm_target_creates_legacy_target(self):
        target = self._create_target(amount=2500.0)

        legacy_target = self.LegacyTarget.search([("crm_target_id", "=", target.id)])
        self.assertEqual(len(legacy_target), 1)
        self.assertEqual(legacy_target.member_id, self.member)
        self.assertEqual(legacy_target.year, 2026)
        self.assertEqual(legacy_target.month, "9")
        self.assertEqual(legacy_target.individual_target_amount, 2500.0)
        self.assertEqual(legacy_target.origin_type, "auto")
        self.assertEqual(legacy_target.state, target.state)
        self.assertIn(legacy_target, self.member.target_ids)

    def test_02_crm_target_changes_update_legacy_target(self):
        target = self._create_target(amount=2500.0)
        legacy_target_id = self.LegacyTarget.search(
            [("crm_target_id", "=", target.id)]
        ).id
        target.write(
            {
                "target_date": date(2026, 10, 1),
                "target_amount": 3750.0,
            }
        )

        legacy_target = self.LegacyTarget.search([("crm_target_id", "=", target.id)])
        self.assertEqual(len(legacy_target), 1)
        self.assertEqual(legacy_target.id, legacy_target_id)
        self.assertEqual(legacy_target.year, 2026)
        self.assertEqual(legacy_target.month, "10")
        self.assertEqual(legacy_target.individual_target_amount, 3750.0)

    def test_03_crm_target_unlink_removes_legacy_target(self):
        target = self._create_target()
        self.assertTrue(
            self.LegacyTarget.search_count([("crm_target_id", "=", target.id)])
        )

        target.unlink()

        self.assertFalse(
            self.LegacyTarget.search_count([("crm_target_id", "=", target.id)])
        )

    def test_04_backfill_syncs_existing_crm_targets(self):
        target = self.CrmTarget.with_context(
            crm_commissions_skip_legacy_target_sync=True
        ).create(
            {
                "target_scope": "salesperson",
                "agent_id": self.partner.id,
                "target_date": date(2026, 11, 1),
                "target_amount": 1750.0,
            }
        )
        self.assertFalse(
            self.LegacyTarget.search_count([("crm_target_id", "=", target.id)])
        )

        self.CrmTarget._sync_all_legacy_targets()

        legacy_target = self.LegacyTarget.search([("crm_target_id", "=", target.id)])
        self.assertEqual(len(legacy_target), 1)
        self.assertEqual(legacy_target.individual_target_amount, 1750.0)

    def test_05_member_created_after_target_syncs_existing_target(self):
        partner = self.Partner.create(
            {
                "name": "Orientadora without member",
                "type_partner": "orientadora",
                "agent": True,
                "agent_type": "orientadora",
            }
        )
        target = self._create_target(partner=partner, target_date=date(2026, 12, 1))
        self.assertFalse(
            self.LegacyTarget.search_count([("crm_target_id", "=", target.id)])
        )

        member = self.Member.create(
            {
                "name": partner.name,
                "member_type": "orientadora",
                "partner_id": partner.id,
            }
        )

        legacy_target = self.LegacyTarget.search([("crm_target_id", "=", target.id)])
        self.assertEqual(len(legacy_target), 1)
        self.assertEqual(legacy_target.member_id, member)

    def test_06_settlement_line_keeps_target_reference(self):
        target = self._create_target()
        wizard = self.env["commission.make.settle"].new(
            {"settlement_type": "crm_performance"}
        )
        settlement = self.env["commission.settlement"].new(
            {"settlement_type": "crm_performance"}
        )

        values = wizard._prepare_settlement_line_vals(settlement, target)

        self.assertEqual(values["target_id"], target.id)

    def test_07_settlement_action_sets_and_reuses_target(self):
        commission = self.env["commission"].create(
            {
                "name": "Commission for settlement sync",
                "commission_type": "fixed",
                "fix_qty": 1.0,
            }
        )
        self.partner.write(
            {"commission_id": commission.id, "settlement": "monthly"}
        )
        target_date = fields.Date.context_today(self.env.user).replace(day=1)
        target = self._create_target(target_date=target_date, amount=100.0)
        self.env["commission.sale"].create(
            {
                "name": "Sale for settlement sync",
                "owner_member_id": self.member.id,
                "patient_name": "Patient for settlement sync",
                "surgery_type": "catarata",
                "sale_category": "particular",
                "date": target_date,
                "hospital_gross_amount": 50.0,
                "status": "confirmed",
            }
        )
        target._refresh_from_sale_changes()
        self.assertEqual(target.state, "in_progress")

        wizard = self.env["commission.make.settle"].create(
            {
                "date_to": target_date,
                "agent_ids": [(6, 0, [self.partner.id])],
                "settlement_type": "crm_performance",
            }
        )
        wizard.action_settle()
        self.assertEqual(
            self.env["commission.settlement.line"].search_count(
                [("target_id", "=", target.id)]
            ),
            1,
        )

        wizard.action_settle()
        self.assertEqual(
            self.env["commission.settlement.line"].search_count(
                [("target_id", "=", target.id)]
            ),
            1,
        )

    def test_08_manual_legacy_target_is_not_adopted(self):
        manual_target = self.LegacyTarget.create(
            {
                "member_id": self.member.id,
                "year": 2026,
                "month": "9",
                "individual_target_amount": 500.0,
                "origin_type": "manual",
            }
        )
        target = self._create_target(amount=2500.0)

        self.assertFalse(manual_target.crm_target_id)
        self.assertEqual(manual_target.individual_target_amount, 500.0)
        self.assertFalse(
            self.LegacyTarget.search_count([("crm_target_id", "=", target.id)])
        )

    def test_09_backfill_adopts_existing_auto_target(self):
        legacy_target = self.LegacyTarget.create(
            {
                "member_id": self.member.id,
                "year": 2026,
                "month": "10",
                "individual_target_amount": 500.0,
                "origin_type": "auto",
            }
        )
        target = self.CrmTarget.with_context(
            crm_commissions_skip_legacy_target_sync=True
        ).create(
            {
                "target_scope": "salesperson",
                "agent_id": self.partner.id,
                "target_date": date(2026, 10, 1),
                "target_amount": 2500.0,
            }
        )

        self.CrmTarget._sync_all_legacy_targets()

        self.assertEqual(legacy_target.crm_target_id, target)
        self.assertEqual(legacy_target.individual_target_amount, 2500.0)
        self.assertEqual(
            self.LegacyTarget.search_count([("crm_target_id", "=", target.id)]), 1
        )
