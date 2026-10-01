# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import importlib.util
from pathlib import Path

from odoo.tests.common import TransactionCase


def _load_migration(version, filename):
    """Import a migration script by path, the way Odoo itself does."""
    path = Path(__file__).resolve().parents[1] / "migrations" / version / filename
    spec = importlib.util.spec_from_file_location(f"_mig_{version}_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        # Migration functions, exercised directly: the wrong state they fix
        # is built by hand, since the computes no longer produce it.
        cls.post_migration = _load_migration("18.0.2.0.0", "post-migrate.py")

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

        vals2 = [(0, 0, {"agent_id": self.sdr.id, "commission_id": commission.id})]
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

    def _create_product(self, name, categ, taxes=None):
        return self.env["product.product"].create(
            {
                "name": name,
                "categ_id": categ.id,
                "type": "consu",
                "sale_ok": True,
                "list_price": 100.0,
                "taxes_id": [(6, 0, taxes.ids)] if taxes else [(5, 0, 0)],
            }
        )

    def _create_sale_tax(self, name, amount):
        """A plain sale tax, enough to make the line carry a real tax amount.

        ``account.tax`` derives both ``country_id`` and ``tax_group_id`` from
        the company, and both are NOT NULL in the database. A company without
        a fiscal country -- the default on a bare test database -- has neither,
        so the fiscal country is set first and the group created on demand.
        """
        if not self.env.company.account_fiscal_country_id:
            self.env.company.account_fiscal_country_id = self.env.ref("base.br").id
        group = self.env["account.tax.group"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        if not group:
            group = self.env["account.tax.group"].create(
                {
                    "name": "Vendas Teste",
                    "company_id": self.env.company.id,
                    "country_id": self.env.company.account_fiscal_country_id.id,
                }
            )
        return self.env["account.tax"].create(
            {
                "name": name,
                "amount_type": "percent",
                "amount": amount,
                "type_tax_use": "sale",
                "tax_group_id": group.id,
            }
        )

    def _ensure_account(self, account_type, name, code):
        """Return a company account of the given type, creating it if needed.

        ``account.account`` carries ``company_ids`` (a many2many) in Odoo 18,
        and a test database without a chart of accounts has none of them.
        """
        account = self.env["account.account"].search(
            [
                ("account_type", "=", account_type),
                ("company_ids", "in", self.env.company.id),
            ],
            limit=1,
        )
        if not account:
            account = self.env["account.account"].create(
                {
                    "name": name,
                    "code": code,
                    "account_type": account_type,
                    "company_ids": [(6, 0, self.env.company.ids)],
                }
            )
        return account

    def _ensure_sale_journal(self):
        """A sale journal, absent on a database with no chart of accounts.

        Invoicing raises "No journal could be found" without one, which is
        what the invoice-side test needs to get past.
        """
        journal = self.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", self.env.company.id)],
            limit=1,
        )
        if not journal:
            journal = self.env["account.journal"].create(
                {
                    "name": "Vendas Teste",
                    "code": "VEN",
                    "type": "sale",
                    "company_id": self.env.company.id,
                }
            )
        return journal

    def _create_card_fee_order(self, partner, doctor, fee_percent):
        payment_method = self.env["payment.method"].create(
            {"name": "Cartão Teste", "code": "TEST_CARD"}
        )
        payment_method.credit_card_admin = True
        self.env["credit.card.fee.range"].create(
            {
                "payment_method_id": payment_method.id,
                "installments_from": 1,
                "installments_to": 12,
                "fee_percent": fee_percent,
            }
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "doctor_id": doctor.id,
                "payment_method_ids": [payment_method.id],
            }
        )
        self.env["sale.invoice.plan"].create(
            {
                "sale_id": order.id,
                "invoice_type": "installment",
                "installment": 1,
                "plan_date": order.date_order,
                "percent": 100.0,
            }
        )
        return order

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
        agent = line_extra.agent_ids.filtered(lambda a: a.agent_id == self.orientadora)
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
        cat_hon = self.env["product.category"].create({"name": "HONORARIO TESTE"})
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
        agent = line_extra.agent_ids.filtered(lambda a: a.agent_id == self.orientadora)
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

        orient = line.agent_ids.filtered(lambda a: a.agent_id == self.orientadora)
        coord = line.agent_ids.filtered(lambda a: a.agent_id == self.coordenadora)
        self.assertEqual(orient.commission_id, fixed)
        self.assertNotEqual(coord.commission_id, fixed)

    def test_14_coordinator_mirrors_orientadora_commission(self):
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
        self.orientadora.salesman_as_agent = True
        self.orientadora.coordenadora_id = self.coordenadora.id
        sales_user = self.env["res.users"].create(
            {
                "name": "Sales Orientadora 14",
                "login": "sales_orientadora_login_14",
                "partner_id": self.orientadora.id,
                "company_id": self.company.id,
                "company_ids": [(6, 0, [self.company.id])],
            }
        )
        customer = self.ResPartner.create({"name": "Cliente Teste 14"})
        cat_extra = self.env["product.category"].create({"name": "TESTE EXTRA 14"})
        cat_lio = self.env["product.category"].create({"name": "TESTE LIO 14"})
        cat_hon = self.env["product.category"].create({"name": "HONORARIO TESTE 14"})
        cat_other = self.env["product.category"].create({"name": "TESTE OUTRA 14"})
        prod_extra = self._create_product("Produto Extra 14", cat_extra)
        prod_lio = self._create_product("Lente LIO 14", cat_lio)
        prod_hon = self._create_product("Produto Hon 14", cat_hon)
        prod_other = self._create_product("Produto Outro 14", cat_other)
        self.env["commission.agent.rule"].create(
            {
                "agent_id": self.orientadora.id,
                "commission_id": fixed.id,
                "categ_ids": [(6, 0, [cat_extra.id])],
                "sequence": 10,
            }
        )
        prog.categ_ids = [(6, 0, [cat_lio.id])]
        coordinator_comm = self.env.ref("crm_commissions.commission_coordinator_policy")

        policy = self.env["commission.policy"].search(
            [("active", "=", True)], order="date_start desc", limit=1
        )
        self.assertTrue(policy)
        self.assertEqual(policy.coordinator_rate, 0.5)

        line_extra = self._create_sale_line(customer, prod_extra, user_id=sales_user.id)
        line_extra._compute_agent_ids()
        self.assertEqual(len(line_extra.agent_ids), 2)
        orient = line_extra.agent_ids.filtered(lambda a: a.agent_id == self.orientadora)
        coord = line_extra.agent_ids.filtered(lambda a: a.agent_id == self.coordenadora)
        self.assertEqual(orient.commission_id, fixed)
        self.assertEqual(orient.amount, 1.0)
        self.assertEqual(coord.commission_id, coordinator_comm)
        self.assertAlmostEqual(coord.amount, 0.5)

        line_lio = self._create_sale_line(customer, prod_lio, user_id=sales_user.id)
        line_lio._compute_agent_ids()
        orient_lio = line_lio.agent_ids.filtered(
            lambda a: a.agent_id == self.orientadora
        )
        coord_lio = line_lio.agent_ids.filtered(
            lambda a: a.agent_id == self.coordenadora
        )
        self.assertTrue(orient_lio)
        self.assertEqual(orient_lio.commission_id, prog)
        self.assertEqual(coord_lio.commission_id, coordinator_comm)
        self.assertAlmostEqual(coord_lio.amount, 0.5)

        line_hon = self._create_sale_line(customer, prod_hon, user_id=sales_user.id)
        line_hon._compute_agent_ids()
        self.assertFalse(
            line_hon.agent_ids.filtered(lambda a: a.agent_id == self.coordenadora)
        )

        line_other = self._create_sale_line(customer, prod_other, user_id=sales_user.id)
        line_other._compute_agent_ids()
        self.assertFalse(
            line_other.agent_ids.filtered(lambda a: a.agent_id == self.coordenadora)
        )

    def test_15_coordinator_not_duplicated_when_agent_listed(self):
        self.orientadora.coordenadora_id = self.coordenadora.id
        orient_comm = self.Commission.create(
            {"name": "Teste Padrao", "commission_type": "fixed", "fix_qty": 0.5}
        )
        coord_comm = self.Commission.create(
            {"name": "Teste Coordenador", "commission_type": "fixed", "fix_qty": 0.5}
        )
        self.orientadora.commission_id = orient_comm.id
        self.coordenadora.commission_id = coord_comm.id
        customer = self.ResPartner.create({"name": "Cliente Teste 15"})
        customer.agent_ids = [(6, 0, [self.orientadora.id, self.coordenadora.id])]

        line = self._create_sale_line(
            customer,
            self._create_product(
                "Produto 15", self.env["product.category"].create({"name": "TESTE 15"})
            ),
        )
        line._compute_agent_ids()

        coord_lines = line.agent_ids.filtered(lambda a: a.agent_id == self.coordenadora)
        self.assertEqual(len(coord_lines), 1)
        self.assertEqual(coord_lines.commission_id, coord_comm)

    def _create_doctor_sale_line(self, customer, product, doctor):
        order = self.env["sale.order"].create(
            {"partner_id": customer.id, "doctor_id": doctor.id}
        )
        return self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": 1,
                "price_unit": 100.0,
            }
        )

    def test_16_doctor_consulta_deduct_fixed_tax(self):
        comm = self.Commission.create(
            {
                "name": "Repasse Médico - Consulta",
                "commission_type": "fixed",
                "fix_qty": 60.0,
                "amount_base_type": "net_amount_deduction",
                "tax_deduction_pct": 16.33,
                "deduct_card_fee": False,
            }
        )
        self.doctor.agent = True
        self.doctor.commission_id = comm.id
        cat = self.env["product.category"].create({"name": "CONSULTA TESTE"})
        prod = self._create_product("Consulta", cat)
        customer = self.ResPartner.create({"name": "Cliente Consulta"})
        line = self._create_doctor_sale_line(customer, prod, self.doctor)
        line._compute_agent_ids()

        agent = line.agent_ids.filtered(lambda a: a.agent_id == self.doctor)
        self.assertTrue(agent)
        self.assertEqual(agent.commission_id, comm)
        # base = 100 - 100 * 0.1633 = 83.67 ; 83.67 * 60% = 50.202
        self.assertAlmostEqual(agent.amount, 50.202)

    def test_17_doctor_exame_deduct_tax_and_card_fee(self):
        comm = self.Commission.create(
            {
                "name": "Repasse Médico - Exame",
                "commission_type": "fixed",
                "fix_qty": 50.0,
                "amount_base_type": "net_amount_deduction",
                "tax_deduction_pct": 11.73,
                "deduct_card_fee": True,
            }
        )
        self.doctor.agent = True
        self.doctor.commission_id = comm.id
        pm = self.env["payment.method"].create(
            {"name": "Cartão Teste", "code": "TEST_CARD"}
        )
        pm.credit_card_admin = True
        self.env["credit.card.fee.range"].create(
            {
                "payment_method_id": pm.id,
                "installments_from": 1,
                "installments_to": 12,
                "fee_percent": 2.5,
            }
        )
        cat = self.env["product.category"].create({"name": "EXAME TESTE"})
        prod = self._create_product("Exame", cat)
        customer = self.ResPartner.create({"name": "Cliente Exame"})
        order = self.env["sale.order"].create(
            {
                "partner_id": customer.id,
                "doctor_id": self.doctor.id,
                "payment_method_ids": [pm.id],
            }
        )
        self.env["sale.invoice.plan"].create(
            {
                "sale_id": order.id,
                "invoice_type": "installment",
                "installment": 1,
                "plan_date": order.date_order,
                "percent": 100.0,
            }
        )
        self.assertAlmostEqual(order.credit_card_fee_percent, 2.5)

        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": prod.id,
                "product_uom_qty": 1,
                "price_unit": 100.0,
            }
        )
        line._compute_agent_ids()

        agent = line.agent_ids.filtered(lambda a: a.agent_id == self.doctor)
        self.assertTrue(agent)
        self.assertEqual(agent.commission_id, comm)
        # base = 100 - 100*0.1173 - 100*0.025 = 85.77 ; 85.77 * 50% = 42.885
        self.assertAlmostEqual(agent.amount, 42.885)

    def test_18_honorario_only_commissions_order_doctor(self):
        """HONORARIO/PROCEDIMENTO lines must only commission the order's doctor.

        Every other agent type used to leak: customer agents of any
        type_partner, the salesperson-as-agent and non-doctor referrals.
        """
        comm = self.Commission.create(
            {"name": "Fixa 1% Repasse", "commission_type": "fixed", "fix_qty": 1.0}
        )
        self.doctor.agent = True
        self.doctor.agent_type = "doctor"
        self.doctor.commission_id = comm.id
        # Customer agents covering every non-medical type_partner.
        others_agent = self.ResPartner.create(
            {
                "name": "Agente Outros",
                "type_partner": "others",
                "agent": True,
                "agent_type": "agent",
                "commission_id": comm.id,
            }
        )
        self.coordenadora.commission_id = comm.id
        self.sdr.commission_id = comm.id
        self.orientadora.commission_id = comm.id
        # A salesperson that is not an orientadora/sdr: used to leak.
        vendedor = self.ResPartner.create(
            {
                "name": "Vendedor",
                "type_partner": "employee",
                "agent": True,
                "agent_type": "agent",
                "commission_id": comm.id,
                "salesman_as_agent": True,
            }
        )
        sales_user = self.env["res.users"].create(
            {
                "name": "User Vendedor",
                "login": "vendedor_honorario_test",
                "partner_id": vendedor.id,
                "company_id": self.company.id,
                "company_ids": [(6, 0, [self.company.id])],
            }
        )
        # A non-doctor referral: referred_partner only excludes convenio.
        indicador = self.ResPartner.create(
            {
                "name": "Indicador Nao Medico",
                "type_partner": "employee",
                "agent": True,
                "agent_type": "agent",
                "commission_id": comm.id,
            }
        )
        cat_hon = self.env["product.category"].create({"name": "HONORARIO T18"})
        prod_hon = self._create_product("Honorario T18", cat_hon)
        customer = self.ResPartner.create(
            {
                "name": "Cliente Honorario T18",
                "agent_ids": [
                    (
                        6,
                        0,
                        [
                            others_agent.id,
                            self.coordenadora.id,
                            self.orientadora.id,
                            self.sdr.id,
                        ],
                    )
                ],
            }
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": customer.id,
                "user_id": sales_user.id,
                "doctor_id": self.doctor.id,
                "referred_partner": [(6, 0, [indicador.id])],
            }
        )
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": prod_hon.id,
                "product_uom_qty": 1,
                "price_unit": 1000.0,
            }
        )
        line._compute_agent_ids()

        agents = line.agent_ids
        self.assertEqual(
            agents.mapped("agent_id"), self.doctor, "só o médico do pedido"
        )
        self.assertEqual(agents.commission_id, comm)
        self.assertAlmostEqual(agents.amount, 10.0)

    def test_19_honorario_keeps_medical_referral_split(self):
        """Two medical parties on the order still split the honorário 50/50."""
        comm = self.Commission.create(
            {"name": "Fixa 1% T19", "commission_type": "fixed", "fix_qty": 1.0}
        )
        self.doctor.agent = True
        self.doctor.agent_type = "doctor"
        self.doctor.commission_id = comm.id
        ref_doctor = self.ResPartner.create(
            {
                "name": "Dr Indicador",
                "type_partner": "doctorext",
                "agent": True,
                "agent_type": "doctor",
                "commission_id": comm.id,
            }
        )
        cat_hon = self.env["product.category"].create({"name": "PROCEDIMENTO T19"})
        prod_hon = self._create_product("Procedimento T19", cat_hon)
        customer = self.ResPartner.create({"name": "Cliente T19"})
        order = self.env["sale.order"].create(
            {
                "partner_id": customer.id,
                "doctor_id": self.doctor.id,
                "referred_partner": [(6, 0, [ref_doctor.id])],
            }
        )
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": prod_hon.id,
                "product_uom_qty": 1,
                "price_unit": 1000.0,
            }
        )
        line._compute_agent_ids()

        self.assertEqual(
            line.agent_ids.mapped("agent_id"),
            self.doctor + ref_doctor,
        )
        for agent in line.agent_ids:
            self.assertEqual(agent.commission_split_percent, 50.0)
            self.assertAlmostEqual(agent.amount, 5.0)

    def test_20_honorario_applies_doctor_category_rule(self):
        """The per-category repasse rule must still reach the doctor."""
        repasse = self.Commission.create(
            {
                "name": "Repasse Cirurgia",
                "commission_type": "fixed",
                "fix_qty": 100.0,
                "amount_base_type": "net_amount_deduction",
                "tax_deduction_pct": 11.73,
            }
        )
        self.doctor.agent = True
        self.doctor.agent_type = "doctor"
        self.doctor.commission_id = comm_default = self.Commission.create(
            {"name": "Padrao T20", "commission_type": "fixed", "fix_qty": 1.0}
        )
        cat_hon = self.env["product.category"].create({"name": "HONORARIO T20"})
        prod_hon = self._create_product("Cirurgia T20", cat_hon)
        self.env["commission.agent.rule"].create(
            {
                "agent_id": self.doctor.id,
                "commission_id": repasse.id,
                "categ_ids": [(6, 0, [cat_hon.id])],
                "sequence": 10,
            }
        )
        customer = self.ResPartner.create({"name": "Cliente T20"})
        line = self._create_doctor_sale_line(customer, prod_hon, self.doctor)
        line.price_unit = 1000.0
        line._compute_agent_ids()

        agent = line.agent_ids.filtered(lambda a: a.agent_id == self.doctor)
        self.assertEqual(len(agent), 1)
        self.assertEqual(agent.commission_id, repasse)
        self.assertNotEqual(agent.commission_id, comm_default)

    def test_21_honorario_ignores_doctor_as_customer_agent(self):
        """A doctor on the customer's agent_ids but not the order's
        doctor_id must not commission the honorário."""
        comm = self.Commission.create(
            {"name": "Fixa 1% T21", "commission_type": "fixed", "fix_qty": 1.0}
        )
        other_doctor = self.ResPartner.create(
            {
                "name": "Dr Nao Indicado",
                "type_partner": "doctorint",
                "agent": True,
                "agent_type": "doctor",
                "commission_id": comm.id,
            }
        )
        self.doctor.agent = True
        self.doctor.agent_type = "doctor"
        self.doctor.commission_id = comm.id
        cat_hon = self.env["product.category"].create({"name": "HONORARIO T21"})
        prod_hon = self._create_product("Honorario T21", cat_hon)
        customer = self.ResPartner.create(
            {
                "name": "Cliente T21",
                "agent_ids": [(6, 0, [other_doctor.id])],
            }
        )
        line = self._create_doctor_sale_line(customer, prod_hon, self.doctor)
        line.price_unit = 1000.0
        line._compute_agent_ids()

        self.assertEqual(line.agent_ids.mapped("agent_id"), self.doctor)
        self.assertNotIn(other_doctor, line.agent_ids.mapped("agent_id"))

    def _line_tax_repasse(self, taxes=(), fee_percent=0.0, tax_pct=0.0):
        """Build a doctor line and return (sale line, doctor agent line)."""
        comm = self.Commission.create(
            {
                "name": "Repasse Impostos Reais",
                "commission_type": "fixed",
                "fix_qty": 60.0,
                "amount_base_type": "net_amount_deduction",
                "deduct_taxes": True,
                "deduct_card_fee": bool(fee_percent),
                "tax_deduction_pct": tax_pct,
            }
        )
        self.doctor.agent = True
        self.doctor.commission_id = comm.id
        tax = self._create_sale_tax("Imposto Teste", 10.0) if taxes else None
        categ = self.env["product.category"].create({"name": "IMPOSTOS REAIS"})
        product = self._create_product("Produto impostos", categ, taxes=tax)
        customer = self.ResPartner.create({"name": "Cliente Impostos"})
        order = (
            self._create_card_fee_order(customer, self.doctor, fee_percent)
            if fee_percent
            else self.env["sale.order"].create(
                {"partner_id": customer.id, "doctor_id": self.doctor.id}
            )
        )
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": 1,
                "price_unit": 1000.0,
            }
        )
        line._compute_agent_ids()
        agent = line.agent_ids.filtered(lambda a: a.agent_id == self.doctor)
        self.assertEqual(len(agent), 1, "esperado um único agente médico na linha")
        return line, agent

    def test_22_deduct_taxes_removes_the_real_line_tax(self):
        """A dedução deve sair do imposto real da linha, não de um percentual.

        Preço 1.000, imposto de 10% (não incluído no preço) => base
        1.100 - 100 = 1.000 ; 1.000 x 60% = 600,00
        """
        line, agent = self._line_tax_repasse(taxes=True)
        self.assertAlmostEqual(line.price_subtotal, 1000.0)
        self.assertAlmostEqual(line.price_total, 1100.0)
        self.assertAlmostEqual(agent.amount, 600.0)

    def test_23_card_fee_is_deducted_over_the_taxed_amount(self):
        """A taxa de cartão incide sobre price_total, como a maquininha cobra.

        Base = 1.000 - 1.100 x 2,5% = 972,50 ; 972,50 x 60% = 583,50.
        Sobre o subtotal (1.000) daria 585,00: 1,50 a mais por linha.
        """
        _, agent = self._line_tax_repasse(taxes=True, fee_percent=2.5)
        self.assertAlmostEqual(agent.amount, 583.50)

    def test_24_deduct_taxes_wins_over_the_fixed_percentage(self):
        """Com deduct_taxes ligado, tax_deduction_pct fica sem efeito."""
        _, agent = self._line_tax_repasse(taxes=True, tax_pct=16.33)
        # 16,33% sobre 1.000 daria 600,00 x (1 - 0,1633) = 502,02.
        self.assertAlmostEqual(agent.amount, 600.0)

    def test_25_deduct_taxes_without_taxes_keeps_the_subtotal(self):
        """Produto sem imposto não pode zerar a base da comissão."""
        line, agent = self._line_tax_repasse(fee_percent=2.5)
        self.assertAlmostEqual(line.price_total, line.price_subtotal)
        # 1.000 - 1.000 x 2,5% = 975,00 ; 975,00 x 60% = 585,00
        self.assertAlmostEqual(agent.amount, 585.0)

    def test_26_stored_commissions_use_the_real_taxes(self):
        """As comissões de repasse do módulo saem com a dedução real."""
        for xmlid, rate in (
            ("commission_doctor_consulta", 60.0),
            ("commission_doctor_exame", 50.0),
            ("commission_doctor_cirurgia", 100.0),
        ):
            comm = self.env.ref(f"crm_commissions.{xmlid}")
            self.assertEqual(comm.amount_base_type, "net_amount_deduction", xmlid)
            self.assertTrue(comm.deduct_taxes, xmlid)
            self.assertTrue(comm.deduct_card_fee, xmlid)
            self.assertEqual(comm.tax_deduction_pct, 0.0, xmlid)
            self.assertEqual(comm.fix_qty, rate, xmlid)

    def test_27_invoice_line_deducts_the_real_taxes_too(self):
        """A linha da fatura, origem do repasse, tem de deduzir o imposto real.

        É dela que o assistente de repasse tira o valor a pagar, então a
        regra ``[preço - impostos - taxa cartão]`` precisa valer igual
        na venda. A linha é montada à mão porque este banco de teste não
        tem plano de contas: a taxa de cartão, que depende do pedido de
        origem, é verificada em ``test_23``.
        """
        comm = self.Commission.create(
            {
                "name": "Repasse Faturado",
                "commission_type": "fixed",
                "fix_qty": 60.0,
                "amount_base_type": "net_amount_deduction",
                "deduct_taxes": True,
                "deduct_card_fee": True,
            }
        )
        self.doctor.agent = True
        self.doctor.commission_id = comm.id
        tax = self._create_sale_tax("Imposto Faturado", 10.0)
        categ = self.env["product.category"].create({"name": "FATURADO"})
        product = self._create_product("Produto faturado", categ, taxes=tax)
        customer = self.ResPartner.create(
            {
                "name": "Cliente Faturado",
                "agent_ids": [(6, 0, [self.doctor.id])],
            }
        )
        income = self._ensure_account("income", "Receita Teste", "4901")
        # A linha de vencimento criada junto com a fatura busca uma conta
        # de recebível; sem ela o banco recusa a linha do produto também.
        self._ensure_account("asset_receivable", "Recebível Teste", "1.1.1.01.01")
        # Sem plano de contas a linha sai sem conta e o banco recusa.
        product.property_account_income_id = income.id
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": customer.id,
                "journal_id": self._ensure_sale_journal().id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "display_type": "product",
                            "name": "Produto faturado",
                            "quantity": 1.0,
                            "price_unit": 1000.0,
                            "tax_ids": [(6, 0, tax.ids)],
                            "account_id": income.id,
                        },
                    )
                ],
            }
        )
        invoice_line = invoice.invoice_line_ids.filtered(
            lambda line, product=product: line.product_id == product
        )
        self.assertEqual(len(invoice_line), 1)
        agent = invoice_line.agent_ids.filtered(lambda a: a.agent_id == self.doctor)
        self.assertEqual(len(agent), 1, "o médico precisa ir para a linha da fatura")
        # Mesma conta da venda: 1.100 - 100 = 1.000 ; 1.000 x 60% = 600,00
        self.assertAlmostEqual(invoice_line.price_total, 1100.0)
        self.assertAlmostEqual(agent.amount, 600.0)

    def _card_fee_product(self):
        """The product ``sale_credit_card_fee`` bills its fee with."""
        product = self.env.ref(
            "sale_credit_card_fee.product_credit_card_fee", raise_if_not_found=False
        )
        self.assertTrue(
            product, "sale_credit_card_fee precisa estar instalado para este teste"
        )
        return product

    def _insert_legacy_fee_agent(self, fee_line, agent, commission):
        """Insert by SQL the agent line the previous version used to create.

        ``agent_ids`` is a stored computed one2many whose compute starts by
        wiping itself, so writing the child through the ORM makes the
        recompute delete it right away. The legacy rows this reproduces only
        ever existed because an older compute produced them, so they have to
        land in the table directly.
        """
        self.env.cr.execute(
            """
            INSERT INTO account_invoice_line_agent
                (object_id, agent_id, commission_id, create_uid, write_uid,
                 create_date, write_date, commission_split_percent)
            VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), %s)
            RETURNING id
            """,
            (
                fee_line.id,
                agent.id,
                commission.id,
                self.env.uid,
                self.env.uid,
                100.0,
            ),
        )
        return self.env.cr.fetchone()[0]

    def _create_invoice_with_line(self, customer, product, price_unit, taxes=None):
        """A draft customer invoice with a single product line."""
        income = self._ensure_account("income", "Receita Teste", "4901")
        # A linha de vencimento criada junto com a fatura busca uma conta
        # de recebível; sem ela o banco recusa a linha do produto também.
        self._ensure_account("asset_receivable", "Recebível Teste", "1.1.1.01.01")
        product.property_account_income_id = income.id
        taxes = taxes if taxes is not None else self.env["account.tax"]
        return self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": customer.id,
                "journal_id": self._ensure_sale_journal().id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "display_type": "product",
                            "name": product.name,
                            "quantity": 1.0,
                            "price_unit": price_unit,
                            "tax_ids": [(6, 0, taxes.ids)],
                            "account_id": income.id,
                        },
                    )
                ],
            }
        )

    def test_28_card_fee_line_earns_no_commission(self):
        """A taxa de cartão é custo, não venda: não pode pagar agente.

        A linha da taxa é gravada pela ``sale_credit_card_fee`` sem nenhuma
        ``sale_line_ids``, então ela caía em
        ``_prepare_agents_vals_partner`` e a orientadora e a coordenadora
        recebiam comissão justamente sobre a taxa que a Fase 1 deduz da
        base delas.
        """
        comm = self.Commission.create(
            {"name": "Progressiva Taxa", "commission_type": "progressive"}
        )
        self.Coordinator = self.ResPartner.create(
            {
                "name": "Test Coordenadora Taxa",
                "type_partner": "coordenadora",
                "agent": True,
                "agent_type": "coordenadora",
                "commission_id": comm.id,
            }
        )
        customer = self.ResPartner.create(
            {
                "name": "Cliente Taxa",
                "agent_ids": [(6, 0, [self.orientadora.id, self.Coordinator.id])],
            }
        )
        fee_product = self._card_fee_product()
        fee_product.commission_free = False
        invoice = self._create_invoice_with_line(customer, fee_product, 27.50)
        fee_line = invoice.invoice_line_ids.filtered(
            lambda line, product=fee_product: line.product_id == product
        )
        self.assertEqual(len(fee_line), 1)
        self.assertFalse(
            fee_line.agent_ids,
            "a linha da taxa de cartão não pode ter agente nenhum",
        )
        # O valor da taxa é R$ 27,50; se fosse comissionado a 0,5% da
        # coordenadora daria R$ 0,14 de ganho indevido por fatura.
        self.assertAlmostEqual(fee_line.price_subtotal, 27.50)

    def test_29_product_line_still_commissions_next_to_the_fee(self):
        """O guard da taxa não pode apagar a comissão da venda normal."""
        comm = self.Commission.create(
            {"name": "Fixa Taxa", "commission_type": "fixed", "fix_qty": 1.0}
        )
        self.orientadora.commission_id = comm.id
        self.Coordinator = self.ResPartner.create(
            {
                "name": "Test Coordenadora Venda",
                "type_partner": "coordenadora",
                "agent": True,
                "agent_type": "coordenadora",
                "commission_id": comm.id,
            }
        )
        customer = self.ResPartner.create(
            {
                "name": "Cliente Venda",
                "agent_ids": [(6, 0, [self.orientadora.id, self.Coordinator.id])],
            }
        )
        categ = self.env["product.category"].create({"name": "VENDA NORMAL"})
        product = self._create_product("Produto vendido", categ)
        fee_product = self._card_fee_product()
        income = self._ensure_account("income", "Receita Teste", "4901")
        self._ensure_account("asset_receivable", "Recebível Teste", "1.1.1.01.01")
        product.property_account_income_id = income.id
        invoice = self._create_invoice_with_line(customer, product, 1000.0)
        invoice.write(
            {
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": fee_product.id,
                            "display_type": "product",
                            "name": "Credit Card Fee",
                            "quantity": 1.0,
                            "price_unit": 27.50,
                            "tax_ids": [(5, 0, 0)],
                            "account_id": income.id,
                        },
                    )
                ]
            }
        )
        sale_line = invoice.invoice_line_ids.filtered(
            lambda line, product=product: line.product_id == product
        )
        fee_line = invoice.invoice_line_ids.filtered(
            lambda line, product=fee_product: line.product_id == product
        )
        self.assertEqual(len(sale_line), 1)
        self.assertEqual(len(fee_line), 1)
        self.assertTrue(sale_line.agent_ids, "a linha da venda continua comissionando")
        self.assertFalse(fee_line.agent_ids, "só a linha da taxa fica sem agente")
        # A fatura sem sale_line_ids usa os agentes do cliente: orientadora e
        # coordenadora, 1% cada sobre os 1.000,00 da linha de venda.
        self.assertEqual(len(sale_line.agent_ids), 2)
        self.assertAlmostEqual(sum(sale_line.agent_ids.mapped("amount")), 20.0)

    def test_30_migration_drops_the_agents_on_the_fee_line(self):
        """A migração remove os agentes que já estão na linha da taxa.

        O guard impede novos agentes, mas os que já foram gravados
        continuariam pagando a taxa como se fosse venda. O estado errado é
        montado à mão (o compute já não o produz) e as funções da migração
        são chamadas direto, como em ``test_commission_migration.py``.
        """
        comm = self.Commission.create(
            {"name": "Fixa Migracao Taxa", "commission_type": "fixed", "fix_qty": 1.0}
        )
        customer = self.ResPartner.create(
            {
                "name": "Cliente Migracao Taxa",
                "agent_ids": [(6, 0, [self.orientadora.id])],
            }
        )
        self.orientadora.commission_id = comm.id
        fee_product = self._card_fee_product()
        invoice = self._create_invoice_with_line(customer, fee_product, 27.50)
        fee_line = invoice.invoice_line_ids.filtered(
            lambda line, product=fee_product: line.product_id == product
        )
        fee_agents = self.env["account.invoice.line.agent"]
        self._insert_legacy_fee_agent(fee_line, self.orientadora, comm)
        self.assertEqual(
            fee_agents.search_count([("object_id", "=", fee_line.id)]),
            1,
            "premissa do teste",
        )

        product_ids = self.post_migration.get_card_fee_product_ids(self.env)
        self.assertIn(fee_product.id, product_ids)
        invoice_line_ids = self.post_migration.get_card_fee_invoice_line_ids(
            self.env, product_ids
        )
        self.assertIn(fee_line.id, invoice_line_ids)

        dropped, skipped = self.post_migration.drop_fee_agent_lines(
            self.env, product_ids
        )
        self.assertEqual(dropped, 1)
        self.assertEqual(skipped, 0)
        self.assertEqual(
            fee_agents.search_count([("object_id", "=", fee_line.id)]),
            0,
            "o agente sobre a taxa precisa ter sido removido",
        )
        # Idempotente: rodar de novo não encontra mais nada.
        self.assertEqual(
            self.post_migration.drop_fee_agent_lines(self.env, product_ids), (0, 0)
        )

    def test_31_migration_flags_the_fee_product_commission_free(self):
        """A migração marca o produto da taxa como livre de comissão.

        É a defesa em profundidade: mesmo que uma linha da taxa ganhasse
        um agente por outro caminho, ``_get_commission_amount`` devolveria
        zero para um produto ``commission_free``.
        """
        fee_product = self._card_fee_product()
        fee_product.commission_free = False
        self.assertEqual(
            self.post_migration.clear_fee_product_flag(self.env, [fee_product.id]), 1
        )
        self.assertTrue(fee_product.commission_free)
        # Idempotente: rodar de novo não muda nada.
        self.assertEqual(
            self.post_migration.clear_fee_product_flag(self.env, [fee_product.id]), 0
        )
