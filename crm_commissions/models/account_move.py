# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class AccountInvoiceLineAgent(models.Model):
    _inherit = "account.invoice.line.agent"

    @api.depends(
        "object_id.price_subtotal",
        "object_id.commission_free",
        "object_id.quantity",
        "commission_id",
        "commission_split_percent",
    )
    def _compute_amount(self):
        """Apply the agent split to the invoice commission amount.

        The OCA computation only looks at the commission itself, so a row
        carrying 25% (SDR) or 50% (doctor referral) would otherwise be paid in
        full on the invoice even though the sale line holds the right share.
        """
        result = super()._compute_amount()
        for line in self:
            line.amount = line.amount or 0.0
            if line.commission_split_percent:
                line.amount *= line.commission_split_percent / 100.0
        return result
