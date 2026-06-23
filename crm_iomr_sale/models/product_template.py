# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, models
from odoo.exceptions import AccessError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model_create_multi
    def create(self, vals_list):
        if self._is_sale_user_restricted():
            raise AccessError(
                _(
                    "You are not allowed to create products. "
                    "Only users with Administrator access in Sales can create products."
                )
            )
        return super().create(vals_list)

    @api.model
    def _is_sale_user_restricted(self):
        return (
            self.env.user.has_group("sales_team.group_sale_salesman")
            and not self.env.user.has_group("sales_team.group_sale_manager")
        )
