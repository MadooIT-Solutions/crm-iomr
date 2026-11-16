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
        invoice.action_post()

        # A fatura postada mas ainda não paga não entra no fechamento.
        self._make_settle_wizard("sale_invoice", date(2026, 4, 1)).action_settle()
        self.assertFalse(
            self.SettleLine.search([("invoice_agent_line_id", "=", agent_line.id)])
        )

        # Paga em abril: o fechamento de abril (rodado em maio) a inclui.
        self._register_payment(invoice, date(2026, 4, 2))
        self._make_settle_wizard("sale_invoice", date(2026, 5, 1)).action_settle()

        line = self.SettleLine.search([("invoice_agent_line_id", "=", agent_line.id)])
        self.assertEqual(len(line), 1)
        self.assertEqual(line.date, date(2026, 4, 2))
        self.assertEqual(line.settlement_id.date_from, date(2026, 4, 1))
        self.assertEqual(line.settlement_id.date_to, date(2026, 4, 30))
        self.assertEqual(line.sale_order_id, order)
        action = line.action_open_sale_order()
        self.assertEqual(action["res_model"], "sale.order")
        self.assertEqual(action["res_id"], order.id)

    def test_07_invoice_settlement_follows_the_payment_date(self):
        """Fatura de setembro paga em outubro fecha no período de outubro.

        O fechamento não pode usar a data da fatura: o período (e a data da
        linha) é o do pagamento. Assim, a fatura não aparece no fechamento de
        setembro e aparece no de outubro.
        """
        invoice_date = date(2026, 9, 20)
        payment_date = date(2026, 10, 5)
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
        invoice.action_post()
        self._register_payment(invoice, payment_date)

        # Fechamento de setembro: a fatura está fora do período.
        self._make_settle_wizard("sale_invoice", date(2026, 10, 1)).action_settle()
        self.assertFalse(
            self.SettleLine.search([("invoice_agent_line_id", "=", agent_line.id)])
        )

        # Fechamento de outubro: entra com a data do pagamento.
        self._make_settle_wizard("sale_invoice", date(2026, 11, 1)).action_settle()
        line = self.SettleLine.search([("invoice_agent_line_id", "=", agent_line.id)])
        self.assertEqual(len(line), 1)
        self.assertEqual(line.date, payment_date)
        self.assertEqual(line.settlement_id.date_from, date(2026, 10, 1))
        self.assertEqual(line.settlement_id.date_to, date(2026, 10, 31))

    def test_08_closing_bills_the_last_crm_of_the_closing_month(self):
        """O fechamento usa o último IS-CRM do mês de fechamento.

        As vendas do mês foram boas, mas a última registrada dentro do mês
        (20/03) teve IS-CRM 90%: o fechamento deve aplicar a penalidade sobre
        o último IS-CRM do mês, e não a média das vendas do período.
        """
        target = self._create_target(date(2026, 3, 1), 1000.0)
        for day, crm_pct in ((10, 100.0), (20, 90.0)):
            self.env["commission.sale"].create(
                {
                    "name": f"Venda Settlement CRM 2026-03-{day}",
                    "owner_member_id": self.member.id,
                    "patient_name": f"Paciente Settlement CRM {day}",
                    "surgery_type": "catarata",
                    "sale_category": "particular",
                    "date": date(2026, 3, day),
                    "hospital_gross_amount": 500.0,
                    "crm_pct": crm_pct,
                    "status": "confirmed",
                    "line_ids": [(0, 0, {"line_type": "hospital", "amount": 500.0})],
                }
            )
        target._refresh_closing_indicators()

        self.assertEqual(target.achieved_amount, 1000.0)
        self.assertEqual(target.performance_pct, 100.0)
        self.assertEqual(target.is_crm_score, 90.0)
        self.assertFalse(target.is_crm_ok)

        wizard = self._make_settle_wizard("crm_performance", date(2026, 4, 1))
        wizard.action_settle()

        line = self.SettleLine.search([("target_id", "=", target.id)])
        self.assertEqual(len(line), 1)
        # 1000 * (0,75 - 0,25) / 100 = 5,00 — penalidade do último IS-CRM do mês.
        self.assertAlmostEqual(line.settled_amount, 5.0)

    def test_08_recomputing_invoice_agents_does_not_duplicate_the_closing(self):
        """Recalcular os agentes da fatura não pode refechar a comissão.

        O recálculo de ``agent_ids`` apaga/recria a linha de agente. Se o
        fechamento já existe, a linha de settlement perdia o vínculo
        (``invoice_agent_line_id`` é ``ON DELETE SET NULL``) e a mesma
        comissão era fechada de novo na rodada seguinte.
        """
        order = self._create_confirmed_sale(date(2026, 3, 15), 1000.0)
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": order.partner_id.id,
                "invoice_date": date(2026, 3, 15),
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
        invoice.action_post()
        self._register_payment(invoice, date(2026, 3, 16))
        agent_line = invoice.invoice_line_ids.agent_ids
        self.assertTrue(agent_line)

        self._make_settle_wizard("sale_invoice", date(2026, 4, 1)).action_settle()
        settlement_line = self.SettleLine.search(
            [("invoice_agent_line_id", "=", agent_line.id)]
        )
        self.assertEqual(len(settlement_line), 1)

        # Simula o recálculo dos agentes que apagava a linha de origem.
        invoice.invoice_line_ids._compute_agent_ids()
        self.assertTrue(agent_line.exists())

        self._make_settle_wizard("sale_invoice", date(2026, 4, 1)).action_settle()
        self.assertEqual(
            self.SettleLine.search_count(
                [("invoice_line_id", "=", invoice.invoice_line_ids.id)]
            ),
            1,
        )

    def test_11_orphan_settlement_line_is_relinked_instead_of_duplicated(self):
        """Linha órfã (agente apagado) é religada, não fechada de novo.

        É o que acontece quando a FK ``invoice_agent_line_id`` é zerada por um
        delete fora do ORM (migração/script). O fechamento seguinte encontra o
        agente recriado, restaura o vínculo da linha antiga e não cria uma
        segunda linha para a mesma fatura.
        """
        order = self._create_confirmed_sale(date(2026, 3, 15), 1000.0)
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": order.partner_id.id,
                "invoice_date": date(2026, 3, 15),
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
        invoice.action_post()
        self._register_payment(invoice, date(2026, 3, 16))
        agent_line = invoice.invoice_line_ids.agent_ids.filtered(
            lambda line: line.agent_id == self.partner
        )
        self._make_settle_wizard("sale_invoice", date(2026, 4, 1)).action_settle()
        settlement_line = self.SettleLine.search(
            [("invoice_agent_line_id", "=", agent_line.id)]
        )
        self.assertEqual(len(settlement_line), 1)
        invoice_line = invoice.invoice_line_ids
        self.env.cr.execute(
            "UPDATE commission_settlement_line "
            "SET invoice_agent_line_id = NULL WHERE id = %s",
            (settlement_line.id,),
        )
        # Delete the agent row without the ORM (as the FK cascade did) and
        # rebuild the invoice agents.
        self.env.cr.execute(
            "DELETE FROM account_invoice_line_agent WHERE id = %s",
            (agent_line.id,),
        )
        self.env.invalidate_all()
        invoice_line._compute_agent_ids()
        self.env.flush_all()
        new_agent_line = invoice_line.agent_ids.filtered(
            lambda line: line.agent_id == self.partner
        )
        self.assertTrue(new_agent_line)
        self.assertNotEqual(new_agent_line, agent_line)

        self._make_settle_wizard("sale_invoice", date(2026, 4, 1)).action_settle()
        settlement_lines = self.SettleLine.search(
            [("invoice_line_id", "=", invoice_line.id)]
        )
        self.assertEqual(len(settlement_lines), 1)
        self.assertEqual(
            settlement_lines.invoice_agent_line_id, new_agent_line
        )

    def test_09_partial_payment_value_follows_the_received_amount(self):
        """Fatura paga em parte fecha proporcionalmente ao valor recebido.

        O valor base é congelado em ``invoice_base_amount``; quando o restante
        é pago, apenas o percentual recebido muda, sem depender do ``amount``
        atual da linha de agente.
        """
        commission = self.env["commission"].create(
            {
                "name": "Fixa 1% - teste parcial",
                "commission_type": "fixed",
                "fix_qty": 1.0,
            }
        )
        agent = self.env["res.partner"].create(
            {
                "name": "Orientadora Parcial",
                "type_partner": "orientadora",
                "agent": True,
                "agent_type": "orientadora",
                "commission_id": commission.id,
                "settlement": "monthly",
            }
        )
        customer = self.env["res.partner"].create(
            {"name": "Cliente Parcial", "agent_ids": [(6, 0, [agent.id])]}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": customer.id,
                "date_order": datetime.combine(date(2026, 3, 15), time(12, 0)),
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1,
                            "price_unit": 1000.0,
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
                    "agent_id": agent.id,
                    "commission_id": commission.id,
                    "commission_split_percent": 100.0,
                },
            ),
        ]
        order._action_confirm()
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": customer.id,
                "invoice_date": date(2026, 3, 15),
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
        invoice.action_post()
        agent_line = invoice.invoice_line_ids.agent_ids.filtered(
            lambda line: line.agent_id == agent
        )
        self.assertAlmostEqual(agent_line.amount, 10.0)

        self._register_payment(invoice, date(2026, 3, 16), amount=400.0)
        self.assertEqual(invoice.payment_state, "partial")
        wizard = self.env["commission.make.settle"].create(
            {
                "date_to": date(2026, 4, 1),
                "agent_ids": [(6, 0, [agent.id])],
                "settlement_type": "sale_invoice",
            }
        )
        wizard.action_settle()
        settlement_line = self.SettleLine.search(
            [("invoice_line_id", "=", invoice.invoice_line_ids.id)]
        )
        self.assertEqual(len(settlement_line), 1)
        self.assertAlmostEqual(settlement_line.settled_amount, 4.0)
        self.assertAlmostEqual(settlement_line.invoice_base_amount, 10.0)

        # Paga o restante: a mesma linha passa a valer a comissão inteira.
        self._register_payment(invoice, date(2026, 3, 20))
        self.assertIn(invoice.payment_state, ("in_payment", "paid"))
        settlement_line.invalidate_recordset()
        self.assertAlmostEqual(settlement_line.settled_amount, 10.0)

    def test_10_zero_performance_commission_is_not_closed(self):
        """Meta sem base não pode gerar linha zero e bloquear o fechamento.

        Uma linha de valor zero fica escondida na tela e marca a meta como
        fechada para sempre, então o fechamento seguinte nunca pagaria a
        comissão quando a base aparecesse.
        """
        commission = self.env["commission"].create(
            {
                "name": "Progressiva teste zero",
                "commission_type": "fixed",
                "fix_qty": 1.0,
            }
        )
        agent = self.env["res.partner"].create(
            {
                "name": "Orientadora Zero",
                "type_partner": "orientadora",
                "agent": True,
                "agent_type": "orientadora",
                "commission_id": commission.id,
                "settlement": "monthly",
            }
        )
        member = self.env["commission.member"].create(
            {
                "name": "Orientadora Zero",
                "member_type": "orientadora",
                "partner_id": agent.id,
            }
        )
        target = self.Target.create(
            {
                "target_scope": "salesperson",
                "agent_id": agent.id,
                "target_date": date(2026, 3, 1),
                "target_amount": 1000.0,
            }
        )
        # Venda sem linhas de detalhe: o atingido existe, mas a base é zero.
        self.env["commission.sale"].create(
            {
                "name": "Venda sem detalhe",
                "owner_member_id": member.id,
                "patient_name": "Paciente Zero",
                "surgery_type": "catarata",
                "sale_category": "particular",
                "date": date(2026, 3, 15),
                "hospital_gross_amount": 1000.0,
                "status": "confirmed",
            }
        )
        target._refresh_from_sale_changes()
        self.assertGreater(target.achieved_amount, 0.0)
        self.assertEqual(target._get_commission_base(), 0.0)

        wizard = self.env["commission.make.settle"].create(
            {
                "date_to": date(2026, 4, 1),
                "agent_ids": [(6, 0, [agent.id])],
                "settlement_type": "crm_performance",
            }
        )
        wizard.action_settle()
        self.assertFalse(
            self.SettleLine.search([("target_id", "=", target.id)])
        )
        self.assertFalse(target._skip_settlement())

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

    def test_06_backfill_restores_the_origin_of_old_lines(self):
        """Linhas lançadas antes da coluna de origem voltam a apontar a origem.

        ``target_id`` e ``quarterly_bonus_id`` são gravados na criação da
        linha pelo wizard de fechamento; as criadas antes disso ficaram sem
        origem, e a migração ``18.0.2.7.0`` os reconstrói pelos mesmos syncs.
        """
        # Meta do mês → linha de CRM Performance.
        target = self._create_target(date(2026, 3, 1), 1000.0)
        self._create_confirmed_sale(date(2026, 3, 15), 1000.0)
        target._refresh_from_sale_changes()
        self._make_settle_wizard("crm_performance", date(2026, 4, 1)).action_settle()
        performance_line = self.SettleLine.search([("target_id", "=", target.id)])
        self.assertEqual(len(performance_line), 1)
        performance_line.write({"target_id": False})

        # Bônus do trimestre fechado → linha de recuperação.
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
        self._make_settle_wizard("crm_quarterly_recovery").action_settle()
        recovery_line = self.SettleLine.search([("quarterly_bonus_id", "=", bonus.id)])
        self.assertEqual(len(recovery_line), 1)
        recovery_line.write({"quarterly_bonus_id": False})

        self.Target._sync_settlement_line_targets()
        self.Target._sync_settlement_line_quarterly_bonuses()

        self.assertEqual(performance_line.target_id, target)
        self.assertEqual(recovery_line.quarterly_bonus_id, bonus)

    def _register_payment(self, invoice, payment_date, amount=None):
        """Register a payment for the invoice on ``payment_date``.

        ``amount`` limits the payment to a partial value; by default the
        whole residual is paid.
        """
        journal = self.env["account.journal"].search(
            [
                ("type", "in", ("bank", "cash")),
                ("company_id", "=", self.env.company.id),
            ],
            limit=1,
        )
        values = {"journal_id": journal.id, "payment_date": payment_date}
        if amount is not None:
            values["amount"] = amount
        wizard = (
            self.env["account.payment.register"]
            .with_context(
                active_model="account.move",
                active_ids=invoice.ids,
                dont_redirect_to_payments=True,
            )
            .create(values)
        )
        wizard.action_create_payments()
        if amount is None:
            self.assertIn(invoice.payment_state, ("in_payment", "paid"))
        return invoice.reconciled_payment_ids

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
