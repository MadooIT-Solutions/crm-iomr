# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Fechamento de fatura quando o desconto/entrada muda o valor faturado.

A base de cada linha de fechamento é a comissão do agente no pedido rateada
pelo valor efetivamente faturado **das linhas do agente**:

    base = comissão_do_pedido × faturado_do_agente / valor_ordenado_do_agente

O acumulado por fatura impede pagar mais que a comissão do pedido, e as
entradas/adiantamentos seguem a regra descrita no plano:

* sem agente, a entrada é ignorada nas duas pontas e a fatura final absorve a
  parte dela;
* com agente, a entrada recebe a sua fatia e a fatura final só o restante.
"""

from datetime import date, datetime, time

from odoo.tests.common import TransactionCase


class TestInvoiceDiscountSettlement(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.SettleLine = cls.env["commission.settlement.line"]
        cls.category = cls.env["product.category"].create(
            {"name": "Fechamento desconto fatura"}
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Produto fechamento desconto",
                "categ_id": cls.category.id,
                "type": "consu",
                "list_price": 100.0,
                "taxes_id": [(5, 0, 0)],
                "supplier_taxes_id": [(5, 0, 0)],
            }
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _create_commission(self, name, commission_type="fixed", fix_qty=1.0):
        values = {
            "name": f"{name} {self._testMethodName}",
            "commission_type": commission_type,
        }
        if commission_type == "fixed":
            values["fix_qty"] = fix_qty
        return self.env["commission"].create(values)

    def _create_product_commission(self, amount):
        commission = self._create_commission("Repasse", "product")
        self.env["commission.item"].create(
            {
                "commission_id": commission.id,
                "applied_on": "2_product_category",
                "categ_id": self.category.id,
                "commission_type": "fixed",
                "fixed_amount": amount,
            }
        )
        return commission

    def _create_agent(self, name, commission):
        return self.env["res.partner"].create(
            {
                "name": f"{name} {self._testMethodName}",
                "type_partner": "orientadora",
                "agent": True,
                "agent_type": "orientadora",
                "commission_id": commission.id,
                "settlement": "monthly",
            }
        )

    def _create_order(self, lines, order_date=date(2026, 3, 15)):
        """Create a confirmed order. ``lines`` get their ``sale_line`` filled."""
        customer = self.env["res.partner"].create(
            {"name": f"Cliente {self._testMethodName} {len(lines)}"}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": customer.id,
                "date_order": datetime.combine(order_date, time(12, 0)),
            }
        )
        for spec in lines:
            sale_line = self.env["sale.order.line"].create(
                {
                    "order_id": order.id,
                    "product_id": spec.get("product", self.product).id,
                    "product_uom_qty": spec.get("quantity", 1.0),
                    "price_unit": spec["price_unit"],
                    "tax_id": [(5, 0, 0)],
                }
            )
            if spec.get("agent"):
                sale_line.agent_ids = [
                    (5, 0, 0),
                    (
                        0,
                        0,
                        {
                            "agent_id": spec["agent"].id,
                            "commission_id": spec["commission"].id,
                            "commission_split_percent": 100.0,
                        },
                    ),
                ]
            spec["sale_line"] = sale_line
        order._action_confirm()
        return order

    def _create_downpayment(self, order, amount, agent=None, commission=None):
        """Down payment line as created by the sale advance wizard."""
        sale_line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.product.id,
                "product_uom_qty": 0.0,
                "price_unit": amount,
                "is_downpayment": True,
                "tax_id": [(5, 0, 0)],
            }
        )
        if agent:
            sale_line.agent_ids = [
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
        return sale_line

    def _create_invoice(self, order, lines, invoice_date=date(2026, 3, 15)):
        invoice_lines = []
        for spec in lines:
            values = {
                "product_id": self.product.id,
                "quantity": spec.get("quantity", 1.0),
                "price_unit": spec["price_unit"],
                "discount": spec.get("discount", 0.0),
                "tax_ids": [(5, 0, 0)],
            }
            sale_line = spec.get("sale_line")
            if sale_line:
                values["sale_line_ids"] = [(6, 0, sale_line.ids)]
            invoice_lines.append((0, 0, values))
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": order.partner_id.id,
                "invoice_date": invoice_date,
                "invoice_line_ids": invoice_lines,
            }
        )
        invoice.action_post()
        return invoice

    def _pay(self, invoice, payment_date, amount=None):
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

    def _settle(self, agent, date_to=date(2026, 4, 1)):
        self.env["commission.make.settle"].create(
            {
                "date_to": date_to,
                "agent_ids": [(6, 0, [agent.id])],
                "settlement_type": "sale_invoice",
            }
        ).action_settle()

    def _settlement_line(self, invoice_line):
        return self.SettleLine.search(
            [("invoice_line_id", "=", invoice_line.id)]
        )

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------
    def test_01_control_full_invoice_keeps_the_invoice_amount(self):
        """Fatura única sem desconto continua usando o amount da fatura."""
        commission = self._create_commission("Fixa 1%")
        agent = self._create_agent("Orientadora Controle", commission)
        spec = {
            "price_unit": 1000.0,
            "agent": agent,
            "commission": commission,
        }
        order = self._create_order([spec])
        invoice = self._create_invoice(
            order, [{"price_unit": 1000.0, "sale_line": spec["sale_line"]}]
        )
        self._pay(invoice, date(2026, 3, 20))

        self._settle(agent, date(2026, 4, 1))

        line = self._settlement_line(invoice.invoice_line_ids)
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.invoice_base_amount, 10.0, places=2)
        self.assertAlmostEqual(line.settled_amount, 10.0, places=2)

    def test_02_invoice_only_discount_prorates_the_commission(self):
        """Desconto aplicado só na fatura reduz a comissão na proporção."""
        commission = self._create_commission("Fixa 1%")
        agent = self._create_agent("Orientadora Desconto", commission)
        spec = {
            "price_unit": 1000.0,
            "agent": agent,
            "commission": commission,
        }
        order = self._create_order([spec])
        invoice = self._create_invoice(
            order,
            [
                {
                    "price_unit": 1000.0,
                    "discount": 10.0,
                    "sale_line": spec["sale_line"],
                }
            ],
        )
        self.assertAlmostEqual(invoice.amount_total, 900.0, places=2)
        self._pay(invoice, date(2026, 3, 20))

        self._settle(agent, date(2026, 4, 1))

        line = self._settlement_line(invoice.invoice_line_ids)
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.invoice_base_amount, 9.0, places=2)
        self.assertAlmostEqual(line.settled_amount, 9.0, places=2)

    def test_03_product_repasse_is_prorated_by_the_billed_value(self):
        """O repasse fixo do médico também cai com o desconto da fatura."""
        commission = self._create_product_commission(190.0)
        agent = self._create_agent("Dr. Repasse", commission)

        discounted = {"price_unit": 1000.0, "agent": agent, "commission": commission}
        discounted_order = self._create_order([discounted])
        discounted_invoice = self._create_invoice(
            discounted_order,
            [
                {
                    "price_unit": 1000.0,
                    "discount": 10.0,
                    "sale_line": discounted["sale_line"],
                }
            ],
        )

        full = {"price_unit": 1000.0, "agent": agent, "commission": commission}
        full_order = self._create_order([full])
        full_invoice = self._create_invoice(
            full_order, [{"price_unit": 1000.0, "sale_line": full["sale_line"]}]
        )

        self._pay(discounted_invoice, date(2026, 3, 20))
        self._pay(full_invoice, date(2026, 3, 20))
        self._settle(agent, date(2026, 4, 1))

        discounted_line = self._settlement_line(
            discounted_invoice.invoice_line_ids
        )
        self.assertEqual(len(discounted_line), 1)
        self.assertAlmostEqual(discounted_line.invoice_base_amount, 171.0)
        self.assertEqual(discounted_line.commission_id, commission)

        full_line = self._settlement_line(full_invoice.invoice_line_ids)
        self.assertEqual(len(full_line), 1)
        self.assertAlmostEqual(full_line.invoice_base_amount, 190.0)

    def test_04_downpayments_without_agent_are_absorbed_by_the_final_invoice(
        self,
    ):
        """Entrada sem agente não reduz a comissão nem é paga duas vezes."""
        commission = self._create_product_commission(190.0)
        agent = self._create_agent("Dr. Entrada", commission)

        # Pedido 1.000, entradas de 200 + 200 sem agente e fatura final de 600.
        spec = {"price_unit": 1000.0, "agent": agent, "commission": commission}
        order = self._create_order([spec])
        first_advance = self._create_downpayment(order, 200.0)
        first_invoice = self._create_invoice(
            order, [{"price_unit": 200.0, "sale_line": first_advance}]
        )
        second_advance = self._create_downpayment(order, 200.0)
        second_invoice = self._create_invoice(
            order, [{"price_unit": 200.0, "sale_line": second_advance}]
        )
        final_advance = self._create_downpayment(order, 400.0)
        final_invoice = self._create_invoice(
            order,
            [
                {"price_unit": 1000.0, "sale_line": spec["sale_line"]},
                {"price_unit": -400.0, "sale_line": final_advance},
            ],
        )
        self.assertAlmostEqual(final_invoice.amount_total, 600.0, places=2)

        for invoice in (first_invoice, second_invoice, final_invoice):
            self._pay(invoice, date(2026, 3, 20))

        self._settle(agent, date(2026, 4, 1))

        lines = self.SettleLine.search([("agent_id", "=", agent.id)])
        self.assertEqual(len(lines), 1)
        self.assertAlmostEqual(lines.invoice_base_amount, 190.0)

        # Variante com desconto: produto 900 e entrada de 400 → base 171.
        discounted = {
            "price_unit": 1000.0,
            "agent": agent,
            "commission": commission,
        }
        discounted_order = self._create_order([discounted])
        advance = self._create_downpayment(discounted_order, 400.0)
        advance_invoice = self._create_invoice(
            discounted_order, [{"price_unit": 400.0, "sale_line": advance}]
        )
        discounted_invoice = self._create_invoice(
            discounted_order,
            [
                {
                    "price_unit": 1000.0,
                    "discount": 10.0,
                    "sale_line": discounted["sale_line"],
                },
                {"price_unit": -400.0, "sale_line": advance},
            ],
        )
        self._pay(advance_invoice, date(2026, 3, 20))
        self._pay(discounted_invoice, date(2026, 3, 20))
        self._settle(agent, date(2026, 4, 1))

        discounted_line = self._settlement_line(
            discounted_invoice.invoice_line_ids.filtered(
                lambda line: line.price_subtotal > 0
            )
        )
        self.assertEqual(len(discounted_line), 1)
        self.assertAlmostEqual(discounted_line.invoice_base_amount, 171.0)

    def test_05_advances_with_agent_do_not_pay_the_commission_twice(self):
        """Entrada com agente recebe a sua fatia e a final só o restante."""
        commission = self._create_commission("Fixa 0,5%", fix_qty=0.5)
        agent = self._create_agent("Orientadora Entrada", commission)
        spec = {
            "price_unit": 5500.0,
            "agent": agent,
            "commission": commission,
        }
        order = self._create_order([spec])
        advance = self._create_downpayment(order, 4500.0, agent, commission)
        advance_invoice = self._create_invoice(
            order, [{"price_unit": 4500.0, "sale_line": advance}]
        )
        final_invoice = self._create_invoice(
            order,
            [
                {"price_unit": 5500.0, "sale_line": spec["sale_line"]},
                {"price_unit": -4500.0, "sale_line": advance},
            ],
        )
        self._pay(advance_invoice, date(2026, 3, 20))
        self._pay(final_invoice, date(2026, 3, 20))

        self._settle(agent, date(2026, 4, 1))

        advance_line = self._settlement_line(advance_invoice.invoice_line_ids)
        self.assertEqual(len(advance_line), 1)
        self.assertAlmostEqual(advance_line.invoice_base_amount, 22.5, places=2)

        product_line = final_invoice.invoice_line_ids.filtered(
            lambda line: line.price_subtotal > 0
        )
        settled_product = self._settlement_line(product_line)
        self.assertEqual(len(settled_product), 1)
        self.assertAlmostEqual(
            settled_product.invoice_base_amount, 5.0, places=2
        )

        # A linha negativa da entrada não recebe comissão de novo.
        negative_line = final_invoice.invoice_line_ids - product_line
        settled_negative = self._settlement_line(negative_line)
        self.assertEqual(len(settled_negative), 1)
        self.assertAlmostEqual(
            settled_negative.invoice_base_amount, 0.0, places=2
        )

        total = advance_line.invoice_base_amount + settled_product.invoice_base_amount
        self.assertAlmostEqual(total, 27.5, places=2)

    def test_06_split_billing_distributes_the_order_commission(self):
        """Pedido faturado em partes paga a comissão total, sem inflar."""
        commission = self._create_commission("Fixa 1%")
        agent = self._create_agent("Orientadora Parcelada", commission)
        spec = {
            "price_unit": 1820.0,
            "agent": agent,
            "commission": commission,
        }
        order = self._create_order([spec])
        invoices = [
            self._create_invoice(
                order,
                [
                    {
                        "price_unit": 182.0,
                        "sale_line": spec["sale_line"],
                    }
                ],
            )
            for _index in range(10)
        ]
        for invoice in invoices:
            self._pay(invoice, date(2026, 3, 20))

        self._settle(agent, date(2026, 4, 1))

        lines = self.SettleLine.search([("agent_id", "=", agent.id)])
        self.assertEqual(len(lines), 10)
        for line in lines:
            self.assertAlmostEqual(line.invoice_base_amount, 1.82, places=2)
        self.assertAlmostEqual(sum(lines.mapped("invoice_base_amount")), 18.2)

    def test_07_discount_with_partial_payment_keeps_the_prorated_base(self):
        """Fatura com desconto paga em parte fecha proporcional ao recebido."""
        commission = self._create_commission("Fixa 1%")
        agent = self._create_agent("Orientadora Parcial", commission)
        spec = {
            "price_unit": 1000.0,
            "agent": agent,
            "commission": commission,
        }
        order = self._create_order([spec])
        invoice = self._create_invoice(
            order,
            [
                {
                    "price_unit": 1000.0,
                    "discount": 10.0,
                    "sale_line": spec["sale_line"],
                }
            ],
        )
        self._pay(invoice, date(2026, 3, 16), amount=450.0)
        self.assertEqual(invoice.payment_state, "partial")
        self._settle(agent, date(2026, 4, 1))

        line = self._settlement_line(invoice.invoice_line_ids)
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.invoice_base_amount, 9.0, places=2)
        self.assertAlmostEqual(line.settled_amount, 4.5, places=2)
        # Colunas exibidas nas linhas de liquidação de fatura.
        self.assertAlmostEqual(line.invoice_amount, 900.0, places=2)
        self.assertAlmostEqual(line.amount_paid, 450.0, places=2)

        self._pay(invoice, date(2026, 3, 20))
        line.invalidate_recordset()
        self.assertAlmostEqual(line.settled_amount, 9.0, places=2)
        self.assertAlmostEqual(line.invoice_base_amount, 9.0, places=2)
        self.assertAlmostEqual(line.amount_paid, 900.0, places=2)

    def test_08_closed_base_is_frozen_and_invoiced_lines_are_not_rewritten(self):
        """Recalcular não muda a base fechada, nem fechamento já faturado."""
        commission = self._create_commission("Fixa 1%")
        agent = self._create_agent("Orientadora Congelada", commission)
        spec = {
            "price_unit": 1000.0,
            "agent": agent,
            "commission": commission,
        }
        order = self._create_order([spec])
        invoice = self._create_invoice(
            order,
            [
                {
                    "price_unit": 1000.0,
                    "discount": 10.0,
                    "sale_line": spec["sale_line"],
                }
            ],
        )
        self._pay(invoice, date(2026, 3, 20))
        self._settle(agent, date(2026, 4, 1))
        settlement_line = self._settlement_line(invoice.invoice_line_ids)
        self.assertEqual(len(settlement_line), 1)

        # Recalcular é idempotente e usa a regra nova (900/1000).
        settlement_line.action_recompute_settled_amount()
        self.assertAlmostEqual(
            settlement_line.invoice_base_amount, 9.0, places=2
        )
        self.assertAlmostEqual(settlement_line.settled_amount, 9.0, places=2)

        # Alterar o amount do agente não reescreve a base já congelada.
        agent_line = invoice.invoice_line_ids.agent_ids
        agent_line.amount = 1.0
        settlement_line._compute_settled_amount()
        self.assertAlmostEqual(settlement_line.settled_amount, 9.0, places=2)

        # Fechamento já faturado é um fato contábil: não pode ser reescrito.
        settlement_line.settlement_id.state = "invoiced"
        settlement_line.settled_amount = 123.45
        settlement_line._compute_settled_amount()
        self.assertAlmostEqual(settlement_line.settled_amount, 123.45, places=2)

    def test_09_multiple_agent_lines_do_not_multiply_the_commission(self):
        """Duas linhas do mesmo agente dividem a base, não a repetem."""
        commission = self._create_commission("Fixa 1%")
        agent = self._create_agent("Orientadora Dupla", commission)
        first = {"price_unit": 1000.0, "agent": agent, "commission": commission}
        second = {"price_unit": 1000.0, "agent": agent, "commission": commission}
        order = self._create_order([first, second])
        invoice = self._create_invoice(
            order,
            [
                {
                    "price_unit": 1000.0,
                    "discount": 10.0,
                    "sale_line": first["sale_line"],
                },
                {
                    "price_unit": 1000.0,
                    "discount": 10.0,
                    "sale_line": second["sale_line"],
                },
            ],
        )
        self._pay(invoice, date(2026, 3, 20))

        self._settle(agent, date(2026, 4, 1))

        lines = self.SettleLine.search([("agent_id", "=", agent.id)])
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertAlmostEqual(line.invoice_base_amount, 9.0, places=2)
        self.assertAlmostEqual(sum(lines.mapped("invoice_base_amount")), 18.0)

    def test_10_each_agent_receives_only_its_own_line(self):
        """O rateio usa as linhas do agente, não o total do pedido."""
        commission = self._create_commission("Fixa 1%")
        first_agent = self._create_agent("Orientadora A", commission)
        second_agent = self._create_agent("Orientadora B", commission)
        first = {
            "price_unit": 1000.0,
            "agent": first_agent,
            "commission": commission,
        }
        second = {
            "price_unit": 1000.0,
            "agent": second_agent,
            "commission": commission,
        }
        order = self._create_order([first, second])
        first_invoice = self._create_invoice(
            order, [{"price_unit": 1000.0, "sale_line": first["sale_line"]}]
        )
        second_invoice = self._create_invoice(
            order, [{"price_unit": 1000.0, "sale_line": second["sale_line"]}]
        )
        self._pay(first_invoice, date(2026, 3, 20))
        self._pay(second_invoice, date(2026, 3, 20))

        self._settle(first_agent, date(2026, 4, 1))
        self._settle(second_agent, date(2026, 4, 1))

        first_settled = self._settlement_line(first_invoice.invoice_line_ids)
        self.assertEqual(len(first_settled), 1)
        self.assertAlmostEqual(first_settled.invoice_base_amount, 10.0)

        second_settled = self._settlement_line(second_invoice.invoice_line_ids)
        self.assertEqual(len(second_settled), 1)
        self.assertAlmostEqual(second_settled.invoice_base_amount, 10.0)

    def test_11_invoice_with_more_than_one_order_falls_back_to_the_amount(self):
        """Fatura que cobre mais de um pedido não arrisca rateio cruzado."""
        commission = self._create_commission("Fixa 1%")
        agent = self._create_agent("Orientadora Multi", commission)
        first = {"price_unit": 1000.0, "agent": agent, "commission": commission}
        second = {"price_unit": 1000.0, "agent": agent, "commission": commission}
        first_order = self._create_order([first])
        self._create_order([second])
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": first_order.partner_id.id,
                "invoice_date": date(2026, 3, 15),
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 1000.0,
                            "tax_ids": [(5, 0, 0)],
                            "sale_line_ids": [
                                (
                                    6,
                                    0,
                                    (
                                        first["sale_line"]
                                        | second["sale_line"]
                                    ).ids,
                                )
                            ],
                        },
                    )
                ],
            }
        )
        invoice.action_post()
        self._pay(invoice, date(2026, 3, 20))
        agent_line = invoice.invoice_line_ids.agent_ids
        self.assertEqual(len(agent_line), 1)

        with self.assertLogs(
            "odoo.addons.crm_commissions.models.account_move", level="WARNING"
        ):
            base = agent_line._get_settlement_base_amount()
        self.assertAlmostEqual(base, agent_line.amount, places=2)

        self._settle(agent, date(2026, 4, 1))
        settled = self._settlement_line(invoice.invoice_line_ids)
        self.assertEqual(len(settled), 1)
        self.assertAlmostEqual(
            settled.invoice_base_amount, agent_line.amount, places=2
        )

    def test_12_non_invoice_settlements_are_not_prorated(self):
        """Fechamentos manuais/CRM mantêm o valor gravado na criação."""
        commission = self._create_commission("Fixa 1%")
        agent = self._create_agent("Orientadora Manual", commission)
        settlement = self.env["commission.settlement"].create(
            {
                "date_from": date(2026, 3, 1),
                "date_to": date(2026, 3, 31),
                "agent_id": agent.id,
            }
        )
        line = self.SettleLine.create(
            {
                "settlement_id": settlement.id,
                "agent_id": agent.id,
                "date": date(2026, 3, 31),
                "commission_id": commission.id,
                "settled_amount": 42.0,
            }
        )
        line.settled_amount = 42.0
        line._compute_settled_amount()
        self.assertAlmostEqual(line.settled_amount, 42.0)
