# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

# ``sale_credit_card_fee`` (and its l10n_br flavour) bill the card
# administrator fee as an invoice line of a service product. Two xmlids,
# because either module may be the installed one.
CARD_FEE_PRODUCT_XMLIDS = (
    "sale_credit_card_fee.product_credit_card_fee",
    "l10n_br_sale_credit_card_fee.product_credit_card_fee",
)


class CommissionMixin(models.AbstractModel):
    _inherit = "commission.mixin"

    @api.model
    def _get_card_fee_product_ids(self):
        """Ids of the products that bill the card administrator fee.

        ``sale_credit_card_fee`` writes its fee onto the invoice as a plain
        service product, which is indistinguishable from a real sale. The
        fee is a cost the clinic pays the acquirer, and the repasse rule
        treats it as such: it is *deducted* from the commission base
        (``deduct_card_fee``), never paid out to an agent. Without this
        list the customer agents earn commission on the very fee that
        was discounted from their base.
        """
        products = self.env["product.product"].browse()
        for xmlid in CARD_FEE_PRODUCT_XMLIDS:
            product = self.env.ref(xmlid, raise_if_not_found=False)
            if product:
                products |= product
        return products.ids

    def _is_card_fee_line(self):
        self.ensure_one()
        return (
            bool(self.product_id)
            and self.product_id.id in self._get_card_fee_product_ids()
        )


