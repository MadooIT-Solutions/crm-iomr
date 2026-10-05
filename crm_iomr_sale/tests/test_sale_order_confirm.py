# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestSaleOrderConfirm(TransactionCase):
    """Required fields checked when a sale order is confirmed."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env["res.partner"]
        cls.Product = cls.env["product.product"].create(
            {
                "name": "Produto Teste Confirmação",
                "type": "consu",
                "sale_ok": True,
                "list_price": 100.0,
            }
        )
        cls.Convenio = cls.Partner.create(
            {"name": "Convênio Teste", "type_partner": "convenio"}
        )
        cls.Doctor = cls.Partner.create(
            {"name": "Médico Teste", "type_partner": "doctorint"}
        )
        cls.Customer = cls.Partner.create(
            {"name": "Paciente Teste Confirmação", "type_partner": "patient"}
        )
        cls.PaymentMethod = cls.env["sale.payment.method"].create({"name": "PIX Teste"})

    def _make_order(self, **overrides):
        lead = self.env["crm.lead"].create(
            {
                "name": "Oportunidade Teste Confirmação",
                "partner_id": self.Customer.id,
                "type": "opportunity",
                "convenio": self.Convenio.id,
                "doctor": self.Doctor.id,
            }
        )
        vals = {
            "partner_id": self.Customer.id,
            "opportunity_id": lead.id,
            "doctor_id": self.Doctor.id,
            "order_line": [
                (0, 0, {"product_id": self.Product.id, "product_uom_qty": 1})
            ],
        }
        vals.update(overrides)
        return self.env["sale.order"].create(vals)

    def test_confirm_without_payment_method_raises(self):
        order = self._make_order()
        self.assertFalse(order.payment_method_ids)
        with self.assertRaises(UserError):
            order.action_confirm()
        self.assertEqual(order.state, "draft")

    def test_confirm_with_payment_method_succeeds(self):
        order = self._make_order(payment_method_ids=[(6, 0, self.PaymentMethod.ids)])
        order.action_confirm()
        self.assertEqual(order.state, "sale")

    def test_convenio_is_filled_from_opportunity(self):
        """The related field must be set before the payment method check."""
        order = self._make_order()
        self.assertEqual(order.convenio, self.Convenio)
