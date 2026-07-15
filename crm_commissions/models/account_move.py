from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.depends("move_id.partner_id")
    def _compute_agent_ids(self):
        self.agent_ids = False
        for record in self:
            if (
                record.move_id.partner_id
                and record.move_id.move_type[:3] == "out"
                and not record.commission_free
                and record.product_id
            ):
                if record.sale_line_ids:
                    sale_agents = record.sale_line_ids[0].agent_ids
                    if sale_agents:
                        record.agent_ids = [
                            (0, 0, {
                                "agent_id": x.agent_id.id,
                                "commission_id": x.commission_id.id,
                                "commission_split_percent": x.commission_split_percent,
                            })
                            for x in sale_agents
                        ]
                        continue
                record.agent_ids = record._prepare_agents_vals_partner(
                    record.move_id.partner_id, settlement_type="sale_invoice"
                )


class AccountInvoiceLineAgent(models.Model):
    _inherit = "account.invoice.line.agent"

    @api.depends(
        "object_id.price_subtotal",
        "object_id.commission_free",
        "object_id.quantity",
        "commission_id",
    )
    def _compute_amount(self):
        super()._compute_amount()
        for line in self:
            line.amount = line.amount or 0.0
            if line.commission_split_percent:
                line.amount *= line.commission_split_percent / 100.0
