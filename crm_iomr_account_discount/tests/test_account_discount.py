# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import Form

from odoo.addons.base.tests.common import BaseCommon


class TestAccountDiscount(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.env.user.groups_id |= cls.env.ref("account.group_account_invoice")
        cls.partner = cls.env["res.partner"].create({"name": "Test"})
        cls.product = cls.env["product.product"].create({"name": "Test Product"})
        cls.account = cls.env["account.account"].search(
            [("account_type", "=", "income")],
            limit=1,
        )
        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "sale")],
            limit=1,
        )

    def _create_invoice(self, discount=0.0, discount_fixed=0.0):
        return (
            self.env["account.move"]
            .with_context(check_move_validity=False)
            .create(
                {
                    "journal_id": self.journal.id,
                    "partner_id": self.partner.id,
                    "move_type": "out_invoice",
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product.id,
                                "quantity": 1.0,
                                "account_id": self.account.id,
                                "name": "Line 1",
                                "price_unit": 200.00,
                                "discount": discount,
                                "discount_fixed": discount_fixed,
                            },
                        )
                    ],
                }
            )
        )

    def test_01_percentage_discount_not_lost(self):
        """A percentage discount without discount_value must be preserved."""
        invoice = self._create_invoice(discount=20.0)
        line = invoice.invoice_line_ids
        self.assertEqual(line.discount, 20.0)
        self.assertEqual(line.discount_value, 0.0)
        self.assertEqual(line.price_subtotal, 160.00)
        self.assertEqual(invoice.amount_total, 160.00)

    def test_03_fixed_discount_still_works(self):
        """The fixed discount flow from account_invoice_fixed_discount is kept."""
        invoice = self._create_invoice()
        with Form(invoice) as invoice_form:
            with invoice_form.invoice_line_ids.edit(0) as line:
                line.discount_fixed = 57.00
        line = invoice.invoice_line_ids
        self.assertEqual(line.discount_fixed, 57.00)
        self.assertEqual(line.discount, 28.5)
        self.assertEqual(line.price_subtotal, 143.00)

    def test_04_percentage_kept_when_mixed(self):
        """A % discount survives together with a fixed discount on the line."""
        invoice = self._create_invoice(discount=10.0, discount_fixed=30.0)
        line = invoice.invoice_line_ids
        self.assertEqual(line.discount, 10.0)
        self.assertEqual(line.discount_fixed, 30.00)
        self.assertEqual(line.price_subtotal, 170.00)