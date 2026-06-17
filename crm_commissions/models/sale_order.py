# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    doctor_id = fields.Many2one(
        "res.partner",
        string="Doctor/Médico",
        domain=[("type_partner", "in", ("doctorint", "doctorext"))],
    )
    is_crm_score = fields.Float(
        string="IS-CRM score",
        default=100.0,
    )
    discount_approved = fields.Boolean(string="Discount approved", default=False)
    margin_percent = fields.Float(
        string="Margin (%)",
        compute="_compute_margin",
        store=True,
    )

    @api.depends("order_line.price_subtotal", "order_line.product_id.standard_price")
    def _compute_margin(self):
        for rec in self:
            total_cost = sum(
                rec.order_line.mapped(
                    lambda line: line.product_id.standard_price * line.product_uom_qty
                )
            )
            total_revenue = rec.amount_untaxed
            if total_revenue:
                rec.margin_percent = (
                    (total_revenue - total_cost) / total_revenue * 100.0
                )
            else:
                rec.margin_percent = 0.0
