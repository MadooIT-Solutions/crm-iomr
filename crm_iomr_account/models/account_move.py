# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    opportunity_id = fields.Many2one(
        comodel_name="crm.lead",
        string="Oportunidade",
        compute="_compute_opportunity_id",
        store=True,
        help="Oportunidade do primeiro pedido de venda vinculado às linhas da "
        "fatura. Fica vazio quando a fatura não origina de um pedido de venda.",
    )

    @api.depends("invoice_line_ids.sale_line_ids.order_id.opportunity_id")
    def _compute_opportunity_id(self):
        for move in self:
            orders = move.invoice_line_ids.sale_line_ids.order_id
            move.opportunity_id = orders.sorted("id")[:1].opportunity_id
