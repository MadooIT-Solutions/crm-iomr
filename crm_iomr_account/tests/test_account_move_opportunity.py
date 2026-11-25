# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAccountMoveOpportunity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Cliente Oportunidade"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "Produto Oportunidade",
                "type": "consu",
                "list_price": 100.0,
            }
        )
        cls.opportunity_1 = cls.env["crm.lead"].create(
            {"name": "Oportunidade 1", "type": "opportunity"}
        )
        cls.opportunity_2 = cls.env["crm.lead"].create(
            {"name": "Oportunidade 2", "type": "opportunity"}
        )

    def _create_sale_order(self, opportunity):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "opportunity_id": opportunity.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1.0,
                        },
                    )
                ],
            }
        )
        # Bypass action_confirm(): only the "sale" state is needed to invoice,
        # and other modules may add unrelated required fields on confirmation.
        order.write({"state": "sale"})
        return order

    def test_invoice_gets_opportunity_from_sale_order(self):
        order = self._create_sale_order(self.opportunity_1)
        invoice = order._create_invoices()
        self.assertEqual(invoice.opportunity_id, self.opportunity_1)

    def test_invoice_without_sale_order_has_no_opportunity(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )
        self.assertFalse(invoice.opportunity_id)

    def test_opportunity_follows_sale_order_update(self):
        order = self._create_sale_order(self.opportunity_1)
        invoice = order._create_invoices()
        order.opportunity_id = self.opportunity_2
        self.assertEqual(invoice.opportunity_id, self.opportunity_2)

    def test_first_opportunity_kept_on_consolidated_invoice(self):
        order_1 = self._create_sale_order(self.opportunity_1)
        order_2 = self._create_sale_order(self.opportunity_2)
        invoice = (order_1 | order_2)._create_invoices()
        self.assertEqual(len(invoice), 1)
        self.assertEqual(invoice.opportunity_id, self.opportunity_1)

    def test_customer_invoice_list_shows_opportunity(self):
        view = self.env.ref("account.view_out_invoice_tree")
        self.assertIn('name="opportunity_id"', view.get_combined_arch())
