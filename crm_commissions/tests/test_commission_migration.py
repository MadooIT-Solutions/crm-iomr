# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Tests for the 18.0.1.6.0 migration that rebuilds honorário commissions.

The wrong state is built by hand (the compute no longer produces it) and the
migration functions are called directly, so the cleanup is exercised without
depending on a full module upgrade.
"""

import importlib.util
from pathlib import Path

from odoo.tests.common import TransactionCase

_MIGRATION_DIR = Path(__file__).resolve().parents[1] / "migrations" / "18.0.1.6.0"


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
        cls.categ = cls.env["product.category"].create({"name": "HONORARIO MIGRACAO"})
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
                    (
                        0,
                        0,
                        {
                            "product_id": cls.product.id,
                            "product_uom_qty": 1,
                            "price_unit": 1000.0,
                        },
                    ),
                ],
            }
        )
        cls.line = cls.order.order_line

    def _force_wrong_agents(self):
        """Reproduce the pre-1.6.0 state: non-doctor agents on a honorário line."""
        self.line.agent_ids = [
            (5, 0, 0),
            (0, 0, {"agent_id": self.vendedor.id, "commission_id": self.commission.id}),
            (0, 0, {"agent_id": self.doctor.id, "commission_id": self.commission.id}),
        ]
        self.assertEqual(len(self.line.agent_ids), 2)

    def test_01_migration_removes_non_doctor_from_honorario(self):
        self._force_wrong_agents()
        self.pre.migrate(self.env.cr, "18.0.1.5.1")
        self.post.migrate(self.env.cr, "18.0.1.5.1")
        self.assertEqual(
            self.line.agent_ids.mapped("agent_id"),
            self.doctor,
            "só o médico do pedido deve permanecer",
        )

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
            {
                "name": "Produto Normal",
                "categ_id": cat_ok.id,
                "list_price": 1000.0,
                "standard_price": 0.0,
            }
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "doctor_id": self.doctor.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": prod_ok.id,
                            "product_uom_qty": 1,
                            "price_unit": 1000.0,
                        },
                    ),
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
