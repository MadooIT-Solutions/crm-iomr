# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestProductSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ProductProduct = cls.env["product.product"]
        cls.ProductTemplate = cls.env["product.template"]

        cls.group_sale_salesman = cls.env.ref("sales_team.group_sale_salesman")
        cls.group_sale_manager = cls.env.ref("sales_team.group_sale_manager")

        cls.salesman_user = cls.env["res.users"].create(
            {
                "name": "Salesman Test",
                "login": "salesman_test",
                "groups_id": [(6, 0, [cls.group_sale_salesman.id])],
            }
        )
        cls.manager_user = cls.env["res.users"].create(
            {
                "name": "Manager Test",
                "login": "manager_test",
                "groups_id": [(6, 0, [cls.group_sale_manager.id])],
            }
        )

    def test_salesman_cannot_create_product_template(self):
        with self.assertRaises(AccessError):
            self.ProductTemplate.sudo(self.salesman_user.id).create(
                {"name": "Test Product"}
            )

    def test_salesman_cannot_create_product_product(self):
        template = self.ProductTemplate.sudo(self.manager_user.id).create(
            {"name": "Base Product"}
        )
        with self.assertRaises(AccessError):
            self.ProductProduct.sudo(self.salesman_user.id).create(
                {
                    "product_tmpl_id": template.id,
                }
            )

    def test_manager_can_create_product_template(self):
        product = self.ProductTemplate.sudo(self.manager_user.id).create(
            {"name": "Manager Product"}
        )
        self.assertTrue(product)

    def test_manager_can_create_product_product(self):
        template = self.ProductTemplate.sudo(self.manager_user.id).create(
            {"name": "Base Product"}
        )
        product = self.ProductProduct.sudo(self.manager_user.id).create(
            {
                "product_tmpl_id": template.id,
            }
        )
        self.assertTrue(product)
