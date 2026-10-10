# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestCommissionValidation(TransactionCase):
    """Saving an order must not silently drop a commission the rules owe.

    The agents are built by ``sale.order.line``'s compute, but the field is
    editable, so a save is the last moment to notice that an expected
    commission of any type (médico, orientadora, SDR or coordenadora) is
    missing.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Commission = cls.env["commission"]
        cls.ResPartner = cls.env["res.partner"]
        cls.Product = cls.env["product.product"]
        cls.Category = cls.env["product.category"]
        cls.company = cls.env.ref("base.main_company")

        cls.commission = cls.Commission.create(
            {
                "name": "Validação Fixa 10%",
                "commission_type": "fixed",
                "fix_qty": 10.0,
                "amount_base_type": "gross_amount",
            }
        )
        cls.coordinator_commission = cls.env.ref(
            "crm_commissions.commission_coordinator_policy"
        )

        cls.coordenadora = cls.ResPartner.create(
            {
                "name": "Coordenadora Validação",
                "type_partner": "coordenadora",
                "agent": True,
                "agent_type": "coordenadora",
                "commission_id": cls.coordinator_commission.id,
            }
        )
        cls.orientadora = cls.ResPartner.create(
            {
                "name": "Orientadora Validação",
                "type_partner": "orientadora",
                "agent": True,
                "agent_type": "orientadora",
                "commission_id": cls.commission.id,
                "coordenadora_id": cls.coordenadora.id,
            }
        )
        cls.sdr = cls.ResPartner.create(
            {
                "name": "SDR Validação",
                "type_partner": "sdr",
                "agent": True,
                "agent_type": "sdr",
                "commission_id": cls.commission.id,
            }
        )
        cls.doctor = cls.ResPartner.create(
            {
                "name": "Dr Validação",
                "type_partner": "doctorint",
                "agent": True,
                "agent_type": "doctor",
                "commission_id": cls.commission.id,
            }
        )
        cls.convenio = cls.ResPartner.create(
            {"name": "Convênio Validação", "type_partner": "convenio"}
        )

        cls.category = cls.Category.create({"name": "VALIDACAO CATEG"})
        cls.product = cls._create_product("Produto Validação", cls.category)
        cls.customer = cls.ResPartner.create(
            {
                "name": "Cliente Validação",
                "agent_ids": [(6, 0, [cls.orientadora.id])],
            }
        )

    @classmethod
    def _create_product(cls, name, categ, **extra):
        vals = {
            "name": name,
            "categ_id": categ.id,
            "type": "consu",
            "sale_ok": True,
            "list_price": 100.0,
            "taxes_id": [(5, 0, 0)],
            "invoice_policy": "order",
        }
        vals.update(extra)
        return cls.Product.create(vals)

    def _create_order(self, product=None, doctor=True):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "doctor_id": self.doctor.id if doctor else False,
            }
        )
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": (product or self.product).id,
                "product_uom_qty": 1,
                "price_unit": 100.0,
            }
        )
        return order, line

    def _remove_agent(self, line, partner):
        line.agent_ids.filtered(lambda agent: agent.agent_id == partner).unlink()
        self.env.flush_all()

    def test_01_complete_order_has_all_types_and_saves(self):
        order, line = self._create_order()
        agents = line.agent_ids.mapped("agent_id")
        self.assertIn(self.doctor, agents)
        self.assertIn(self.orientadora, agents)
        self.assertIn(self.coordenadora, agents)

        # A second save of a complete order is not blocked.
        order.write({"note": "salvo pelo usuário"})

    def test_02_expected_partners_follow_the_rules(self):
        order, line = self._create_order()
        self.assertEqual(
            set(line._get_expected_agent_partners()),
            {self.doctor, self.orientadora, self.coordenadora},
        )

    def test_03_missing_doctor_blocks_save(self):
        order, line = self._create_order()
        self._remove_agent(line, self.doctor)
        with self.assertRaises(ValidationError):
            order.write({"note": "salvo pelo usuário"})

    def test_04_missing_orientadora_blocks_save_with_clear_message(self):
        order, line = self._create_order()
        self._remove_agent(line, self.orientadora)
        with self.assertRaises(ValidationError) as error:
            order.write({"note": "salvo pelo usuário"})
        message = str(error.exception)
        self.assertIn(self.orientadora.name, message)
        self.assertIn("Orientadora", message)

    def test_05_missing_coordenadora_blocks_save(self):
        order, line = self._create_order()
        self._remove_agent(line, self.coordenadora)
        with self.assertRaises(ValidationError):
            order.write({"note": "salvo pelo usuário"})

    def test_06_excluded_category_only_requires_the_doctor(self):
        """HONORARIO/PROCEDIMENTO pay only the doctor, so orientadora and
        coordenadora are not owed and their absence must not block the save.
        """
        category = self.Category.create({"name": "HONORARIO VALIDACAO"})
        product = self._create_product("Honorário Validação", category)
        order, line = self._create_order(product=product)

        agents = line.agent_ids.mapped("agent_id")
        self.assertEqual(agents, self.doctor)
        order.write({"note": "salvo pelo usuário"})

    def test_07_commission_free_line_is_not_checked(self):
        product = self._create_product(
            "Produto Sem Comissão", self.category, commission_free=True
        )
        order, line = self._create_order(product=product)

        self.assertFalse(line.agent_ids)
        order.write({"note": "salvo pelo usuário"})

    def test_08_save_blocks_when_created_without_agents(self):
        """The create itself is validated, not only later writes."""
        with self.assertRaises(ValidationError):
            self.env["sale.order"].create(
                {
                    "partner_id": self.customer.id,
                    "doctor_id": self.doctor.id,
                    "order_line": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product.id,
                                "product_uom_qty": 1,
                                "price_unit": 100.0,
                                "agent_ids": [(5, 0, 0)],
                            },
                        )
                    ],
                }
            )

    def test_09_rotation_sdr_is_required(self):
        order, line = self._create_sdr_order()
        agents = line.agent_ids.mapped("agent_id")
        self.assertIn(self.sdr, agents)

        self._remove_agent(line, self.sdr)
        with self.assertRaises(ValidationError):
            order.write({"note": "salvo pelo usuário"})

    def test_10_sdr_owned_opportunity_is_required(self):
        """An opportunity created directly by the SDR owes her commission too."""
        order, line = self._create_sdr_order(with_rotation=False)
        agents = line.agent_ids.mapped("agent_id")
        self.assertIn(self.sdr, agents)

        self._remove_agent(line, self.sdr)
        with self.assertRaises(ValidationError):
            order.write({"note": "salvo pelo usuário"})

    def test_11_cancelled_order_is_not_blocked(self):
        order, line = self._create_order()
        self._remove_agent(line, self.doctor)
        order.write({"state": "cancel"})
        order.write({"note": "salvo pelo usuário"})

    def test_12_unrelated_write_keeps_a_complete_order_saved(self):
        order, line = self._create_order()
        order.write({"client_order_ref": "PO-123"})
        self.assertEqual(order.client_order_ref, "PO-123")

    def _create_sdr_order(self, with_rotation=True):
        sdr_user = self.env["res.users"].create(
            {
                "name": "SDR User Validação",
                "login": "sdr_validacao_user",
                "partner_id": self.sdr.id,
                "company_id": self.company.id,
                "company_ids": [(6, 0, [self.company.id])],
            }
        )
        lead = self.env["crm.lead"].create(
            {
                "name": "Oportunidade Validação",
                "partner_id": self.customer.id,
                "user_id": sdr_user.id,
                "convenio": self.convenio.id,
                "doctor": self.doctor.id,
            }
        )
        if with_rotation:
            self.env["crm.lead.rotation"].create(
                {
                    "lead_id": lead.id,
                    "user_to_id": sdr_user.id,
                    "rotation_sequence": 1,
                    "rotation_type": "lost_sdr",
                }
            )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "doctor_id": self.doctor.id,
                "opportunity_id": lead.id,
            }
        )
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.product.id,
                "product_uom_qty": 1,
                "price_unit": 100.0,
            }
        )
        return order, line
