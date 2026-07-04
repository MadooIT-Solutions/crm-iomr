# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model_create_multi
    def create(self, vals_list):
        restricted = self.env["product.template"]._is_sale_user_restricted()
        if restricted:
            raise AccessError(
                _(
                    "You are not allowed to create products. "
                    "Only users with Administrator access in Sales can create products."
                )
            )
        return super().create(vals_list)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    prontuario = fields.Char(
        string="Prontuário",
        related="partner_id.prontuario",
        readonly=False,
    )
