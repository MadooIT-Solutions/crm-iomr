# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date, datetime, time

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestCrmSettlement(TransactionCase):
    """Fechamento dos dois tipos de settlement do CRM.

    * ``crm_performance``: a linha fatura a comissão calculada (base elegível
      × taxa da Política 2026 ± IS-CRM) e não o bruto atingido pela meta.
    * ``crm_quarterly_recovery``: a comissão perdida e recuperada no
      fechamento do trimestre vira linha de settlement, uma única vez.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.SettleLine = cls.env["commission.settlement.line"]
        cls.Target = cls.env["crm.commission.target"]
        cls.Bonus = cls.env["crm.commission.quarterly.bonus"]
        cls.commission = cls.env.ref("crm_commissions.commission_progressive_lios")
        cls.policy = cls.env.ref("crm_commissions.policy_2026")
        cls.category = cls.env["product.category"].create({"name": "Settlement CRM"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "Produto Settlement CRM",
                "categ_id": cls.category.id,
                "type": "consu",
                "list_price": 100.0,
                "taxes_id": [(5, 0, 0)],
                "supplier_taxes_id": [(5, 0, 0)],
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Orientadora Settlement CRM",
                "type_partner": "orientadora",
                "agent": True,
                "agent_type": "orientadora",
                "commission_id": cls.commission.id,
                "settlement": "monthly",
            }
        )
        cls.member = cls.env["commission.member"].create(
            {
                "name": "Orientadora Settlement CRM",
                "member_type": "orientadora",
                "partner_id": cls.partner.id,
            }
        )

    def _create_target(self, target_date, amount=1000.0):
        return self.Target.create(
            {
                "target_scope": "salesperson",
                "agent_id": self.partner.id,
                "target_date": target_date,
                "target_amount": amount,
            }
        )

    @staticmethod
    def _quarter_start(anchor):
        first_month = ((anchor.month - 1) // 3) * 3 + 1
        return anchor.replace(month=first_month, day=1)

    def _make_settle_wizard(self, settlement_type, date_to=None):
        return self.env["commission.make.settle"].create(
            {
                "date_to": date_to or fields.Date.context_today(self.env.user),
                "agent_ids": [(6, 0, [self.partner.id])],
                "settlement_type": settlement_type,
            }
        )

    def test_01_crm_performance_bills_commission_not_gross(self):
        """A meta de 100% fatura base × (0,75% + 0,25% IS-CRM) = 1% e não R$ 1.000."""
        target_date = date(2026, 3, 1)
        target = self._create_target(target_date, 1000.0)
        self.env["commission.sale"].create(
            {
                "name": "Venda Settlement CRM 2026-03",
                "owner_member_id": self.member.id,
                "patient_name": "Paciente Settlement CRM",
                "surgery_type": "catarata",
                "sale_category": "particular",
                "date": date(2026, 3, 15),
                "hospital_gross_amount": 1000.0,
                "status": "confirmed",
                "line_ids": [(0, 0, {"line_type": "hospital", "amount": 1000.0})],
            }
        )
        target._refresh_from_sale_changes()

        self.assertEqual(target.achieved_amount, 1000.0)
        self.assertEqual(target.performance_pct, 100.0)
        self.assertTrue(target.is_crm_ok)
        self.assertEqual(target._get_commission_base(), 1000.0)
        # Política 2026: exatamente 100% → 0,75% de taxa base.
        self.assertEqual(target._get_rate_for_performance(100.0), 0.75)

        wizard = self._make_settle_wizard("crm_performance", target_date)
        wizard.action_settle()

        line = self.SettleLine.search([("target_id", "=", target.id)])
        self.assertEqual(len(line), 1)
        self.assertEqual(line.settlement_id.settlement_type, "crm_performance")
        self.assertEqual(line.date, target_date)
        self.assertEqual(line.commission_id, self.commission)
        # 1000 * (0,75 + 0,25) / 100 = 10,00 — e nunca o bruto de 1.000.
        self.assertAlmostEqual(line.settled_amount, 10.0)
        self.assertNotEqual(line.settled_amount, target.achieved_amount)

        # Segunda rodada não duplica a linha da meta.
        wizard.action_settle()
        self.assertEqual(
            self.SettleLine.search_count([("target_id", "=", target.id)]), 1
        )

    def test_02_rate_gap_between_policy_bands_falls_to_next_band(self):
        """Performance no intervalo entre faixas nunca cai na última (1,75%)."""
        target = self._create_target(date(2026, 3, 1), 1000.0)
        # 50,5% está na lacuna 50→51 da tabela configurada.
        self.assertEqual(target._get_rate_for_performance(50.5), 0.45)
        # Acima do maior limite usa a última faixa, como manda a política.
        self.assertEqual(target._get_rate_for_performance(150.0), 1.75)

    def test_03_quarterly_recovery_is_billed_once(self):
        """A comissão recuperada no fechamento do trimestre vira settlement."""
        closed_quarter = self._quarter_start(
            fields.Date.context_today(self.env.user) - relativedelta(months=4)
        )
        for offset, amount in enumerate((700.0, 700.0, 1600.0)):
            target_date = closed_quarter + relativedelta(months=offset)
            self._create_confirmed_sale(target_date, amount)
            self._create_target(target_date, 1000.0)

        self.Bonus._cron_sync_and_finalize_quarterly_bonuses()
        bonus = self.Bonus.search(
            [
                ("agent_id", "=", self.partner.id),
                ("year", "=", closed_quarter.year),
                (
                    "quarter",
                    "=",
                    f"Q{(closed_quarter.month - 1) // 3 + 1}",
                ),
            ]
        )
        self.assertEqual(len(bonus), 1)
        self.assertEqual(bonus.state, "recovered")
        self.assertGreater(bonus.lost_commission_recovered, 0.0)

        wizard = self._make_settle_wizard("crm_quarterly_recovery")
        wizard.action_settle()

        line = self.SettleLine.search([("quarterly_bonus_id", "=", bonus.id)])
        self.assertEqual(len(line), 1)
        self.assertEqual(line.settlement_id.settlement_type, "crm_quarterly_recovery")
        self.assertEqual(line.date, bonus.date_to)
        self.assertEqual(line.settlement_id.date_to, bonus.date_to)
        self.assertEqual(line.commission_id, self.commission)
        self.assertAlmostEqual(line.settled_amount, bonus.lost_commission_recovered)
        self.assertNotEqual(line.settled_amount, bonus.total_achieved)

        # O fechamento seguinte não fatura a mesma recuperação de novo.
        wizard.action_settle()
        self.assertEqual(
            self.SettleLine.search_count([("quarterly_bonus_id", "=", bonus.id)]), 1
        )

    def test_04_settlement_line_points_back_to_its_sale_order(self):
        """A linha fechada pela fatura aponta o pedido e o clique abre ele.

        A coluna "Pedido de venda" das linhas de comissão vem de
        ``sale_order_id``: a linha da fatura aponta as linhas de venda que
        ela faturou (``sale_line_ids``), e de lá se sobe até o pedido.
        """
        invoice_date = date(2026, 3, 15)
        order = self._create_confirmed_sale(invoice_date, 1000.0)
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": order.partner_id.id,
                "invoice_date": invoice_date,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1,
                            "price_unit": 1000.0,
                            "tax_ids": [(5, 0, 0)],
                            "sale_line_ids": [(6, 0, order.order_line.ids)],
                        },
                    )
                ],
            }
        )
        agent_line = invoice.invoice_line_ids.agent_ids
        self.assertEqual(agent_line.agent_id, self.partner)
        # Só fatura postada entra em settlement (``_skip_settlement``).
        invoice.action_post()

        # Fecha o mês de março, onde caiu a fatura.
        self._make_settle_wizard("sale_invoice", date(2026, 4, 1)).action_settle()

        line = self.SettleLine.search([("invoice_agent_line_id", "=", agent_line.id)])
        self.assertEqual(len(line), 1)
        self.assertEqual(line.sale_order_id, order)
        action = line.action_open_sale_order()
        self.assertEqual(action["res_model"], "sale.order")
        self.assertEqual(action["res_id"], order.id)

    def test_05_settlement_line_without_invoice_has_no_sale_order(self):
        """Fechamento de meta não fatura um pedido único: fica sem pedido.

        A meta do mês cobre todas as vendas sincronizadas do período, então
        a linha fechada não aponta um pedido só -- e não abre nenhum.
        """
        target = self._create_target(date(2026, 3, 1), 1000.0)
        self._create_confirmed_sale(date(2026, 3, 15), 1000.0)
        target._refresh_from_sale_changes()
        self.assertTrue(target.achieved_amount)

        wizard = self._make_settle_wizard("crm_performance", date(2026, 4, 1))
        wizard.action_settle()

        line = self.SettleLine.search([("target_id", "=", target.id)])
        self.assertEqual(len(line), 1)
        self.assertFalse(line.sale_order_id)
        self.assertFalse(line.action_open_sale_order())

    def _create_confirmed_sale(self, target_date, amount):
        customer = self.env["res.partner"].create(
            {
                "name": f"Cliente Settlement {target_date:%Y-%m}",
                "agent_ids": [(6, 0, [self.partner.id])],
            }
        )
        order = self.env["sale.order"].create(
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
                            # Sem imposto padrão da empresa: o atingido da meta
                            # é lido do valor total do pedido.
                            "tax_id": [(5, 0, 0)],
                        },
                    )
                ],
            }
        )
        order.order_line.agent_ids = [
            (5, 0, 0),
            (
                0,
                0,
                {
                    "agent_id": self.partner.id,
                    "commission_id": self.commission.id,
                    "commission_split_percent": 100.0,
                },
            ),
        ]
        order._action_confirm()
        return order
