from odoo.tests import TransactionCase


class TestCommissionRules(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.policy = cls.env["commission.policy"].create({
            "name": "Policy 2026 Test",
            "date_start": "2026-01-01",
            "margin_min_pct": 35.0,
            "crm_min_pct": 95.0,
            "max_discount_pct": 5.0,
            "crm_bonus_rate": 0.25,
            "crm_penalty_rate": 0.25,
        })
        cls.env["commission.policy.line"].create([
            {"policy_id": cls.policy.id, "sequence": 10,
             "delivery_pct_from": 0.0, "delivery_pct_to": 50.0, "base_rate": 0.25},
            {"policy_id": cls.policy.id, "sequence": 20,
             "delivery_pct_from": 51.0, "delivery_pct_to": 80.0, "base_rate": 0.45},
            {"policy_id": cls.policy.id, "sequence": 30,
             "delivery_pct_from": 81.0, "delivery_pct_to": 100.0, "base_rate": 0.75},
            {"policy_id": cls.policy.id, "sequence": 40,
             "delivery_pct_from": 101.0, "delivery_pct_to": 120.0, "base_rate": 1.25},
            {"policy_id": cls.policy.id, "sequence": 50,
             "delivery_pct_from": 120.01, "delivery_pct_to": 999.0, "base_rate": 1.75},
        ])
        partner = cls.env["res.partner"].create({
            "name": "Ana Orientadora",
            "type_partner": "orientadora",
        })
        cls.member = cls.env["commission.member"].create({
            "name": "Ana Orientadora",
            "member_type": "orientadora",
            "partner_id": partner.id,
        })

    def _create_result(self, period_code, base_amount, crm_score=100.0):
        return self.env["commission.result"].create({
            "member_id": self.member.id,
            "period_code": period_code,
            "policy_id": self.policy.id,
            "commission_base_amount": base_amount,
            "target_amount": 100000.0,
            "is_crm_score": crm_score,
            "state": "draft",
        })

    def test_rate_band_0_to_50(self):
        """0% to 50% performance = 0.25% rate"""
        result = self._create_result("2026-01", 30000.0)
        result.action_calculate()
        self.assertEqual(result.base_rate, 0.25)
        self.assertEqual(result.range_label, "0% - 50%")

    def test_rate_band_51_to_80(self):
        """51% to 80% performance = 0.45% rate"""
        result = self._create_result("2026-01", 65000.0)
        result.action_calculate()
        self.assertEqual(result.base_rate, 0.45)
        self.assertEqual(result.range_label, "51% - 80%")

    def test_rate_band_81_to_100(self):
        """81% to 100% performance = 0.75% rate"""
        result = self._create_result("2026-01", 81000.0)
        result.action_calculate()
        self.assertEqual(result.base_rate, 0.75)
        self.assertEqual(result.range_label, "81% - 100%")

        result2 = self._create_result("2026-02", 100000.0)
        result2.action_calculate()
        self.assertEqual(result2.base_rate, 0.75)
        self.assertEqual(result2.range_label, "81% - 100%")

    def test_rate_band_101_to_120(self):
        """101% to 120% performance = 1.25% rate"""
        result = self._create_result("2026-01", 110000.0)
        result.action_calculate()
        self.assertEqual(result.base_rate, 1.25)

    def test_rate_band_above_120(self):
        """Above 120% performance = 1.75% rate"""
        result = self._create_result("2026-01", 130000.0)
        result.action_calculate()
        self.assertEqual(result.base_rate, 1.75)

    def test_crm_bonus_above_95(self):
        """CRM >= 95% adds bonus rate"""
        result = self._create_result("2026-01", 100000.0, crm_score=95.0)
        result.action_calculate()
        self.assertTrue(result.is_crm_ok)
        self.assertEqual(result.crm_bonus_rate, 0.25)
        self.assertEqual(result.final_rate, 1.0)

    def test_crm_penalty_below_95(self):
        """CRM < 95% applies penalty"""
        result = self._create_result("2026-01", 100000.0, crm_score=94.9)
        result.action_calculate()
        self.assertFalse(result.is_crm_ok)
        self.assertEqual(result.crm_bonus_rate, -0.25)
        self.assertEqual(result.final_rate, 0.5)

    def test_surgery_medical_fee_excluded(self):
        """Medical fee never commissions"""
        sale = self.env["commission.sale"].create({
            "owner_member_id": self.member.id,
            "patient_name": "John Doe",
            "sale_category": "particular",
            "date": "2026-01-15",
            "hospital_gross_amount": 50000.0,
            "medical_fee_amount": 10000.0,
        })
        self.env["commission.sale.line"].create([
            {"sale_id": sale.id, "line_type": "hospital", "amount": 50000.0},
            {"sale_id": sale.id, "line_type": "medical_fee", "amount": 10000.0},
        ])
        sale.action_confirm()
        commissionable = sale._get_commissionable_amount()
        self.assertEqual(commissionable, 50000.0)

    def test_surgery_lio_package_excluded(self):
        """Package LIO never commissions"""
        sale = self.env["commission.sale"].create({
            "owner_member_id": self.member.id,
            "patient_name": "John Doe",
            "sale_category": "saude_todos",
            "date": "2026-01-15",
            "lio_package_amount": 30000.0,
            "hospital_gross_amount": 50000.0,
        })
        self.env["commission.sale.line"].create([
            {"sale_id": sale.id, "line_type": "lio_package", "amount": 30000.0},
            {"sale_id": sale.id, "line_type": "hospital", "amount": 50000.0},
        ])
        sale.action_confirm()
        commissionable = sale._get_commissionable_amount()
        self.assertEqual(commissionable, 50000.0)

    def test_surgery_lio_upgrade_commissions(self):
        """LIO upgrade commissions"""
        sale = self.env["commission.sale"].create({
            "owner_member_id": self.member.id,
            "patient_name": "John Doe",
            "sale_category": "convenio",
            "date": "2026-01-15",
            "lio_package_amount": 30000.0,
            "lio_upgrade_amount": 15000.0,
            "hospital_gross_amount": 50000.0,
        })
        self.env["commission.sale.line"].create([
            {"sale_id": sale.id, "line_type": "lio_package", "amount": 30000.0},
            {"sale_id": sale.id, "line_type": "lio_upgrade", "amount": 15000.0},
            {"sale_id": sale.id, "line_type": "hospital", "amount": 50000.0},
        ])
        sale.action_confirm()
        self.assertTrue(sale.has_lio_upgrade)
        commissionable = sale._get_commissionable_amount()
        self.assertEqual(commissionable, 65000.0)

    def test_lens_gelatinous_with_exam(self):
        """Lens: gelatinous with exam = 1.5%"""
        sale = self.env["commission.sale"].create({
            "owner_member_id": self.member.id,
            "patient_name": "Lens Patient",
            "sale_category": "particular",
            "date": "2026-01-15",
            "hospital_gross_amount": 10000.0,
            "is_lens_sale": True,
            "lens_type": "gelatinous",
            "lens_commission_type": "with_exam",
        })
        rate = sale._get_lens_rate()
        self.assertEqual(rate, 1.5)

    def test_lens_gelatinous_without_exam(self):
        """Lens: gelatinous without exam (>3 months) = 5%"""
        sale = self.env["commission.sale"].create({
            "owner_member_id": self.member.id,
            "patient_name": "Lens Patient",
            "sale_category": "particular",
            "date": "2026-01-15",
            "hospital_gross_amount": 10000.0,
            "is_lens_sale": True,
            "lens_type": "gelatinous",
            "lens_commission_type": "without_exam",
        })
        rate = sale._get_lens_rate()
        self.assertEqual(rate, 5.0)

    def test_lens_rigid_always_1_5(self):
        """Lens: rigid always 1.5%"""
        sale = self.env["commission.sale"].create({
            "owner_member_id": self.member.id,
            "patient_name": "Lens Patient",
            "sale_category": "particular",
            "date": "2026-01-15",
            "hospital_gross_amount": 10000.0,
            "is_lens_sale": True,
            "lens_type": "rigid",
        })
        rate = sale._get_lens_rate()
        self.assertEqual(rate, 1.5)

    def test_margin_validation(self):
        """Margin calculation works correctly"""
        sale = self.env["commission.sale"].create({
            "owner_member_id": self.member.id,
            "patient_name": "John Doe",
            "sale_category": "particular",
            "date": "2026-01-15",
            "hospital_gross_amount": 100000.0,
        })
        self.assertAlmostEqual(sale.margin_pct, 35.0, places=1)
