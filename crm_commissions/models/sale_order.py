# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_SDR_COMMISSION_PCT = 25.0


class SaleOrder(models.Model):
    _inherit = "sale.order"

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


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.depends("order_id.partner_id", "order_id.doctor_id")
    def _compute_agent_ids(self):
        self.agent_ids = False
        for record in self:
            if record.order_id.partner_id and not record.commission_free:
                vals = record._prepare_agents_vals_partner(
                    record.order_id.partner_id, settlement_type="sale_invoice"
                )
                if record.order_id.doctor_id:
                    doctor = record.order_id.doctor_id
                    if doctor.agent and doctor.commission_id:
                        referring_doctors = record.order_id.referred_partner.filtered(
                            lambda p: p.agent and p.commission_id and p.id != doctor.id
                        )
                        if referring_doctors:
                            doctor_vals = record._prepare_agent_vals(doctor)
                            doctor_vals["commission_split_percent"] = 50.0
                            if not any(
                                v[2].get("agent_id") == doctor.id
                                for v in vals if len(v) >= 3
                            ):
                                vals.append((0, 0, doctor_vals))
                            for ref_doc in referring_doctors:
                                ref_vals = record._prepare_agent_vals(ref_doc)
                                ref_vals["commission_split_percent"] = 50.0
                                if not any(
                                    v[2].get("agent_id") == ref_doc.id
                                    for v in vals if len(v) >= 3
                                ):
                                    vals.append((0, 0, ref_vals))
                        else:
                            doctor_already = any(
                                v[2].get("agent_id") == doctor.id
                                for v in vals
                                if len(v) >= 3
                            )
                            if not doctor_already:
                                vals.append(
                                    (0, 0, record._prepare_agent_vals(doctor))
                                )
                sdr_partner = (
                    record.order_id.opportunity_id
                    and record.order_id.opportunity_id._get_sdr_partner_from_rotation()
                )
                if sdr_partner:
                    vals = record._apply_sdr_commission_split(vals, sdr_partner)
                record.agent_ids = record._apply_agent_category_rules(
                    vals, record.product_id
                )

    def _apply_sdr_commission_split(self, vals, sdr_partner):
        """Split the orientadora's commission when the opportunity passed
        through an SDR.

        The SDR receives _SDR_COMMISSION_PCT (25%) of the orientadora's
        commission and the orientadora keeps the remaining 75%.
        """
        if not sdr_partner or not sdr_partner.agent:
            return vals
        if any(
            len(v) >= 3 and v[2].get("agent_id") == sdr_partner.id
            for v in vals
        ):
            return vals
        orientadora_vals = [
            v
            for v in vals
            if len(v) >= 3
            and v[2].get("agent_id")
            and (
                self.env["res.partner"]
                .browse(v[2]["agent_id"])
                .type_partner
                == "orientadora"
            )
        ]
        if not orientadora_vals:
            return vals
        for v in orientadora_vals:
            v[2]["commission_split_percent"] = 100.0 - _SDR_COMMISSION_PCT
        sdr_vals = self._prepare_agent_vals(sdr_partner)
        sdr_vals["commission_id"] = orientadora_vals[0][2]["commission_id"]
        sdr_vals["commission_split_percent"] = _SDR_COMMISSION_PCT
        vals.append((0, 0, sdr_vals))
        return vals

    def _get_product_category_ids(self, product):
        categ_ids = set()
        categ = product.categ_id
        while categ:
            categ_ids.add(categ.id)
            categ = categ.parent_id
        return list(categ_ids)

    def _apply_agent_category_rules(self, vals, product):
        if not product or not product.categ_id or not vals:
            return vals
        result = []
        categ_ids = self._get_product_category_ids(product)
        for val in vals:
            if len(val) < 3:
                result.append(val)
                continue
            agent_id = val[2].get("agent_id")
            comm_id = val[2].get("commission_id")
            if not agent_id or not comm_id:
                result.append(val)
                continue
            rule = self.env["commission.agent.rule"].search(
                [
                    ("agent_id", "=", agent_id),
                    ("categ_ids", "in", categ_ids),
                ],
                order="sequence",
                limit=1,
            )
            if rule:
                val[2]["commission_id"] = rule.commission_id.id
            commission = self.env["commission"].browse(val[2]["commission_id"])
            if commission.categ_ids:
                commission_categ_ids = set(commission.categ_ids.ids)
                if not any(cid in commission_categ_ids for cid in categ_ids):
                    continue
            if commission.commission_type == "product":
                if not self._has_commission_item_for_product(commission, product):
                    continue
            result.append(val)
        return result

    def _has_commission_item_for_product(self, commission, product):
        categ_ids = set()
        categ = product.categ_id
        while categ:
            categ_ids.add(categ.id)
            categ = categ.parent_id
        return bool(self.env["commission.item"].search([
            ("commission_id", "=", commission.id),
            "|",
            ("product_tmpl_id", "=", False),
            ("product_tmpl_id", "=", product.product_tmpl_id.id),
            "|",
            ("product_id", "=", False),
            ("product_id", "=", product.id),
            "|",
            ("categ_id", "=", False),
            ("categ_id", "in", list(categ_ids)),
        ], limit=1))

    def _prepare_invoice_line(self, **optional_values):
        vals = super()._prepare_invoice_line(**optional_values)
        vals["agent_ids"] = [
            (0, 0, {
                "agent_id": x.agent_id.id,
                "commission_id": x.commission_id.id,
                "commission_split_percent": x.commission_split_percent,
            })
            for x in self.agent_ids
        ]
        return vals


class SaleOrderLineAgent(models.Model):
    _inherit = "sale.order.line.agent"

    @api.depends(
        "commission_id",
        "object_id.price_subtotal",
        "object_id.product_id",
        "object_id.product_uom_qty",
    )
    def _compute_amount(self):
        super()._compute_amount()
        for line in self:
            if line.commission_split_percent:
                line.amount *= line.commission_split_percent / 100.0
