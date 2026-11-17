# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Sincronização dos agentes da fatura com os agentes do pedido.

O fechamento de comissões lê somente as linhas de agente da fatura
(``account.invoice.line.agent``). Se uma regra de comissão aparecer depois que
a fatura foi emitida, só o pedido recebe o agente e a comissão some do
fechamento (caso do pedido S00580). Estes testes cobrem o compute e o reparo
idempotente das faturas já gravadas.
"""

from datetime import date

from odoo.tests.common import TransactionCase


class TestInvoiceAgentSync(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Agent = cls.env["account.invoice.line.agent"]
        cls.category = cls.env["product.category"].create(
            {"name": "Sync agentes fatura"}
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Produto sync agentes fatura",
                "categ_id": cls.category.id,
                "type": "consu",
                "list_price": 100.0,
                "taxes_id": [(5, 0, 0)],
                "supplier_taxes_id": [(5, 0, 0)],
            }
        )
        cls.commission = cls.env["commission"].create(
            {
                "name": "Comissão sync agentes fatura",
                "commission_type": "fixed",
                "fix_qty": 1.0,
            }
        )
        cls.agent = cls.env["res.partner"].create(
            {
                "name": "Orientadora sync agentes fatura",
                "type_partner": "orientadora",
                "agent": True,
                "agent_type": "orientadora",
                "commission_id": cls.commission.id,
            }
        )

    def _create_invoice_line(self, with_sale_agent=True):
        """Cria pedido + fatura postada ligada à linha do pedido."""
        customer = self.env["res.partner"].create(
            {"name": f"Cliente {self._testMethodName}"}
        )
        order = self.env["sale.order"].create(
            {"partner_id": customer.id, "date_order": "2026-09-01 12:00:00"}
        )
        sale_line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.product.id,
                "product_uom_qty": 1.0,
                "price_unit": 1000.0,
                "tax_id": [(5, 0, 0)],
            }
        )
        if with_sale_agent:
            sale_line.agent_ids = [
                (5, 0, 0),
                (
                    0,
                    0,
                    {
                        "agent_id": self.agent.id,
                        "commission_id": self.commission.id,
                        "commission_split_percent": 100.0,
                    },
                ),
            ]
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": customer.id,
                "invoice_date": date(2026, 9, 1),
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 1000.0,
                            "tax_ids": [(5, 0, 0)],
                            "sale_line_ids": [(6, 0, sale_line.ids)],
                        },
                    )
                ],
            }
        )
        return invoice.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
        )

    def _delete_agent_rows(self, lines):
        """Remove linhas de agente direto no SQL (bypass da constraint OCA)."""
        self.env.cr.execute(
            "DELETE FROM account_invoice_line_agent WHERE object_id = ANY(%s)",
            (lines.ids,),
        )
        self.env.invalidate_all()

    def test_01_invoice_takes_agents_from_linked_sale_line(self):
        """A fatura copia os agentes da linha de venda vinculada."""
        line = self._create_invoice_line()
        self.assertEqual(line.agent_ids.mapped("agent_id"), self.agent)
        self.assertEqual(line.agent_ids.commission_id, self.commission)

    def test_02_backfill_restores_missing_agent(self):
        """O reparo recria o agente faltante com comissão e split do pedido."""
        line = self._create_invoice_line()
        self._delete_agent_rows(line)

        created = line._backfill_missing_agents_from_sale_lines()

        self.assertEqual(created, 1)
        self.assertEqual(line.agent_ids.mapped("agent_id"), self.agent)
        self.assertEqual(line.agent_ids.commission_id, self.commission)
        self.assertEqual(line.agent_ids.commission_split_percent, 100.0)
        self.assertEqual(round(line.agent_ids.amount, 2), 10.0)

    def test_03_backfill_is_idempotent(self):
        """Rodar o reparo duas vezes não duplica o agente."""
        line = self._create_invoice_line()
        self._delete_agent_rows(line)

        self.assertEqual(line._backfill_missing_agents_from_sale_lines(), 1)
        self.assertEqual(line._backfill_missing_agents_from_sale_lines(), 0)
        self.assertEqual(len(line.agent_ids), 1)

    def test_04_backfill_does_not_change_existing_agent(self):
        """Um agente já existente (ex.: fechado) nunca é alterado."""
        line = self._create_invoice_line()
        other = self.env["commission"].create(
            {
                "name": "Comissão histórica",
                "commission_type": "fixed",
                "fix_qty": 2.0,
            }
        )
        self.env.cr.execute(
            "UPDATE account_invoice_line_agent SET commission_id = %s "
            "WHERE object_id = %s",
            (other.id, line.id),
        )
        self.env.invalidate_all()

        self.assertEqual(line._backfill_missing_agents_from_sale_lines(), 0)
        self.assertEqual(len(line.agent_ids), 1)
        self.assertEqual(line.agent_ids.commission_id, other)

    def test_05_backfill_ignores_line_without_sale_link(self):
        """Sem linha de venda vinculada não há origem para copiar o agente."""
        customer = self.env["res.partner"].create(
            {"name": f"Cliente avulso {self._testMethodName}"}
        )
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": customer.id,
                "invoice_date": date(2026, 9, 1),
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "tax_ids": [(5, 0, 0)],
                        },
                    )
                ],
            }
        )
        line = invoice.invoice_line_ids.filtered(
            lambda inv_line: inv_line.display_type == "product"
        )
        self.assertEqual(line._backfill_missing_agents_from_sale_lines(), 0)
