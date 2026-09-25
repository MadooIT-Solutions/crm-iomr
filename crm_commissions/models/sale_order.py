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

    # ------------------------------------------------------------------
    # Sync commission.sale from sale.order
    # ------------------------------------------------------------------
    def _action_confirm(self):
        res = super()._action_confirm()
        self._sync_commission_sales_from_orders()
        self._refresh_crm_commission_targets()
        return res

    def _action_cancel(self):
        res = super()._action_cancel()
        sales = self.env["commission.sale"].sudo().search(
            [("source_order_id", "in", self.ids)]
        )
        sales.write({"status": "cancelled"})
        self._refresh_crm_commission_targets()
        return res

    def _get_crm_commission_agents(self):
        """Orientadoras that identify this order as their achievement."""
        return self.mapped("partner_id.agent_ids") | self.mapped(
            "order_line.agent_ids.agent_id"
        )

    def _refresh_crm_commission_targets(self):
        agent_ids = self._get_crm_commission_agents().ids
        if not agent_ids:
            return
        targets = self.env["crm.commission.target"].sudo().search([
            ("target_scope", "=", "salesperson"),
            ("agent_id", "in", agent_ids),
        ])
        targets._refresh_from_sale_changes()

    def write(self, vals):
        tracked_fields = {
            "partner_id",
            "date_order",
            "state",
            "amount_total",
            "order_line",
        }
        old_agents = (
            self._get_crm_commission_agents()
            if tracked_fields.intersection(vals)
            else self.env["res.partner"]
        )
        result = super().write(vals)
        if tracked_fields.intersection(vals):
            affected_agents = old_agents | self._get_crm_commission_agents()
            if affected_agents:
                targets = self.env["crm.commission.target"].sudo().search([
                    ("target_scope", "=", "salesperson"),
                    ("agent_id", "in", affected_agents.ids),
                ])
                targets._refresh_from_sale_changes()
        return result

    def unlink(self):
        old_agents = self._get_crm_commission_agents()
        result = super().unlink()
        if old_agents:
            targets = self.env["crm.commission.target"].sudo().search([
                ("target_scope", "=", "salesperson"),
                ("agent_id", "in", old_agents.ids),
            ])
            targets._refresh_from_sale_changes()
        return result

    def _get_commission_orientadora_members(self):
        """Orientadora members whose partner appears as an agent on the order.

        Runs in superuser context: this is internal bookkeeping and must never
        break order confirmation for users without commission ACLs (plain
        salespeople, orientadoras read-only on commission.*, etc.).
        """
        order = self.sudo()
        partner_ids = set()
        for line in order.order_line.filtered(lambda l: not l.display_type):
            for agent in line.agent_ids:
                if agent.agent_id.type_partner == "orientadora":
                    partner_ids.add(agent.agent_id.id)
        if not partner_ids:
            return self.env["commission.member"]
        return self.env["commission.member"].sudo().search([
            ("member_type", "=", "orientadora"),
            ("partner_id", "in", list(partner_ids)),
        ])

    def _sync_commission_sales_from_orders(self):
        """Create/update one commission.sale per orientadora member and order.

        Idempotent: (member, order) is unique on commission.sale.
        Runs with sudo() because internal bookkeeping must not be blocked by
        the orientadora record rule (read-only on commission.sale).
        """
        for order in self:
            for member in order._get_commission_orientadora_members():
                order._sync_commission_sale_for_member(member)

    def _sync_commission_sale_for_member(self, member):
        self.ensure_one()
        order = self.sudo()
        Sale = self.env["commission.sale"].sudo()
        existing = Sale.search([
            ("owner_member_id", "=", member.id),
            ("source_order_id", "=", order.id),
        ], limit=1)
        vals = order._prepare_commission_sale_vals(member.sudo())
        if existing:
            existing.line_ids.unlink()
            existing.write(vals)
        else:
            vals.update({
                "owner_member_id": member.id,
                "source_order_id": order.id,
            })
            Sale.create(vals)

    def _prepare_commission_sale_vals(self, member):
        """Approximate mapping from this order to a commission.sale record."""
        self.ensure_one()
        line_vals = []
        medical_fee_total = 0.0
        lio_package_total = 0.0
        joined_names = ""
        for line in self.order_line.filtered(lambda l: not l.display_type):
            if not line.product_id:
                continue
            joined = " ".join(
                self._get_product_category_names(line.product_id.categ_id)
            ).upper()
            joined_names += " " + joined
            if "LIO" in joined:
                line_type = "lio_package"
                lio_package_total += line.price_subtotal
            elif line._product_in_excluded_commission_categ():
                line_type = "medical_fee"
                medical_fee_total += line.price_subtotal
            else:
                line_type = "hospital"
            if not any(
                agent.agent_id.id == member.partner_id.id
                for agent in line.agent_ids
            ):
                continue
            line_vals.append((0, 0, {
                "line_type": line_type,
                "amount": line.price_subtotal,
            }))

        is_lens_sale = "LENTE" in joined_names and "LIO" not in joined_names
        lens_type = False
        if is_lens_sale:
            lens_type = "rigid" if "RIGID" in joined_names else "gelatinous"

        convenio = getattr(self, "convenio", False)
        if convenio:
            sale_category = (
                "saude_todos"
                if "saude" in (convenio.name or "").lower()
                else "convenio"
            )
        else:
            sale_category = "particular"

        return {
            "name": self.name,
            "date": (
                self.date_order.date()
                if self.date_order
                else fields.Date.context_today(self)
            ),
            "patient_name": (
                self.partner_id.name
                or self.partner_shipping_id.name
                or "/"
            ),
            "surgery_type": self._detect_surgery_type(joined_names),
            "sale_category": sale_category,
            "status": (
                "invoiced" if self.invoice_status == "invoiced" else "confirmed"
            ),
            "hospital_gross_amount": self.amount_total,
            "medical_fee_amount": medical_fee_total,
            "lio_package_amount": lio_package_total,
            "crm_pct": self.is_crm_score or 100.0,
            "discount_approved": self.discount_approved or False,
            "is_lens_sale": is_lens_sale,
            "lens_type": lens_type,
            "notes": "Sincronizado automaticamente a partir do pedido %s." % self.name,
            "line_ids": line_vals,
        }

    def _get_product_category_names(self, categ):
        names = []
        while categ:
            names.append(categ.name or "")
            categ = categ.parent_id
        return names

    def _detect_surgery_type(self, joined_names):
        for value, key in (
            ("catarata", "CATARATA"),
            ("refrativa", "REFRA"),
            ("glaucoma", "GLAUCO"),
            ("vitrectomia", "VITREC"),
        ):
            if key in joined_names:
                return value
        return "outros"


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.depends("order_id.partner_id", "order_id.doctor_id", "order_id.user_id")
    def _compute_agent_ids(self):
        self.agent_ids = False
        for record in self:
            if record.order_id.partner_id and not record.commission_free:
                is_excluded_categ = record._product_in_excluded_commission_categ()
                vals = record._prepare_agents_vals_partner(
                    record.order_id.partner_id, settlement_type="sale_invoice"
                )
                if is_excluded_categ:
                    vals = [
                        v for v in vals
                        if len(v) < 3
                        or self.env["res.partner"].browse(
                            v[2].get("agent_id")
                        ).type_partner not in ("orientadora", "sdr")
                    ]
                salesperson = record.order_id.user_id.partner_id
                if (
                    salesperson
                    and salesperson.agent
                    and salesperson.salesman_as_agent
                    and not (
                        is_excluded_categ
                        and salesperson.type_partner in ("orientadora", "sdr")
                    )
                    and not any(
                        len(v) >= 3 and v[2].get("agent_id") == salesperson.id
                        for v in vals
                    )
                ):
                    vals.append((0, 0, record._prepare_agent_vals(salesperson)))
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
                if sdr_partner and not is_excluded_categ:
                    vals = record._apply_sdr_commission_split(vals, sdr_partner)
                vals = [v for v in vals if len(v) < 3 or v[2].get("commission_id")]
                record.agent_ids = record._add_coordinator_agents(
                    record._apply_agent_category_rules(vals, record.product_id)
                )

    def _get_coordinator_commission(self):
        commission = self.env.ref(
            "crm_commissions.commission_coordinator_policy",
            raise_if_not_found=False,
        )
        if not commission:
            commission = self.env["commission"].search(
                [("commission_type", "=", "coordinator")], limit=1
            )
        return commission

    def _add_coordinator_agents(self, agent_vals):
        """Mirror the orientadora's commission lines to her coordinator.

        The coordinator receives commission (via the active policy rate) on
        the same items where the orientadora receives commission.
        """
        result = list(agent_vals)
        coordinator_comm = self._get_coordinator_commission()
        if not coordinator_comm:
            return result
        present_agents = {
            v[2].get("agent_id") for v in result if len(v) >= 3
        }
        for val in result:
            if len(val) < 3:
                continue
            agent = self.env["res.partner"].browse(val[2].get("agent_id"))
            coordinator = agent.coordenadora_id
            if (
                agent.type_partner == "orientadora"
                and coordinator
                and coordinator.id not in present_agents
            ):
                result.append(
                    (0, 0, {
                        "agent_id": coordinator.id,
                        "commission_id": coordinator_comm.id,
                        "commission_split_percent": 100.0,
                    })
                )
                present_agents.add(coordinator.id)
        return result

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

    def _product_in_excluded_commission_categ(self):
        if not self.product_id or not self.product_id.categ_id:
            return False
        excluded = set(self._get_excluded_orientadora_categ_ids())
        if not excluded:
            return False
        return any(cid in excluded for cid in self._get_product_category_ids(self.product_id))

    @api.model
    def _get_excluded_orientadora_categ_ids(self):
        cats = self.env["product.category"].search(
            ["|", ("name", "ilike", "HONORARIO"), ("name", "ilike", "PROCEDIMENTO")]
        )
        all_ids = set()
        for cat in cats:
            all_ids.update(
                self.env["product.category"].search(
                    [("id", "child_of", cat.id)]
                ).ids
            )
        return list(all_ids)

    def _apply_agent_category_rules(self, vals, product):
        if not product or not product.categ_id or not vals:
            return vals
        result = []
        categ_ids = self._get_product_category_ids(product)
        excluded_categ_ids = set(self._get_excluded_orientadora_categ_ids())
        for val in vals:
            if len(val) < 3:
                result.append(val)
                continue
            agent_id = val[2].get("agent_id")
            comm_id = val[2].get("commission_id")
            if not agent_id or not comm_id:
                result.append(val)
                continue
            agent = self.env["res.partner"].browse(agent_id)
            if (
                agent.type_partner in ("orientadora", "sdr")
                and excluded_categ_ids
                and any(cid in excluded_categ_ids for cid in categ_ids)
            ):
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
