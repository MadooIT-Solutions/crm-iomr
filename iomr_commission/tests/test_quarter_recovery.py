from odoo.tests import TransactionCase


class TestQuarterRecovery(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.policy = cls.env["commission.policy"].create({
            "name": "Policy Test",
            "date_start": "2026-01-01",
            "crm_bonus_rate": 0.25,
            "crm_penalty_rate": 0.25,
        })
        cls.env["commission.policy.line"].create([
            {"policy_id": cls.policy.id, "sequence": 10,
             "delivery_pct_from": 0.0, "delivery_pct_to": 100.0, "base_rate": 0.75},
        ])
        partner = cls.env["res.partner"].create({
            "name": "Ana Test",
            "type_partner": "orientadora",
        })
        cls.member = cls.env["commission.member"].create({
            "name": "Ana Test",
            "member_type": "orientadora",
            "partner_id": partner.id,
        })

    def test_recovery_100_percent_quarter(self):
        """100% quarter triggers recovery calculation"""
        recovery = self.env["commission.recovery"].create({
            "member_id": self.member.id,
            "quarter": "Q1",
            "year": 2026,
            "quarter_target_amount": 300000.0,
            "quarter_sales_amount": 300000.0,
            "expected_commission_amount": 3000.0,
            "calculated_commission_amount": 2500.0,
        })
        self.assertTrue(recovery.quarter_delivery_pct >= 100)
        self.assertEqual(recovery.recovery_amount, 500.0)
        self.assertEqual(recovery.state, "recovered")

    def test_recovery_below_100_percent(self):
        """Below 100% quarter has no recovery"""
        recovery = self.env["commission.recovery"].create({
            "member_id": self.member.id,
            "quarter": "Q1",
            "year": 2026,
            "quarter_target_amount": 300000.0,
            "quarter_sales_amount": 250000.0,
            "expected_commission_amount": 3000.0,
            "calculated_commission_amount": 2500.0,
        })
        self.assertTrue(recovery.quarter_delivery_pct < 100)
        self.assertEqual(recovery.recovery_amount, 0.0)
        self.assertNotEqual(recovery.state, "recovered")
