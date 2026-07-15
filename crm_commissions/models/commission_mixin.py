# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class CommissionLineMixin(models.AbstractModel):
    _inherit = "commission.line.mixin"

    commission_split_percent = fields.Float(
        string="Commission Split (%)",
        default=100.0,
    )

    def _get_product_category_ids(self, product):
        categ_ids = set()
        categ = product.categ_id
        while categ:
            categ_ids.add(categ.id)
            categ = categ.parent_id
        return list(categ_ids)

    def _get_commission_amount(self, commission, subtotal, product, quantity):
        self.ensure_one()
        if commission and commission.commission_type == "progressive":
            if commission.categ_ids and product and product.categ_id:
                categ_ids = self._get_product_category_ids(product)
                commission_categ_ids = set(commission.categ_ids.ids)
                if not any(cid in commission_categ_ids for cid in categ_ids):
                    return 0.0
            order = (
                self.object_id.order_id
                if hasattr(self.object_id, "order_id")
                else False
            )
            target = False
            is_crm_ok = True
            if order and order.opportunity_id and order.opportunity_id.user_id:
                partner = order.opportunity_id.user_id.partner_id
                agent = partner if partner.type_partner == "orientadora" else False
                if not agent and partner.type_partner == "sdr":
                    agent = self.env["res.partner"].search(
                        [
                            ("type_partner", "=", "orientadora"),
                            ("sdr_agent_ids", "in", partner.id),
                        ],
                        limit=1,
                    )
                if agent:
                    target = self.env["crm.commission.target"].search(
                        [
                            ("agent_id", "=", agent.id),
                            ("state", "=", "in_progress"),
                        ],
                        order="target_date desc",
                        limit=1,
                    )
            if "is_crm_ok" in self.env.context:
                is_crm_ok = self.env.context.get("is_crm_ok", True)
            performance_pct = target.performance_pct if target else 100.0
            return commission.compute_progressive_commission(
                subtotal, performance_pct, is_crm_ok
            )
        return super()._get_commission_amount(commission, subtotal, product, quantity)
