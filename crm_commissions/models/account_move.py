# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class AccountInvoiceLineAgent(models.Model):
    _inherit = "account.invoice.line.agent"

    @api.depends(
        "object_id.price_subtotal",
        "object_id.commission_free",
        "commission_id",
    )
    def _compute_amount(self):
        super()._compute_amount()
        for line in self:
            if line.invoice_id.move_type and "refund" in line.invoice_id.move_type:
                line.amount = -line.amount
            if line.commission_split_percent:
                line.amount *= line.commission_split_percent / 100.0
