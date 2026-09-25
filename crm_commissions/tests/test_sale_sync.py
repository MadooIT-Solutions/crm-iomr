# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase


class TestSaleSync(TransactionCase):
    """commission.sale is auto-synced from confirmed sale orders.

    The Vendas menu (Repasses/Vendas) is fed by commission.sale. Those records
    are created/updated automatically when a sale order is confirmed and the
    orientadora's partner appears as an agent on the order lines.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Member = cls.env["commission.member"]
        cls.Sale = cls.env["commission.sale"]
        cls.Partner = cls.env["res.partner"]
        cls.Category = cls.env["product.category"].create(
            {"name": "Teste Cirurgia Repasses"}
        )
        cls.Product = cls.env["product.product"].create(
            {
                "name": "Produto Teste Repasses",
                "categ_id": cls.Category.id,
                "type": "consu",
                "sale_ok": True,
                "list_price": 100.0,
                "standard_price": 30.0,
            }
        )
        cls.Commission = cls.env.ref("crm_commissions.commission_progressive_lios")
        cls.Pricelist = (
            cls.env.ref("product.list0", raise_if_not_found=False)
            or cls.env["product.pricelist"].search([], limit=1)
        )

    def _make_orientadora(self, name="Test Orientadora"):
        partner = self.Partner.create(
            {
                "name": name,
                "type_partner": "orientadora",
                "agent": True,
                "agent_type": "orientadora",
            }
        )
        member = self.Member.create(
            {
                "name": name,
                "member_type": "orientadora",
                "partner_id": partner.id,
            }
        )
        return partner, member

    def _make_order(self, customer, orientadora_partner):
        order = self.env["sale.order"].create(
            {
                "partner_id": customer.id,
                "partner_invoice_id": customer.id,
                "partner_shipping_id": customer.id,
                "pricelist_id": self.Pricelist.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.Product.id,
                            "product_uom_qty": 2,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )
        line = order.order_line[0]
        line.agent_ids = [
            (
                0,
                0,
                {
                    "agent_id": orientadora_partner.id,
                    "commission_id": self.Commission.id,
                    "commission_split_percent": 100.0,
                },
            )
        ]
        return order

    def test_01_confirm_creates_sale(self):
        customer = self.Partner.create({"name": "Paciente Teste"})
        partner, member = self._make_orientadora()
        order = self._make_order(customer, partner)
        order._action_confirm()

        sales = self.Sale.search(
            [
                ("owner_member_id", "=", member.id),
                ("source_order_id", "=", order.id),
            ]
        )
        self.assertEqual(len(sales), 1)
        sale = sales[0]
        self.assertEqual(sale.status, "confirmed")
        self.assertEqual(sale.patient_name, "Paciente Teste")
        self.assertEqual(sale.sale_category, "particular")
        self.assertEqual(sale.hospital_gross_amount, order.amount_total)
        self.assertEqual(sale.owner_member_id, member)
        self.assertTrue(sale.line_ids)

    def test_02_sync_is_idempotent(self):
        customer = self.Partner.create({"name": "Paciente Teste 2"})
        partner, member = self._make_orientadora()
        order = self._make_order(customer, partner)
        order._action_confirm()
        order._sync_commission_sales_from_orders()

        count = self.Sale.search_count(
            [
                ("owner_member_id", "=", member.id),
                ("source_order_id", "=", order.id),
            ]
        )
        self.assertEqual(count, 1)

    def test_03_cancel_marks_sale_cancelled(self):
        customer = self.Partner.create({"name": "Paciente Teste 3"})
        partner, member = self._make_orientadora()
        order = self._make_order(customer, partner)
        order._action_confirm()
        order._action_cancel()

        sale = self.Sale.search(
            [
                ("owner_member_id", "=", member.id),
                ("source_order_id", "=", order.id),
            ],
            limit=1,
        )
        self.assertTrue(sale)
        self.assertEqual(sale.status, "cancelled")

    def test_04_order_without_orientadora_agent_creates_nothing(self):
        customer = self.Partner.create({"name": "Paciente Teste 4"})
        order = self.env["sale.order"].create(
            {
                "partner_id": customer.id,
                "partner_invoice_id": customer.id,
                "partner_shipping_id": customer.id,
                "pricelist_id": self.Pricelist.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.Product.id,
                            "product_uom_qty": 1,
                            "price_unit": 50.0,
                        },
                    )
                ],
            }
        )
        order._action_confirm()
        self.assertEqual(self.Sale.search_count([("source_order_id", "=", order.id)]), 0)

    def test_05_convenio_maps_to_convenio_category(self):
        customer = self.Partner.create({"name": "Paciente Teste 5"})
        partner, member = self._make_orientadora()
        order = self._make_order(customer, partner)
        # crm.lead.convenio é provido por crm_iomr_auto; sale.order.convenio é
        # related a opportunity_id.convenio (crm_iomr_sale).
        if "convenio" in order._fields:
            convenio_partner = self.Partner.create(
                {"name": "Unimed", "type_partner": "convenio"}
            )
            lead = self.env["crm.lead"].create(
                {
                    "name": "Oportunidade Teste",
                    "partner_id": customer.id,
                    "convenio": convenio_partner.id,
                }
            )
            order.opportunity_id = lead
        order._action_confirm()
        sale = self.Sale.search(
            [
                ("owner_member_id", "=", member.id),
                ("source_order_id", "=", order.id),
            ],
            limit=1,
        )
        if "convenio" in order._fields:
            self.assertEqual(sale.sale_category, "convenio")
        else:
            self.assertEqual(sale.sale_category, "particular")

    def test_06_salesperson_confirms_order_without_access_error(self):
        """Confirming as a plain salesperson (no commission ACLs) must not break
        and must still sync the sale via sudo()."""
        customer = self.Partner.create({"name": "Paciente Teste 6"})
        partner, member = self._make_orientadora()
        user = self.env["res.users"].create(
            {
                "name": "Vendedor Teste Sync",
                "login": "vendedor_teste_sync",
                "groups_id": [
                    (6, 0, [self.env.ref("sales_team.group_sale_salesman").id])
                ],
            }
        )
        order = self._make_order(customer, partner)
        order.with_user(user)._action_confirm()

        sales = self.Sale.sudo().search(
            [
                ("owner_member_id", "=", member.id),
                ("source_order_id", "=", order.id),
            ]
        )
        self.assertEqual(len(sales), 1)
        self.assertEqual(sales.status, "confirmed")