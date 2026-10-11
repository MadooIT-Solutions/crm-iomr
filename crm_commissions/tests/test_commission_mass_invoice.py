# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields
from odoo.tests.common import TransactionCase


class TestCommissionMassInvoice(TransactionCase):
    """Mass commission invoicing wizard.

    The wizard used to group the selected settlements with the recordset
    ``groupby`` helper, which was removed in Odoo 18. These tests cover the
    grouping paths so the removed API cannot come back unnoticed.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = cls.env["res.partner"].create(
            {"name": "Mass Invoice Agent", "agent": True}
        )
        cls.commission = cls.env["commission"].create(
            {
                "name": "Mass invoice commission",
                "commission_type": "fixed",
                "amount_base_type": "gross_amount",
                "fix_qty": 10.0,
            }
        )
        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", cls.env.company.id)],
            limit=1,
        )
        if not cls.journal:
            cls.journal = cls.env["account.journal"].create(
                {
                    "name": "Mass Invoice Purchases",
                    "code": "MIP",
                    "type": "purchase",
                }
            )
        cls.product = cls.env["product.product"].create(
            {"name": "Mass invoice commission", "type": "service"}
        )

    def _create_settlement(self, agent, date_from, date_to, amount):
        settlement = self.env["commission.settlement"].create(
            {
                "agent_id": agent.id,
                "date_from": date_from,
                "date_to": date_to,
                "state": "settled",
                "settlement_type": "manual",
            }
        )
        self.env["commission.settlement.line"].create(
            {
                "settlement_id": settlement.id,
                "date": date_from,
                "commission_id": self.commission.id,
                "settled_amount": amount,
            }
        )
        settlement.invalidate_recordset(["total"])
        return settlement

    def _create_wizard(self, settlements, group_by="agent"):
        return self.env["commission.mass.invoice"].create(
            {
                "journal_id": self.journal.id,
                "product_id": self.product.id,
                "group_by": group_by,
                "settlement_ids": [(6, 0, settlements.ids)],
            }
        )

    def test_01_group_by_agent(self):
        """Grouping by agent invoiced the settlement without the removed API."""
        settlement = self._create_settlement(
            self.agent,
            fields.Date.to_date("2026-01-01"),
            fields.Date.to_date("2026-01-31"),
            100.0,
        )
        wizard = self._create_wizard(settlement, group_by="agent")

        result = wizard.action_create_invoices()

        self.assertEqual(result["res_model"], "account.move")
        invoice_ids = result["domain"][0][2]
        self.assertTrue(invoice_ids)
        self.assertEqual(settlement.state, "invoiced")
        self.assertIn(settlement.invoice_id.id, invoice_ids)

    def test_02_group_by_period(self):
        """Two periods for the same agent produce two invoices."""
        january = self._create_settlement(
            self.agent,
            fields.Date.to_date("2026-01-01"),
            fields.Date.to_date("2026-01-31"),
            100.0,
        )
        february = self._create_settlement(
            self.agent,
            fields.Date.to_date("2026-02-01"),
            fields.Date.to_date("2026-02-28"),
            200.0,
        )
        settlements = january | february
        wizard = self._create_wizard(settlements, group_by="period")

        result = wizard.action_create_invoices()

        self.assertEqual(len(result["domain"][0][2]), 2)
        self.assertEqual(set(settlements.mapped("state")), {"invoiced"})

    def test_03_group_individual(self):
        """One invoice per settlement in individual mode."""
        settlements = self._create_settlement(
            self.agent,
            fields.Date.to_date("2026-01-01"),
            fields.Date.to_date("2026-01-31"),
            100.0,
        ) | self._create_settlement(
            self.agent,
            fields.Date.to_date("2026-02-01"),
            fields.Date.to_date("2026-02-28"),
            200.0,
        )
        wizard = self._create_wizard(settlements, group_by="individual")

        result = wizard.action_create_invoices()

        self.assertEqual(len(result["domain"][0][2]), 2)
        self.assertEqual(set(settlements.mapped("state")), {"invoiced"})
