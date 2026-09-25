# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import datetime, time

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestQuarterlyBonus(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Target = cls.env["crm.commission.target"]
        cls.Bonus = cls.env["crm.commission.quarterly.bonus"]
        cls.Partner = cls.env["res.partner"]
        cls.Member = cls.env["commission.member"]
        cls.SaleOrder = cls.env["sale.order"]
        cls.commission = cls.env.ref("crm_commissions.commission_progressive_lios")
        cls.category = cls.env["product.category"].create(
            {"name": "Teste Bônus Trimestral"}
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Produto Bônus Trimestral",
                "categ_id": cls.category.id,
                "type": "consu",
                "sale_ok": True,
                "list_price": 100.0,
                "standard_price": 30.0,
            }
        )
        cls.orientadora, cls.member = cls._make_orientadora(
            "Orientadora Bônus Trimestral", "orientadora_bonus_trimestral"
        )

    @classmethod
    def _make_orientadora(cls, name, login):
        partner = cls.Partner.create(
            {
                "name": name,
                "type_partner": "orientadora",
                "agent": True,
                "agent_type": "orientadora",
                "commission_id": cls.commission.id,
            }
        )
        member = cls.Member.create(
            {
                "name": name,
                "member_type": "orientadora",
                "partner_id": partner.id,
            }
        )
        return partner, member

    @staticmethod
    def _quarter_start(anchor):
        first_month = ((anchor.month - 1) // 3) * 3 + 1
        return anchor.replace(month=first_month, day=1)

    def _create_target(self, partner, target_date, amount=1000.0):
        return self.Target.create(
            {
                "target_scope": "salesperson",
                "agent_id": partner.id,
                "target_date": target_date,
                "target_amount": amount,
            }
        )

    def _create_confirmed_sale(self, partner, target_date, amount):
        customer = self.Partner.create(
            {
                "name": f"Cliente {target_date:%Y-%m}",
                "agent_ids": [(6, 0, [partner.id])],
            }
        )
        order = self.SaleOrder.create(
            {
                "partner_id": customer.id,
                "date_order": datetime.combine(target_date, time(12, 0)),
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1,
                            "price_unit": amount,
                        },
                    )
                ],
            }
        )
        order.order_line.agent_ids = [
            (
                0,
                0,
                {
                    "agent_id": partner.id,
                    "commission_id": self.commission.id,
                    "commission_split_percent": 100.0,
                },
            )
        ]
        order._action_confirm()
        return order

    def test_monthly_targets_create_one_pending_bonus_and_sync_is_idempotent(self):
        future_quarter = self._quarter_start(
            fields.Date.context_today(self.env.user) + relativedelta(months=4)
        )
        amounts = (1000.0, 2000.0, 3000.0)
        for offset, amount in enumerate(amounts):
            self._create_target(
                self.orientadora,
                future_quarter + relativedelta(months=offset),
                amount,
            )

        bonuses = self.Bonus.search([
            ("agent_id", "=", self.orientadora.id),
            ("year", "=", future_quarter.year),
            ("quarter", "=", f"Q{(future_quarter.month - 1) // 3 + 1}"),
        ])
        self.assertEqual(len(bonuses), 1)
        self.assertTrue(bonuses.auto_generated)
        self.assertEqual(bonuses.target_count, 3)
        self.assertTrue(bonuses.has_all_months)
        self.assertEqual(bonuses.total_target, 6000.0)
        self.assertEqual(bonuses.state, "pending")
        self.assertFalse(bonuses.is_finalized)

        bonuses.bonus_amount = 125.0
        self.Target._sync_all_quarterly_bonuses()
        self.assertEqual(
            self.Bonus.search_count([
                ("agent_id", "=", self.orientadora.id),
                ("year", "=", future_quarter.year),
                ("quarter", "=", bonuses.quarter),
            ]),
            1,
        )
        self.assertEqual(bonuses.bonus_amount, 125.0)

    def test_closed_quarter_recovers_lost_rate_points(self):
        closed_quarter = self._quarter_start(
            fields.Date.context_today(self.env.user) - relativedelta(months=4)
        )
        sales = (700.0, 700.0, 1600.0)
        for offset, amount in enumerate(sales):
            target_date = closed_quarter + relativedelta(months=offset)
            self._create_confirmed_sale(self.orientadora, target_date, amount)
            self._create_target(self.orientadora, target_date)

        bonus = self.Bonus.search([
            ("agent_id", "=", self.orientadora.id),
            ("year", "=", closed_quarter.year),
            ("quarter", "=", f"Q{(closed_quarter.month - 1) // 3 + 1}"),
        ])
        self.assertEqual(len(bonus), 1)
        self.assertEqual(bonus.total_achieved, 3000.0)
        self.assertAlmostEqual(bonus.quarterly_pct, 100.0)

        self.Bonus._cron_sync_and_finalize_quarterly_bonuses()
        self.assertTrue(bonus.is_finalized)
        self.assertTrue(bonus.is_eligible)
        self.assertEqual(bonus.state, "recovered")
        # 70% uses 0.45%; 100% uses 0.75%. The IS-CRM adjustment is not
        # included, so the two months recover 0.30% of their commission base.
        self.assertAlmostEqual(bonus.lost_commission_recovered, 4.2)

        self.Bonus._cron_sync_and_finalize_quarterly_bonuses()
        self.assertEqual(bonus.state, "recovered")
        self.assertEqual(
            self.Bonus.search_count([
                ("agent_id", "=", self.orientadora.id),
                ("year", "=", closed_quarter.year),
                ("quarter", "=", bonus.quarter),
            ]),
            1,
        )

    def test_closed_quarter_with_missing_months_is_incomplete(self):
        closed_quarter = self._quarter_start(
            fields.Date.context_today(self.env.user) - relativedelta(months=4)
        )
        self._create_target(self.orientadora, closed_quarter)
        self._create_target(
            self.orientadora, closed_quarter + relativedelta(months=1)
        )
        self.Bonus._cron_sync_and_finalize_quarterly_bonuses()

        bonus = self.Bonus.search([
            ("agent_id", "=", self.orientadora.id),
            ("year", "=", closed_quarter.year),
            ("quarter", "=", f"Q{(closed_quarter.month - 1) // 3 + 1}"),
        ])
        self.assertTrue(bonus.is_finalized)
        self.assertFalse(bonus.has_all_months)
        self.assertEqual(bonus.state, "incomplete")
        self.assertEqual(bonus.lost_commission_recovered, 0.0)

    def test_closed_quarter_below_target_is_lost(self):
        closed_quarter = self._quarter_start(
            fields.Date.context_today(self.env.user) - relativedelta(months=4)
        )
        for offset in range(3):
            self._create_target(
                self.orientadora, closed_quarter + relativedelta(months=offset)
            )
        self.Bonus._cron_sync_and_finalize_quarterly_bonuses()

        bonus = self.Bonus.search([
            ("agent_id", "=", self.orientadora.id),
            ("year", "=", closed_quarter.year),
            ("quarter", "=", f"Q{(closed_quarter.month - 1) // 3 + 1}"),
        ])
        self.assertTrue(bonus.is_finalized)
        self.assertFalse(bonus.is_eligible)
        self.assertEqual(bonus.state, "lost")
        self.assertEqual(bonus.lost_commission_recovered, 0.0)

    def test_target_amount_change_refreshes_same_bonus(self):
        future_quarter = self._quarter_start(
            fields.Date.context_today(self.env.user) + relativedelta(months=4)
        )
        target = self._create_target(self.orientadora, future_quarter, 1000.0)
        bonus = self.Bonus.search([
            ("agent_id", "=", self.orientadora.id),
            ("year", "=", future_quarter.year),
            ("quarter", "=", f"Q{(future_quarter.month - 1) // 3 + 1}"),
        ])
        self.assertEqual(bonus.total_target, 1000.0)

        target.target_amount = 1750.0
        self.assertEqual(bonus.total_target, 1750.0)
        self.assertEqual(
            self.Bonus.search_count([
                ("agent_id", "=", self.orientadora.id),
                ("year", "=", future_quarter.year),
                ("quarter", "=", bonus.quarter),
            ]),
            1,
        )