class CommissionLineMixin(models.AbstractModel):
    _inherit = "commission.line.mixin"

    commission_split_percent = fields.Float(
        string="Commission Split (%)",
        default=100.0,
    )

    def _get_source_sale_order(self):
        """The sale order behind this commission line, when there is one.

        A sale line carries it directly; an invoice line reaches it through
        the sale lines the invoice was generated from.
        """
        self.ensure_one()
        source_line = self.object_id
        order = getattr(source_line, "order_id", False)
        if order:
            return order
        sale_lines = getattr(source_line, "sale_line_ids", False)
        return sale_lines[:1].order_id if sale_lines else False

    def _can_change_split(self):
        """Whether the split of this row may be rewritten.

        An invoice line held by a settlement is a closed accounting fact --
        OCA raises "You can't modify a settled line" on it -- so it is left
        alone and reported instead of being silently changed.
        """
        return True

    def _apply_medical_split_rule(self):
        """Force the split between the order's doctor and the one that
        indicated the patient.

        ``commission_split_percent`` is a rule output and not a free value:
        the order's doctor (``doctor_id``) and the doctors that referred to
        them (``referred_partner``) share the line evenly, so the usual case
        of a single indication is the 50/50 rule.

        A row reaches its line from three directions -- rebuilt by
        ``_compute_agent_ids``, copied from the customer's agents, or typed in
        by hand on the form -- and each of them used to be able to leave the
        two doctors on the 100% default, paying the whole amount twice. It
        runs when the row is created, when it is written and when the order
        is saved, and it is a no-op once the split already matches.
        """
        splits = {}
        for agent_line in self:
            order = agent_line._get_source_sale_order()
            if not order:
                continue
            medical_parties = order._get_medical_commission_parties()
            if len(medical_parties) < 2:
                continue
            splits[agent_line.object_id] = (
                medical_parties,
                100.0 / len(medical_parties),
            )
        for line, (medical_parties, split_percent) in splits.items():
            to_fix = line.agent_ids.filtered(
                lambda agent_line, parties=medical_parties, percent=split_percent: (
                    agent_line.agent_id in parties
                    and agent_line.commission_split_percent != percent
                )
            )
            to_fix = to_fix.filtered(lambda agent_line: agent_line._can_change_split())
            if to_fix:
                to_fix.write({"commission_split_percent": split_percent})

    def _get_product_category_ids(self, product):
        categ_ids = set()
        categ = product.categ_id
        while categ:
            categ_ids.add(categ.id)
            categ = categ.parent_id
        return list(categ_ids)

    def _get_card_fee_amount(self):
        """Return this line's share of the order's card administrator fee.

        The deduction follows the fee **actually charged**, not its rate:
        ``credit_card_fee_amount`` is the sum of the order's
        ``sale.order.credit.card.fee.line`` amounts, which is what the
        acquirer really billed. That matters because the fee lines are
        editable -- a user may set a fee amount by hand and the module
        rebalances only the remaining lines, so ``fee_percent x base`` no
        longer reconstructs the fee that was collected.

        The fee is an order-level cost, so it is spread over the lines by
        price weight rather than charged to each of them in full. Weighting by
        ``price_total`` is the same base ``sale_credit_card_fee`` charges the
        fee on, so the shares add up to exactly the fee collected.

        Earlier this was read as ``credit_card_fee_percent``, a ``fields.Char``
        holding a formatted, comma-joined string (e.g. ``'2.99'``) for display.
        Multiplying that by a float raised
        ``TypeError: can't multiply sequence by non-int of type 'float'``,
        breaking the commission computation -- and with it the write that
        triggered it -- on every order carrying a card fee.
        """
        self.ensure_one()
        order = self._get_source_sale_order()
        if not order:
            return 0.0
        total_fee = order.credit_card_fee_amount
        if not total_fee:
            return 0.0
        order_gross = sum(order.order_line.mapped("price_total"))
        if not order_gross:
            return 0.0
        line_gross = getattr(self.object_id, "price_total", 0.0) or 0.0
        return total_fee * line_gross / order_gross

    def _get_line_gross_amount(self, subtotal):
        """Return what the patient is actually charged for this line.

        ``price_total`` is the price plus the taxes Odoo computed for the
        line, which is the very base ``sale_credit_card_fee`` charges the
        card fee on (``order.amount_untaxed + order.amount_tax`` is the
        sum of the lines' ``price_total``). Falling back to ``subtotal``
        keeps the calculation working for lines with no price computed.
        """
        self.ensure_one()
        line = self.object_id
        return (getattr(line, "price_total", 0.0) or 0.0) or (subtotal or 0.0)

    def _get_line_tax_amount(self):
        """Return the taxes really charged on this line.

        Two ways a price can carry its taxes, and the deduction has to follow
        whichever one the clinic actually uses:

        * Taxes **added on top** -- ``price_total - price_subtotal`` is what
          Odoo computed from the line's own ``tax_ids``, so the deduction
          follows the product's real fiscal mix instead of a hard-coded
          percentage.
        * Taxes **already inside the price** -- the clinic's price list is
          tax-inclusive, and the Brazilian fiscal framework then maps ISSQN,
          PIS, COFINS, IRPJ and CSLL as ``tax_include`` taxes
          (``l10n_br_fiscal.tax_group.tax_include``), booking them in
          ``amount_tax_included`` with ``amount_tax_not_included`` left at
          zero. ``price_total`` is then equal to ``price_subtotal`` and the
          subtraction above is always ``0.00``: the taxes are in the price but
          invisible to it, and the repasse would be gross when it has to be
          net. ``amount_tax_included`` is the value that actually answers
          "how much tax is inside this price", so it is used for that case.

        An invoice line is the third case. ``amount_tax_included`` is a
        *related* field there, pointing at its move, so an invoice issued
        before the clinic had a fiscal operation carries no tax of its own
        and reads ``0.00`` -- while the sale lines it came from do carry it.
        The invoice is what the repasse is actually paid on, so without a
        fallback the same sale would be net on the order and gross on the
        invoice. The originating sale lines answer it instead, scaled by the
        share of them this line bills, so a partially invoiced line does not
        claim the whole tax.
        """
        self.ensure_one()
        line = self.object_id
        gross = getattr(line, "price_total", 0.0) or 0.0
        net = getattr(line, "price_subtotal", 0.0) or 0.0
        tax_on_top = max(0.0, gross - net)
        if tax_on_top:
            return tax_on_top
        included = max(0.0, getattr(line, "amount_tax_included", 0.0) or 0.0)
        if included:
            return included
        return self._get_source_line_tax_amount()

    def _get_source_line_tax_amount(self):
        """Return the embedded tax of the sale lines this line was billed from.

        Only an invoice line reaches this. The share is proportional to the
        price, and capped at the tax those sale lines really carry, so a line
        invoiced in part never deducts more tax than exists.
        """
        self.ensure_one()
        sale_lines = getattr(self.object_id, "sale_line_ids", None)
        if not sale_lines:
            return 0.0
        sale_net = sum(sale_lines.mapped("price_subtotal"))
        if not sale_net:
            return 0.0
        sale_tax = sum(sale_lines.mapped("amount_tax_included"))
        if not sale_tax:
            return 0.0
        line_net = getattr(self.object_id, "price_subtotal", 0.0) or 0.0
        return min(sale_tax, sale_tax * line_net / sale_net)

    def _get_deducted_base_amount(self, commission, subtotal):
        """Deduct the line's taxes and/or the card fee from the commission base.

        Follows the repasse rule ``[preço - impostos - taxa cartão]``, where
        ``preço`` is the amount charged to the patient, so the base becomes::

            base = gross                          # price_total
                 - impostos da linha               # _get_line_tax_amount()
                 - parte da taxa de cartão         # _get_card_fee_amount()
               = max(0, base)

        ``impostos da linha`` is ``_get_line_tax_amount()``: the tax added on
        top of the price when the price is tax-exclusive, the tax embedded in
        the price (``amount_tax_included``) when it is tax-inclusive, which is
        the clinic's case. ``taxa de cartão`` is this line's share of the
        order's ``credit_card_fee_amount`` -- the fee actually charged,
        spread over the lines by price weight.

        The taxes come from the line itself when ``deduct_taxes`` is set;
        otherwise the legacy fixed ``tax_deduction_pct`` is applied over the
        untaxed subtotal, which stays available for lines the fiscal framework
        cannot price.
        """
        self.ensure_one()
        gross = self._get_line_gross_amount(subtotal)
        base = gross
        if commission.deduct_taxes:
            base -= self._get_line_tax_amount()
        elif commission.tax_deduction_pct:
            base -= (subtotal or 0.0) * commission.tax_deduction_pct / 100.0
        if commission.deduct_card_fee:
            base -= self._get_card_fee_amount()
        return max(0.0, base)

    def _get_single_commission_amount(self, commission, subtotal, product, quantity):
        """Apply the net base to the 'Product criteria' policies as well.

        A ``commission_type == 'product'`` policy is rated straight from its
        ``commission.item`` rows by
        ``sale_commission_oca_product_criteria._get_single_commission_amount``,
        which is reached without ever going through
        ``_get_commission_amount``. So the ``net_amount_deduction`` base --
        the taxes and the card fee -- was never applied to it, no matter what
        ``deduct_taxes``/``deduct_card_fee`` said: those flags are read by
        ``_get_deducted_base_amount``, which that path skips. It is the
        largest policy in the clinic, so the rule has to be applied here too
        or the repasse would stay gross exactly where it matters most.

        Only the percentage items read the base; a fixed item is a flat amount
        that does not, and keeps its value.

        Its cost deduction is intentionally gone: that branch tests
        ``amount_base_type == 'net_amount'``, and moving the policy to
        ``net_amount_deduction`` is what the clinic asked for. ``quantity`` is
        passed on untouched so the items keep reading the real quantity.
        """
        self.ensure_one()
        if commission and commission.amount_base_type == "net_amount_deduction":
            subtotal = self._get_deducted_base_amount(commission, subtotal)
        return super()._get_single_commission_amount(
            commission, subtotal, product, quantity
        )

    def _get_commission_amount(self, commission, subtotal, product, quantity):
        self.ensure_one()
        if commission and commission.amount_base_type == "net_amount_deduction":
            subtotal = self._get_deducted_base_amount(commission, subtotal)
        if commission and commission.commission_type == "coordinator":
            policy = self.env["commission.policy"].search(
                [("active", "=", True)], order="date_start desc", limit=1
            )
            if policy:
                return subtotal * policy.coordinator_rate / 100.0
            return 0.0
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
