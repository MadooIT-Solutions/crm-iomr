# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase


class TestCrmCommission(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Commission = cls.env["commission"]
        cls.CommissionProgressiveLine = cls.env["commission.progressive.line"]
        cls.CommissionTarget = cls.env["crm.commission.target"]
        cls.ResPartner = cls.env["res.partner"]
        cls.QuarterlyBonus = cls.env["crm.commission.quarterly.bonus"]
        cls.company = cls.env.ref("base.main_company")

        cls.orientadora = cls.ResPartner.create(
            {
                "name": "Test Orientadora",
                "type_partner": "orientadora",
                "agent": True,
                "agent_type": "orientadora",
            }
        )
        cls.sdr = cls.ResPartner.create(
            {
                "name": "Test SDR",
                "type_partner": "sdr",
                "agent": True,
                "agent_type": "sdr",
            }
        )
        cls.coordenadora = cls.ResPartner.create(
            {
                "name": "Test Coordenadora",
                "type_partner": "coordenadora",
                "agent": True,
                "agent_type": "coordenadora",
            }
        )
        cls.doctor = cls.ResPartner.create(
            {
                "name": "Test Doctor",
                "type_partner": "doctorint",
                "agent": False,
            }
        )

    def test_01_orientadora_onchange_sets_agent(self):
        partner = self.ResPartner.new({"name": "New Orientadora"})
        partner.type_partner = "orientadora"
        partner._onchange_type_partner()
        self.assertTrue(partner.agent)
        self.assertEqual(partner.agent_type, "orientadora")

    def test_02_sdr_onchange_sets_agent(self):
        partner = self.ResPartner.new({"name": "New SDR"})
        partner.type_partner = "sdr"
        partner._onchange_type_partner()
        self.assertTrue(partner.agent)
        self.assertEqual(partner.agent_type, "sdr")

    def test_03_doctor_onchange_is_agent(self):
        partner = self.ResPartner.new({"name": "New Doctor"})
        partner.type_partner = "doctorint"
        partner._onchange_type_partner()
        self.assertTrue(partner.agent)
        self.assertEqual(partner.agent_type, "doctor")

    def test_04_progressive_lines_validation(self):
        commission = self.Commission.create(
            {
                "name": "Test Progressive",
                "commission_type": "progressive",
            }
        )
        self.CommissionProgressiveLine.create(
            {
                "commission_id": commission.id,
                "percent_from": 0.0,
                "percent_to": 50.0,
                "commission_percent": 0.25,
            }
        )
        self.CommissionProgressiveLine.create(
            {
                "commission_id": commission.id,
                "percent_from": 51.0,
                "percent_to": 99.0,
                "commission_percent": 0.45,
            }
        )
        self.assertEqual(len(commission.progressive_line_ids), 2)

    def test_05_compute_progressive_commission(self):
        commission = self.Commission.create(
            {
                "name": "Test Progressive",
                "commission_type": "progressive",
                "fix_qty": 0.0,
                "is_crm_bonus": 0.25,
                "is_crm_penalty": 0.25,
            }
        )
        self.CommissionProgressiveLine.create(
            {
                "commission_id": commission.id,
                "percent_from": 0.0,
                "percent_to": 50.0,
                "commission_percent": 0.25,
                "sequence": 10,
            }
        )
        self.CommissionProgressiveLine.create(
            {
                "commission_id": commission.id,
                "percent_from": 100.0,
                "percent_to": 100.0,
                "commission_percent": 0.75,
                "sequence": 30,
            }
        )
        # Test at 100% performance with CRM OK
        result = commission.compute_progressive_commission(1000.0, 100.0, True)
        self.assertAlmostEqual(result, 10.0)

        # Test at 100% performance with CRM NOT ok
        result_penalty = commission.compute_progressive_commission(1000.0, 100.0, False)
        self.assertAlmostEqual(result_penalty, 5.0)

        # Test at 30% (band 0-50): 0.25% + 0.25% IS-CRM = 0.50%
        result_low = commission.compute_progressive_commission(1000.0, 30.0, True)
        self.assertAlmostEqual(result_low, 5.0)

    def test_07_partner_role_exclusivity(self):
        partner = self.ResPartner.create(
            {"name": "Multi Role Test", "type_partner": "orientadora"}
        )
        partner.write({"type_partner": "sdr"})
        self.assertEqual(partner.type_partner, "sdr")
