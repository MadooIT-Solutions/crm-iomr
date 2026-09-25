# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    discount = fields.Float(
        compute="_compute_discounts",
        store=True,
        readonly=False,
        string="Discount (%)",
    )

    @api.depends("quantity", "price_unit", "discount_value")
    def _compute_discounts(self):
        """Keep the percentage discount when no ``discount_value`` is given.

        ``l10n_br_account`` redefines the ``discount`` field as a stored
        computed field derived only from ``discount_value``. Invoice lines
        created from a sale order carry the discount percentage but no
        ``discount_value``, so the compute used to reset the discount to zero
        and the invoice was issued without any discount.
        """
        for line in self:
            if line.discount_value:
                line.discount = (line.discount_value * 100) / (
                    line.quantity * line.price_unit or 1
                )