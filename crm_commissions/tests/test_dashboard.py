# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date, datetime

from odoo.tests.common import TransactionCase

from odoo.addons.crm_commissions.controllers.dashboard import (
    _is_invoiced_status,
    _is_uninvoiced_status,
    _parse_dashboard_period,
    get_dashboard_values,
)


class TestCommissionDashboard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_sdr = cls.env.ref("crm_commissions.group_crm_commission_sdr")
        cls.commission = cls.env["commission"].create(
            {
                "name": "Comissão fixa do dashboard",
                "commission_type": "fixed",
                "amount_base_type": "gross_amount",
                "fix_qty": 10.0,
            }
        )
        cls.own_partner = cls.env["res.partner"].create(
            {
                "name": "Agente do Dashboard",
                "type_partner": "sdr",
                "agent": True,
                "agent_type": "sdr",
                "commission_id": cls.commission.id,
            }
        )
        cls.other_partner = cls.env["res.partner"].create(
            {
                "name": "Outro Agente do Dashboard",
                "type_partner": "sdr",
                "agent": True,
                "agent_type": "sdr",
                "commission_id": cls.commission.id,
            }
        )
        cls.own_user = cls.env["res.users"].create(
            {
                "name": "Usuário do Dashboard",
                "login": "dashboard_sdr_test",
                "partner_id": cls.own_partner.id,
                "groups_id": [(6, 0, [cls.group_sdr.id])],
            }
        )
        cls.other_user = cls.env["res.users"].create(
            {
                "name": "Outro Usuário do Dashboard",
                "login": "dashboard_other_sdr_test",
                "partner_id": cls.other_partner.id,
                "groups_id": [(6, 0, [cls.group_sdr.id])],
            }
        )
        cls.dashboard_env = cls.env(user=cls.own_user.id)
        cls.category = cls.env["product.category"].create(
            {"name": "Categoria do Dashboard"}
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Produto do Dashboard",
                "categ_id": cls.category.id,
                "type": "consu",
                "sale_ok": True,
                "list_price": 100.0,
                "invoice_policy": "order",
            }
        )
        cls.customer = cls.env["res.partner"].create({"name": "Cliente do Dashboard"})

    @classmethod
    def _agent_line_vals(cls, agent, split_percent):
        return (
            0,
            0,
            {
                "agent_id": agent.id,
                "commission_id": cls.commission.id,
                "commission_split_percent": split_percent,
            },
        )

    @classmethod
    def _create_order(
        cls,
        date_order,
        agent_values,
        price_unit=100.0,
        quantity=10.0,
        salesperson=None,
    ):
        order = cls.env["sale.order"].create(
            {
                "partner_id": cls.customer.id,
                "date_order": date_order,
                "user_id": salesperson.id if salesperson else cls.env.user.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": cls.product.id,
                            "product_uom_qty": quantity,
                            "price_unit": price_unit,
                            "agent_ids": list(agent_values),
                        },
                    )
                ],
            }
        )
        # Odoo 18 only changes the state in action_confirm(); _action_confirm()
        # is the post-state hook. Set it directly to retain the historical date
        # and avoid crm_iomr_sale's UI-level confirmation requirements.
        order.write({"state": "sale"})
        return order

    @classmethod
    def _create_settlement(
        cls,
        date_from,
        date_to,
        amount,
        state="settled",
        settlement_type="manual",
    ):
        settlement = cls.env["commission.settlement"].create(
            {
                "agent_id": cls.own_partner.id,
                "date_from": date_from,
                "date_to": date_to,
                "state": state,
                "settlement_type": settlement_type,
            }
        )
        cls.env["commission.settlement.line"].create(
            {
                "settlement_id": settlement.id,
                "date": date_from,
                "commission_id": cls.commission.id,
                "settled_amount": amount,
            }
        )
        settlement.invalidate_recordset(["total"])
        return settlement

    def test_01_period_defaults_to_current_month(self):
        today = date(2026, 9, 25)

        date_from, date_to, error = _parse_dashboard_period(self.env, {}, today)

        self.assertEqual(date_from, date(2026, 9, 1))
        self.assertEqual(date_to, date(2026, 9, 30))
        self.assertFalse(error)

    def test_02_period_uses_inclusive_supplied_boundaries(self):
        date_from, date_to, error = _parse_dashboard_period(
            self.env,
            {"date_from": "2026-08-15", "date_to": "2026-09-15"},
            date(2026, 9, 25),
        )

        self.assertEqual(date_from, date(2026, 8, 15))
        self.assertEqual(date_to, date(2026, 9, 15))
        self.assertFalse(error)

    def test_03_period_with_one_boundary_uses_its_month(self):
        date_from, date_to, _error = _parse_dashboard_period(
            self.env, {"date_from": "2026-02-10"}, date(2026, 9, 25)
        )
        self.assertEqual(date_from, date(2026, 2, 10))
        self.assertEqual(date_to, date(2026, 2, 28))

        date_from, date_to, _error = _parse_dashboard_period(
            self.env, {"date_to": "2026-02-10"}, date(2026, 9, 25)
        )
        self.assertEqual(date_from, date(2026, 2, 1))
        self.assertEqual(date_to, date(2026, 2, 10))

    def test_04_invalid_or_reversed_period_falls_back_to_current_month(self):
        today = date(2026, 9, 25)

        date_from, date_to, error = _parse_dashboard_period(
            self.env, {"date_from": "invalid", "date_to": "also-invalid"}, today
        )
        self.assertEqual((date_from, date_to), (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertTrue(error)

        date_from, date_to, error = _parse_dashboard_period(
            self.env, {"date_from": "2026-08-15", "date_to": "invalid"}, today
        )
        self.assertEqual((date_from, date_to), (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertTrue(error)

        date_from, date_to, error = _parse_dashboard_period(
            self.env, {"date_from": "invalid", "date_to": "2026-09-15"}, today
        )
        self.assertEqual((date_from, date_to), (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertTrue(error)

        date_from, date_to, error = _parse_dashboard_period(
            self.env, {"date_from": "2026-10-01", "date_to": "2026-09-30"}, today
        )
        self.assertEqual((date_from, date_to), (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertTrue(error)

    def test_05_invoice_status_groups_cover_all_confirmed_states(self):
        self.assertTrue(_is_invoiced_status("invoiced"))
        self.assertTrue(_is_invoiced_status("upselling"))
        self.assertTrue(_is_uninvoiced_status("to invoice"))
        self.assertTrue(_is_uninvoiced_status("no"))

        for status in ("invoiced", "upselling", "to invoice", "no"):
            self.assertNotEqual(
                _is_invoiced_status(status), _is_uninvoiced_status(status)
            )

    def test_06_orders_are_scoped_by_agent_and_use_only_own_commission(self):
        own_order = self._create_order(
            datetime(2026, 8, 31, 23, 30),
            (
                self._agent_line_vals(self.own_partner, 25.0),
                self._agent_line_vals(self.other_partner, 75.0),
            ),
            salesperson=self.other_user,
        )
        other_order = self._create_order(
            datetime(2026, 8, 15, 12, 0),
            (self._agent_line_vals(self.other_partner, 100.0),),
            salesperson=self.other_user,
        )
        outside_period = self._create_order(
            datetime(2026, 9, 1, 0, 0),
            (self._agent_line_vals(self.own_partner, 100.0),),
        )
        self.env.flush_all()

        values = get_dashboard_values(
            self.dashboard_env, date(2026, 8, 1), date(2026, 8, 31)
        )
        serialized_orders = {order["name"]: order for order in values["order_data"]}

        self.assertEqual(values["order_count"], 1)
        self.assertIn(own_order.name, serialized_orders)
        self.assertNotIn(other_order.name, serialized_orders)
        self.assertNotIn(outside_period.name, serialized_orders)
        self.assertAlmostEqual(own_order.commission_total, 100.0, places=2)
        self.assertAlmostEqual(values["current_commission_total"], 25.0, places=2)
        self.assertEqual(
            serialized_orders[own_order.name]["commission_total_fmt"], "R$ 25.00"
        )

    def test_07_period_uses_the_users_timezone(self):
        local_last_day_order = self._create_order(
            datetime(2026, 9, 1, 2, 30),
            (self._agent_line_vals(self.own_partner, 100.0),),
        )
        local_first_day_order = self._create_order(
            datetime(2026, 9, 1, 3, 30),
            (self._agent_line_vals(self.own_partner, 100.0),),
        )
        self.env.flush_all()
        timezone_env = self.env(
            user=self.own_user.id,
            context={**self.dashboard_env.context, "tz": "America/Sao_Paulo"},
        )

        values = get_dashboard_values(timezone_env, date(2026, 8, 1), date(2026, 8, 31))
        serialized_orders = {order["name"]: order for order in values["order_data"]}

        self.assertIn(local_last_day_order.name, serialized_orders)
        self.assertNotIn(local_first_day_order.name, serialized_orders)

    def test_08_changing_split_recomputes_the_agents_commission(self):
        order = self._create_order(
            datetime(2026, 8, 15, 12, 0),
            (
                self._agent_line_vals(self.own_partner, 25.0),
                self._agent_line_vals(self.other_partner, 75.0),
            ),
        )
        own_agent_line = order.order_line.agent_ids.filtered(
            lambda agent_line: agent_line.agent_id == self.own_partner
        )

        own_agent_line.commission_split_percent = 50.0
        self.env.flush_all()

        self.assertAlmostEqual(own_agent_line.amount, 50.0, places=2)
        values = get_dashboard_values(
            self.dashboard_env, date(2026, 8, 1), date(2026, 8, 31)
        )
        self.assertAlmostEqual(values["current_commission_total"], 50.0, places=2)

    def test_09_pipeline_uses_period_and_excludes_zero_probability(self):
        open_lead = self.env["crm.lead"].create(
            {
                "name": "Oportunidade aberta no período",
                "type": "opportunity",
                "partner_id": self.customer.id,
                "user_id": self.own_user.id,
                "probability": 25.0,
                "expected_revenue": 1000.0,
                "commission_percent": 20.0,
                "date_open": datetime(2026, 8, 31, 23, 30),
            }
        )
        self.env["crm.lead"].create(
            {
                "name": "Oportunidade perdida",
                "type": "opportunity",
                "partner_id": self.customer.id,
                "user_id": self.own_user.id,
                "probability": 0.0,
                "expected_revenue": 5000.0,
                "date_open": datetime(2026, 8, 15, 12, 0),
            }
        )
        self.env["crm.lead"].create(
            {
                "name": "Oportunidade de outro agente",
                "type": "opportunity",
                "partner_id": self.customer.id,
                "user_id": self.other_user.id,
                "probability": 50.0,
                "expected_revenue": 2000.0,
                "date_open": datetime(2026, 8, 15, 12, 0),
            }
        )
        self.env.flush_all()

        values = get_dashboard_values(
            self.dashboard_env, date(2026, 8, 1), date(2026, 8, 31)
        )

        self.assertEqual(
            [lead["name"] for lead in values["lead_data"]], [open_lead.name]
        )
        self.assertAlmostEqual(values["pipeline_total"], 250.0, places=2)
        self.assertAlmostEqual(values["estimated_pipeline_commission"], 50.0, places=2)

    def test_10_sdr_scope_ignores_linked_other_agents(self):
        self.own_partner.write({"type_partner": "orientadora"})
        self.own_partner.sdr_agent_ids = [(4, self.other_partner.id)]
        linked_lead = self.env["crm.lead"].create(
            {
                "name": "Oportunidade de SDR vinculado",
                "type": "opportunity",
                "partner_id": self.customer.id,
                "user_id": self.other_user.id,
                "probability": 50.0,
                "expected_revenue": 2000.0,
                "date_open": datetime(2026, 8, 15, 12, 0),
            }
        )
        self.env.flush_all()

        values = get_dashboard_values(
            self.dashboard_env, date(2026, 8, 1), date(2026, 8, 31)
        )

        self.assertNotIn(
            linked_lead.name, [lead["name"] for lead in values["lead_data"]]
        )

        orientadora_group = self.env.ref(
            "crm_commissions.group_crm_commission_orientadora"
        )
        self.own_user.write({"groups_id": [(4, orientadora_group.id)]})
        self.env.flush_all()
        values = get_dashboard_values(
            self.env(user=self.own_user.id), date(2026, 8, 1), date(2026, 8, 31)
        )
        self.assertIn(linked_lead.name, [lead["name"] for lead in values["lead_data"]])

        sales_group = self.env.ref("sales_team.group_sale_salesman")
        self.own_user.write(
            {
                "groups_id": [
                    (3, self.group_sdr.id),
                    (3, orientadora_group.id),
                    (4, sales_group.id),
                ]
            }
        )
        self.env.flush_all()
        values = get_dashboard_values(
            self.env(user=self.own_user.id), date(2026, 8, 1), date(2026, 8, 31)
        )
        self.assertIn(linked_lead.name, [lead["name"] for lead in values["lead_data"]])

    def test_11_target_totals_include_every_month_touched_by_period(self):
        for target_date, amount in (
            (date(2026, 8, 1), 1000.0),
            (date(2026, 9, 1), 2000.0),
            (date(2026, 10, 1), 4000.0),
        ):
            self.env["crm.commission.target"].create(
                {
                    "agent_id": self.own_partner.id,
                    "target_date": target_date,
                    "target_amount": amount,
                }
            )
        self.env.flush_all()

        values = get_dashboard_values(
            self.dashboard_env, date(2026, 8, 15), date(2026, 9, 15)
        )

        self.assertEqual(values["target_amount"], 3000.0)
        self.assertEqual(values["target_amount_fmt"], "R$ 3,000.00")

    def test_12_settlement_totals_are_complete_and_separate_performance(self):
        for _index in range(12):
            self._create_settlement(date(2026, 8, 1), date(2026, 8, 31), 10.0)
        self._create_settlement(
            date(2026, 8, 1), date(2026, 8, 31), 50.0, state="cancel"
        )
        self._create_settlement(
            date(2026, 8, 1),
            date(2026, 8, 31),
            500.0,
            settlement_type="crm_performance",
        )
        self._create_settlement(
            date(2026, 8, 1), date(2026, 8, 31), 25.0, state="except_invoice"
        )
        self._create_settlement(date(2026, 9, 1), date(2026, 9, 30), 1000.0)
        self.env.flush_all()

        values = get_dashboard_values(
            self.dashboard_env, date(2026, 8, 1), date(2026, 8, 31)
        )

        self.assertEqual(values["settlement_count"], 14)
        self.assertEqual(len(values["settlement_data"]), 10)
        self.assertAlmostEqual(values["pending_total"], 120.0, places=2)
        self.assertAlmostEqual(values["performance_settlements_total"], 500.0, places=2)
        self.assertAlmostEqual(values["invoice_exception_total"], 25.0, places=2)

    def test_13_quarterly_bonuses_are_not_truncated_or_filtered_by_lost(self):
        for year in range(2020, 2026):
            self.env["crm.commission.quarterly.bonus"].create(
                {
                    "agent_id": self.own_partner.id,
                    "quarter": "Q3",
                    "year": year,
                    "state": "lost" if year == 2025 else "pending",
                }
            )
        self.env.flush_all()

        values = get_dashboard_values(
            self.dashboard_env, date(2020, 7, 1), date(2025, 9, 30)
        )

        self.assertEqual(len(values["quarterly_bonus_data"]), 6)
        self.assertIn(
            "lost", {bonus["state"] for bonus in values["quarterly_bonus_data"]}
        )

    def test_14_progressive_pipeline_uses_policy_rate_and_crm_adjustment(self):
        progressive = self.env["commission"].create(
            {
                "name": "Comissão progressiva do dashboard",
                "commission_type": "progressive",
                "amount_base_type": "gross_amount",
                "is_crm_bonus": 5.0,
                "is_crm_penalty": 3.0,
                "progressive_line_ids": [
                    (
                        0,
                        0,
                        {
                            "sequence": 10,
                            "percent_from": 0.0,
                            "percent_to": 50.0,
                            "commission_percent": 2.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "sequence": 20,
                            "percent_from": 50.0,
                            "percent_to": 100.0,
                            "commission_percent": 4.0,
                        },
                    ),
                ],
            }
        )
        self.own_partner.write({"commission_id": progressive.id})
        lead = self.env["crm.lead"].create(
            {
                "name": "Oportunidade com política progressiva",
                "type": "opportunity",
                "partner_id": self.customer.id,
                "user_id": self.own_user.id,
                "probability": 50.0,
                "expected_revenue": 1000.0,
                "is_crm_score": 100.0,
                "date_open": datetime(2026, 8, 15, 12, 0),
            }
        )
        self.env.flush_all()

        values = get_dashboard_values(
            self.dashboard_env, date(2026, 8, 1), date(2026, 8, 31)
        )

        # No target means the progressive policy uses its 100% band, then the
        # IS-CRM bonus: 4% + 5%, applied to the weighted 50% revenue.
        self.assertAlmostEqual(values["estimated_pipeline_commission"], 45.0, places=2)

        lead.write({"is_crm_score": 0.0})
        self.env.flush_all()
        values = get_dashboard_values(
            self.dashboard_env, date(2026, 8, 1), date(2026, 8, 31)
        )
        self.assertAlmostEqual(values["estimated_pipeline_commission"], 5.0, places=2)

        lead.write({"commission_percent": 12.0})
        self.env.flush_all()
        values = get_dashboard_values(
            self.dashboard_env, date(2026, 8, 1), date(2026, 8, 31)
        )
        self.assertAlmostEqual(values["estimated_pipeline_commission"], 60.0, places=2)

    def test_15_quarterly_totals_ignore_other_company_targets(self):
        other_company = self.env["res.company"].create({"name": "Empresa Secundária"})
        self.env["crm.commission.target"].create(
            {
                "agent_id": self.own_partner.id,
                "target_date": date(2026, 10, 1),
                "target_amount": 1000.0,
            }
        )
        self.env["crm.commission.target"].create(
            {
                "agent_id": self.own_partner.id,
                "target_date": date(2026, 11, 1),
                "target_amount": 2000.0,
                "company_id": other_company.id,
                "currency_id": other_company.currency_id.id,
            }
        )
        self.env.flush_all()

        bonus = self.env["crm.commission.quarterly.bonus"].search(
            [
                ("agent_id", "=", self.own_partner.id),
                ("year", "=", 2026),
                ("quarter", "=", "Q4"),
            ],
            limit=1,
        )
        self.assertTrue(bonus)
        self.assertEqual(len(bonus.monthly_targets), 2)

        values = get_dashboard_values(
            self.dashboard_env, date(2026, 10, 1), date(2026, 12, 31)
        )

        self.assertEqual(values["quarterly_total_target"], 1000.0)
        self.assertEqual(values["quarterly_total_achieved"], 0.0)
        self.assertEqual(values["quarterly_pct"], 0.0)
        self.assertEqual(len(values["quarterly_bonus_data"]), 1)

    def test_16_coordinator_pipeline_uses_active_policy_rate(self):
        self.env["commission.policy"].create(
            {
                "name": "Política do coordinator",
                "date_start": date(2099, 1, 1),
                "coordinator_rate": 7.0,
                "active": True,
            }
        )
        coordinator = self.env["commission"].create(
            {
                "name": "Comissão coordinator do dashboard",
                "commission_type": "coordinator",
                "amount_base_type": "gross_amount",
            }
        )
        self.own_partner.write({"commission_id": coordinator.id})
        self.env["crm.lead"].create(
            {
                "name": "Oportunidade de coordinator",
                "type": "opportunity",
                "partner_id": self.customer.id,
                "user_id": self.own_user.id,
                "probability": 50.0,
                "expected_revenue": 1000.0,
                "date_open": datetime(2026, 8, 15, 12, 0),
            }
        )
        self.env.flush_all()

        values = get_dashboard_values(
            self.dashboard_env, date(2026, 8, 1), date(2026, 8, 31)
        )

        self.assertAlmostEqual(values["estimated_pipeline_commission"], 35.0, places=2)
