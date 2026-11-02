# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

# OCA uses these states to decide whether an invoice is already paid enough
# to settle its commission. ``in_payment`` is a registered payment still on
# its way to the bank; ``reversed`` is kept for refunds, matching the OCA
# ``_skip_settlement`` rule.
PAYMENT_STATES = ("in_payment", "paid", "reversed")


class AccountInvoiceLineAgent(models.Model):
    _inherit = "account.invoice.line.agent"

    payment_date = fields.Date(
        string="Payment Date",
        compute="_compute_payment_date",
        help="Date on which the invoice was paid. It is the date used to "
        "close payment-based commissions.",
    )

    @api.depends(
        "invoice_id.state",
        "invoice_id.payment_state",
        "invoice_id.line_ids.matched_debit_ids.max_date",
        "invoice_id.line_ids.matched_credit_ids.max_date",
    )
    def _compute_payment_date(self):
        for line in self:
            line.payment_date = line._get_payment_date()

    def _get_payment_date(self):
        """Return the date the invoice was actually paid.

        The date of the payment itself wins over the reconciliation date:
        ``account.partial.reconcile.max_date`` is the *latest* of the invoice
        and payment dates, so a payment made before the invoice date (an
        advance) would otherwise be reported as if it happened on the invoice
        date. When the invoice was settled by something other than an
        ``account.payment`` (a credit note, for example), the reconciliation
        date is the best available answer.
        """
        self.ensure_one()
        invoice = self.invoice_id
        if (
            not invoice
            or invoice.state != "posted"
            or invoice.payment_state not in PAYMENT_STATES
        ):
            return False
        payment_dates = [
            payment.date
            for payment in invoice.reconciled_payment_ids
            if payment.date
        ]
        if payment_dates:
            return max(payment_dates)
        partials = (
            invoice.line_ids.matched_debit_ids
            | invoice.line_ids.matched_credit_ids
        )
        partial_dates = [partial.max_date for partial in partials if partial.max_date]
        return max(partial_dates) if partial_dates else False

    def _skip_settlement(self):
        """Never settle an invoice commission before the invoice is paid.

        This is the hard business rule, independent from the per-commission
        ``invoice_state`` setting: the closing of invoice commissions follows
        the payment date, not the invoice date. It keeps old/misconfigured
        commissions from being closed when the patient has not paid yet.
        """
        self.ensure_one()
        if (
            self.invoice_id.state != "posted"
            or self.invoice_id.payment_state not in PAYMENT_STATES
        ):
            return True
        return super()._skip_settlement()

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
