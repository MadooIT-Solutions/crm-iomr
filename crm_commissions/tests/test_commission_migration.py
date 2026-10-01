# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Tests for the 18.0.1.6.0 migration that rebuilds honorário commissions.

The wrong state is built by hand (the compute no longer produces it) and the
migration functions are called directly, so the cleanup is exercised without
depending on a full module upgrade.
"""

import importlib.util
from datetime import date
from pathlib import Path

from odoo.tests.common import TransactionCase

_MIGRATION_DIR = (
    Path(__file__).resolve().parents[1] / "migrations" / "18.0.1.6.0"
)


def _load(filename):
    path = _MIGRATION_DIR / filename
    spec = importlib.util.spec_from_file_location(f"_mig_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCommissionMigration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pre = _load("pre-migrate.py")
        cls.post = _load("post-migrate.py")
        cls.ResPartner = cls.env["res.partner"]
        cls.commission = cls.env["commission"].create(
            {"name": "Fixa 1% Migracao", "commission_type": "fixed", "fix_qty": 1.0}
        )
        cls.vendedor = cls.ResPartner.create(
            {
                "name": "Vendedor Vazamento",
                "type_partner": "employee",
                "agent": True,
                "agent_type": "agent",
                "commission_id": cls.commission.id,
                "salesman_as_agent": True,
            }
        )
        cls.doctor = cls.ResPartner.create(
            {
                "name": "Dr Certinho",
                "type_partner": "doctorint",
                "agent": True,
                "agent_type": "doctor",
                "commission_id": cls.commission.id,
            }
        )
        cls.categ = cls.env["product.category"].create(
            {"name": "HONORARIO MIGRACAO"}
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Honorario Migracao",
                "categ_id": cls.categ.id,
                "list_price": 1000.0,
                "standard_price": 0.0,
            }
        )
        cls.customer = cls.ResPartner.create(
            {
                "name": "Cliente Migracao",
                "agent_ids": [(6, 0, [cls.vendedor.id, cls.doctor.id])],
            }
        )
        cls.order = cls.env["sale.order"].create(
            {
                "partner_id": cls.customer.id,
                "doctor_id": cls.doctor.id,
                "order_line": [
                    (0, 0, {"product_id": cls.product.id, "product_uom_qty": 1,
                            "price_unit": 1000.0}),
                ],
            }
        )
        cls.line = cls.order.order_line

    def _force_wrong_agents(self):
        """Reproduce the pre-1.6.0 state: non-doctor agents on a honorário line."""
        self.line.agent_ids = [
            (5, 0, 0),
            (0, 0, {"agent_id": self.vendedor.id,
                    "commission_id": self.commission.id}),
            (0, 0, {"agent_id": self.doctor.id,
                    "commission_id": self.commission.id}),
        ]
        self.assertEqual(len(self.line.agent_ids), 2)

    def _make_invoice_and_settlement(self, agent):
        """Create an invoice agent line + settlement, as the settle wizard does."""
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer.id,
                "invoice_date": date.today(),
                "invoice_line_ids": [
                    (0, 0, {
                        "product_id": self.product.id,
                        "quantity": 1,
                        "price_unit": 1000.0,
                        "agent_ids": [
                            (0, 0, {"agent_id": agent.id,
                                    "commission_id": self.commission.id}),
                        ],
                    }),
                ],
            }
        )
        inv_agent = invoice.invoice_line_ids.agent_ids
        # Only posted invoices are settleable (_skip_settlement).
        invoice.action_post()
        settlement = self.env["commission.settlement"].create(
            {
                "agent_id": agent.id,
                "date_from": date(date.today().year, date.today().month, 1),
                "date_to": date.today(),
                "settlement_type": "sale_invoice",
            }
        )
        self.env["commission.settlement.line"].create(
            {
                "settlement_id": settlement.id,
                "invoice_agent_line_id": inv_agent.id,
                "date": date.today(),
                "commission_id": self.commission.id,
                "settled_amount": 10.0,
            }
        )
        return settlement, inv_agent

    def test_01_migration_removes_non_doctor_from_honorario(self):
        self._force_wrong_agents()
        self.pre.migrate(self.env.cr, "18.0.1.5.1")
        self.post.migrate(self.env.cr, "18.0.1.5.1")
        self.assertEqual(
            self.line.agent_ids.mapped("agent_id"),
            self.doctor,
            "só o médico do pedido deve permanecer",
        )

    def test_02_migration_rebuilds_doctor_settlement(self):
        """The doctor settlement is released then regenerated: releasing only
        the wrong ones is not enough, because a doctor line still held by a
        settlement cannot be recomputed."""
        self._force_wrong_agents()
        self._make_invoice_and_settlement(self.doctor)
        self.pre.migrate(self.env.cr, "18.0.1.5.1")
        self.post.migrate(self.env.cr, "18.0.1.5.1")
        settlements = self.env["commission.settlement"].search(
            [("agent_id", "=", self.doctor.id), ("state", "!=", "cancel")]
        )
        self.assertTrue(
            settlements,
            "o repasse do médico deve ser recriado pela migração",
        )
        self.assertEqual(
            settlements.mapped("line_ids").mapped("agent_id"),
            self.doctor,
        )

    def test_03_migration_removes_non_doctor_settlement(self):
        self._force_wrong_agents()
        wrong_settlement, _inv = self._make_invoice_and_settlement(self.vendedor)
        self.assertTrue(wrong_settlement.exists())
        self.pre.migrate(self.env.cr, "18.0.1.5.1")
        self.post.migrate(self.env.cr, "18.0.1.5.1")
        self.assertFalse(
            wrong_settlement.exists(),
            "repasse do agente não-médico deve ser removido",
        )
        self.assertFalse(
            self.env["commission.settlement"].search(
                [("agent_id", "=", self.vendedor.id), ("state", "!=", "cancel")]
            ),
            "nenhum repasse deve sobrar para o agente não-médico",
        )

    def test_04_migration_unblocks_settled_invoice_lines(self):
        """The settlement must be released before the recompute, or the
        'You can't modify a settled line' constraint aborts the upgrade."""
        self._force_wrong_agents()
        wrong_settlement, inv_agent = self._make_invoice_and_settlement(self.vendedor)
        self.assertTrue(
            any(
                line.settlement_id.state != "cancel"
                for line in inv_agent.settlement_line_ids
            ),
            "pré-condição: a linha de fatura está settled",
        )
        self.pre.migrate(self.env.cr, "18.0.1.5.1")
        # Must not raise: this is what used to break the upgrade.
        self.post.migrate(self.env.cr, "18.0.1.5.1")

    def test_05_migration_is_idempotent(self):
        self._force_wrong_agents()
        self.pre.migrate(self.env.cr, "18.0.1.5.1")
        self.post.migrate(self.env.cr, "18.0.1.5.1")
        first = self.line.agent_ids.mapped("agent_id")
        self.pre.migrate(self.env.cr, "18.0.1.5.1")
        self.post.migrate(self.env.cr, "18.0.1.5.1")
        self.assertEqual(self.line.agent_ids.mapped("agent_id"), first)

    def test_06_migration_leaves_normal_lines_untouched(self):
        cat_ok = self.env["product.category"].create({"name": "CATEGORIA NORMAL"})
        prod_ok = self.env["product.product"].create(
            {"name": "Produto Normal", "categ_id": cat_ok.id,
             "list_price": 1000.0, "standard_price": 0.0}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "doctor_id": self.doctor.id,
                "order_line": [
                    (0, 0, {"product_id": prod_ok.id, "product_uom_qty": 1,
                            "price_unit": 1000.0}),
                ],
            }
        )
        line_ok = order.order_line
        line_ok._compute_agent_ids()
        before = line_ok.agent_ids.mapped("agent_id")
        self.assertIn(self.vendedor, before)
        self.pre.migrate(self.env.cr, "18.0.1.5.1")
        self.post.migrate(self.env.cr, "18.0.1.5.1")
        self.assertEqual(
            line_ok.agent_ids.mapped("agent_id"),
            before,
            "linhas fora de honorário/procedimento não devem ser alteradas",
        )
