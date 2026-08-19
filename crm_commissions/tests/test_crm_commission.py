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

    def test_08_sdr_extra_commission_split(self):
        commission = self.Commission.create(
            {
                "name": "Test Progressive",
                "commission_type": "progressive",
            }
        )
        vals = [
            (0, 0, {"agent_id": self.orientadora.id, "commission_id": commission.id})
        ]
        line = self.env["sale.order.line"].new({})
        result = line._apply_sdr_commission_split(vals, self.sdr)

        sdr_lines = [v for v in result if v[2].get("agent_id") == self.sdr.id]
        self.assertTrue(sdr_lines)
        self.assertAlmostEqual(sdr_lines[0][2]["commission_split_percent"], 25.0)
        self.assertEqual(sdr_lines[0][2]["commission_id"], commission.id)

        orientadora_lines = [
            v for v in result if v[2].get("agent_id") == self.orientadora.id
        ]
        self.assertTrue(orientadora_lines)
        self.assertAlmostEqual(
            orientadora_lines[0][2]["commission_split_percent"], 75.0
        )

    def test_09_sdr_split_guards(self):
        commission = self.Commission.create(
            {
                "name": "Test Progressive",
                "commission_type": "progressive",
            }
        )
        line = self.env["sale.order.line"].new({})

        vals = [
            (0, 0, {"agent_id": self.orientadora.id, "commission_id": commission.id}),
            (0, 0, {"agent_id": self.sdr.id, "commission_id": commission.id}),
        ]
        result = line._apply_sdr_commission_split(vals, self.sdr)
        sdr_lines = [v for v in result if v[2].get("agent_id") == self.sdr.id]
        self.assertEqual(len(sdr_lines), 1)

        vals2 = [
            (0, 0, {"agent_id": self.sdr.id, "commission_id": commission.id})
        ]
        result2 = line._apply_sdr_commission_split(vals2, self.sdr)
        self.assertEqual(len(result2), 1)

        result3 = line._apply_sdr_commission_split(vals, False)
        self.assertEqual(len(result3), 2)

    def test_10_get_sdr_partner_from_rotation(self):
        sdr_user = self.env["res.users"].create(
            {
                "name": "SDR User",
                "login": "sdr_rotation_login",
                "partner_id": self.sdr.id,
                "company_id": self.company.id,
                "company_ids": [(6, 0, [self.company.id])],
            }
        )
        customer = self.ResPartner.create({"name": "Rotation Customer"})
        lead = self.env["crm.lead"].create(
            {
                "name": "Opportunity Via SDR",
                "partner_id": customer.id,
                "user_id": sdr_user.id,
            }
        )
        self.assertFalse(lead._get_sdr_partner_from_rotation())

        self.env["crm.lead.rotation"].create(
            {
                "lead_id": lead.id,
                "user_to_id": sdr_user.id,
                "rotation_sequence": 1,
                "rotation_type": "lost_sdr",
            }
        )
        self.assertEqual(lead._get_sdr_partner_from_rotation(), self.sdr)

    def _create_sale_line(self, partner, product, user_id=False):
        order = self.env["sale.order"].create(
            {"partner_id": partner.id, "user_id": user_id or False}
        )
        return self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": 1,
                "price_unit": 100.0,
            }
        )

    def _create_product(self, name, categ):
        return self.env["product.product"].create(
            {
                "name": name,
                "categ_id": categ.id,
                "type": "consu",
                "sale_ok": True,
                "list_price": 100.0,
            }
        )

    def test_11_agent_rule_fixed_commission_by_category(self):
        fixed = self.Commission.create(
            {"name": "Teste Fixa 1%", "commission_type": "fixed", "fix_qty": 1.0}
        )
        prog = self.Commission.create(
            {"name": "Teste Progressiva", "commission_type": "progressive"}
        )
        self.CommissionProgressiveLine.create(
            {
                "commission_id": prog.id,
                "percent_from": 0.0,
                "percent_to": 100.0,
                "commission_percent": 0.5,
                "sequence": 10,
            }
        )
        self.orientadora.commission_id = prog.id
        cat_extra = self.env["product.category"].create({"name": "TESTE EXTRA"})
        cat_lio = self.env["product.category"].create({"name": "TESTE LIO"})
        cat_lio_sub = self.env["product.category"].create(
            {"name": "TESTE LIO SUB", "parent_id": cat_lio.id}
        )
        cat_other = self.env["product.category"].create({"name": "TESTE OUTRA"})
        prod_extra = self._create_product("Produto Extra", cat_extra)
        prod_lio = self._create_product("Lente LIO", cat_lio_sub)
        prod_other = self._create_product("Produto Outro", cat_other)
        customer = self.ResPartner.create({"name": "Cliente Teste"})
        customer.agent_ids = [(6, 0, [self.orientadora.id])]

        self.env["commission.agent.rule"].create(
            {
                "agent_id": self.orientadora.id,
                "commission_id": fixed.id,
                "categ_ids": [(6, 0, [cat_extra.id])],
                "sequence": 10,
            }
        )
        prog.categ_ids = [(6, 0, [cat_lio.id, cat_lio_sub.id])]

        line_extra = self._create_sale_line(customer, prod_extra)
        line_extra._compute_agent_ids()
        agent = line_extra.agent_ids.filtered(
            lambda a: a.agent_id == self.orientadora
        )
        self.assertTrue(agent)
        self.assertEqual(agent.commission_id, fixed)
        self.assertAlmostEqual(agent.amount, 1.0)

        line_lio = self._create_sale_line(customer, prod_lio)
        line_lio._compute_agent_ids()
        agent_lio = line_lio.agent_ids.filtered(
            lambda a: a.agent_id == self.orientadora
        )
        self.assertTrue(agent_lio)
        self.assertEqual(agent_lio.commission_id, prog)
        self.assertAlmostEqual(agent_lio.amount, 0.75)

        line_other = self._create_sale_line(customer, prod_other)
        line_other._compute_agent_ids()
        agent_other = line_other.agent_ids.filtered(
            lambda a: a.agent_id == self.orientadora
        )
        self.assertFalse(agent_other)

    def test_13_salesperson_flow_fixed_commission(self):
        fixed = self.Commission.create(
            {"name": "Teste Fixa 1%", "commission_type": "fixed", "fix_qty": 1.0}
        )
        prog = self.Commission.create(
            {"name": "Teste Progressiva", "commission_type": "progressive"}
        )
        self.CommissionProgressiveLine.create(
            {
                "commission_id": prog.id,
                "percent_from": 0.0,
                "percent_to": 100.0,
                "commission_percent": 0.5,
                "sequence": 10,
            }
        )
        self.orientadora.commission_id = prog.id
        cat_extra = self.env["product.category"].create({"name": "TESTE EXTRA"})
        cat_lio = self.env["product.category"].create({"name": "TESTE LIO"})
        cat_lio_sub = self.env["product.category"].create(
            {"name": "TESTE LIO SUB", "parent_id": cat_lio.id}
        )
        cat_hon = self.env["product.category"].create(
            {"name": "HONORARIO TESTE"}
        )
        cat_other = self.env["product.category"].create({"name": "TESTE OUTRA"})
        prod_extra = self._create_product("Produto Extra", cat_extra)
        prod_lio = self._create_product("Lente LIO", cat_lio_sub)
        prod_hon = self._create_product("Honorario", cat_hon)
        prod_other = self._create_product("Produto Outro", cat_other)
        customer = self.ResPartner.create({"name": "Cliente Teste"})

        self.orientadora.salesman_as_agent = True
        sales_user = self.env["res.users"].create(
            {
                "name": "Sales Orientadora",
                "login": "sales_orientadora_login",
                "partner_id": self.orientadora.id,
                "company_id": self.company.id,
                "company_ids": [(6, 0, [self.company.id])],
            }
        )
        self.env["commission.agent.rule"].create(
            {
                "agent_id": self.orientadora.id,
                "commission_id": fixed.id,
                "categ_ids": [(6, 0, [cat_extra.id])],
                "sequence": 10,
            }
        )
        prog.categ_ids = [(6, 0, [cat_lio.id, cat_lio_sub.id])]

        line_extra = self._create_sale_line(customer, prod_extra, user_id=sales_user.id)
        line_extra._compute_agent_ids()
        agent = line_extra.agent_ids.filtered(
            lambda a: a.agent_id == self.orientadora
        )
        self.assertTrue(agent)
        self.assertEqual(agent.commission_id, fixed)
        self.assertAlmostEqual(agent.amount, 1.0)

        line_lio = self._create_sale_line(customer, prod_lio, user_id=sales_user.id)
        line_lio._compute_agent_ids()
        agent_lio = line_lio.agent_ids.filtered(
            lambda a: a.agent_id == self.orientadora
        )
        self.assertTrue(agent_lio)
        self.assertEqual(agent_lio.commission_id, prog)

        line_hon = self._create_sale_line(customer, prod_hon, user_id=sales_user.id)
        line_hon._compute_agent_ids()
        agent_hon = line_hon.agent_ids.filtered(
            lambda a: a.agent_id == self.orientadora
        )
        self.assertFalse(agent_hon)

        line_other = self._create_sale_line(customer, prod_other, user_id=sales_user.id)
        line_other._compute_agent_ids()
        agent_other = line_other.agent_ids.filtered(
            lambda a: a.agent_id == self.orientadora
        )
        self.assertFalse(agent_other)

    def test_12_agent_rule_does_not_affect_other_agents(self):
        self.orientadora.commission_id = self.Commission.create(
            {"name": "Teste Padrao", "commission_type": "fixed", "fix_qty": 0.5}
        ).id
        fixed = self.Commission.create(
            {"name": "Teste Fixa 1%", "commission_type": "fixed", "fix_qty": 1.0}
        )
        coord_comm = self.Commission.create(
            {"name": "Teste Coordenador", "commission_type": "fixed", "fix_qty": 0.5}
        )
        cat_extra = self.env["product.category"].create({"name": "TESTE EXTRA"})
        prod_extra = self._create_product("Produto Extra", cat_extra)
        customer = self.ResPartner.create({"name": "Cliente Teste"})
        self.coordenadora.commission_id = coord_comm.id
        customer.agent_ids = [(6, 0, [self.orientadora.id, self.coordenadora.id])]

        self.env["commission.agent.rule"].create(
            {
                "agent_id": self.orientadora.id,
                "commission_id": fixed.id,
                "categ_ids": [(6, 0, [cat_extra.id])],
                "sequence": 10,
            }
        )
        line = self._create_sale_line(customer, prod_extra)
        line._compute_agent_ids()

        orient = line.agent_ids.filtered(
            lambda a: a.agent_id == self.orientadora
        )
        coord = line.agent_ids.filtered(
            lambda a: a.agent_id == self.coordenadora
        )
        self.assertEqual(orient.commission_id, fixed)
        self.assertNotEqual(coord.commission_id, fixed)
