from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import http
from odoo.http import request


def _fmt(val):
    return "R$ {:,.2f}".format(val or 0.0)


class CommissionDashboard(http.Controller):
    @http.route(
        "/dashboard/commission",
        type="http",
        auth="user",
        website=True,
    )
    def commission_dashboard(self):
        partner = request.env.user.partner_id
        today = date.today()
        month_start = today.replace(day=1)
        next_month = month_start + relativedelta(months=1)

        current_target = request.env["crm.commission.target"].search(
            [
                ("agent_id", "=", partner.id),
                ("target_date", ">=", month_start),
                ("target_date", "<", next_month),
            ],
            limit=1,
        )

        targets_quarter = request.env["crm.commission.target"].search(
            [
                ("agent_id", "=", partner.id),
                ("target_date", ">=", month_start),
                ("target_date", "<", month_start + relativedelta(months=3)),
            ]
        )
        quarterly_total_target = sum(targets_quarter.mapped("target_amount"))
        quarterly_total_achieved = sum(targets_quarter.mapped("achieved_amount"))
        quarterly_pct = (
            (quarterly_total_achieved / quarterly_total_target * 100)
            if quarterly_total_target
            else 0.0
        )

        sdr_partner_ids = partner.sdr_agent_ids.ids
        domain_leads = [("type", "=", "opportunity"), ("probability", "<", 100)]
        if sdr_partner_ids:
            domain_leads += [("user_id.partner_id", "in", sdr_partner_ids)]
        else:
            domain_leads += [("user_id", "=", request.env.user.id)]
        open_leads = request.env["crm.lead"].search(
            domain_leads,
            order="probability desc, expected_revenue desc",
        )

        pipeline_total = sum(
            lead.expected_revenue * (lead.probability / 100.0) for lead in open_leads
        )
        rate = partner.commission_id.fix_qty or 0.0
        estimated_pipeline_commission = pipeline_total * (rate / 100.0)

        domain_orders = [
            ("state", "in", ["sale", "done"]),
            ("date_order", ">=", month_start),
            ("date_order", "<", next_month),
        ]
        if sdr_partner_ids:
            domain_orders += [("opportunity_id.user_id.partner_id", "in", sdr_partner_ids)]
        else:
            domain_orders += [("user_id", "=", request.env.user.id)]
        recent_orders = request.env["sale.order"].search(domain_orders)
        current_commission_total = sum(
            recent_orders.mapped("order_line.agent_ids")
            .filtered(lambda line: line.agent_id.id == partner.id)
            .mapped("amount")
        )

        settlements = request.env["commission.settlement"].search(
            [("agent_id", "=", partner.id)],
            order="date_from desc",
            limit=10,
        )

        pending_total = sum(s.total for s in settlements if s.state == "settled")
        invoiced_total = sum(s.total for s in settlements if s.state == "invoiced")

        quarterly_bonus = request.env["crm.commission.quarterly.bonus"].search(
            [
                ("agent_id", "=", partner.id),
                ("state", "!=", "lost"),
            ],
            limit=5,
        )

        target_amount = current_target and current_target.target_amount or 0.0
        achieved_amount = current_target and current_target.achieved_amount or 0.0

        settlement_data = []
        for s in settlements:
            settlement_data.append(
                {
                    "date_from": s.date_from,
                    "date_to": s.date_to,
                    "total_fmt": _fmt(s.total),
                    "state": s.state,
                }
            )

        lead_data = []
        for lead in open_leads:
            weighted = lead.expected_revenue * lead.probability / 100.0
            lead_data.append(
                {
                    "name": lead.name,
                    "partner_name": lead.sudo().partner_id.name or "-",
                    "expected_revenue_fmt": _fmt(lead.expected_revenue),
                    "probability": lead.probability,
                    "weighted_fmt": _fmt(weighted),
                    "stage_name": lead.stage_id.sudo().name,
                }
            )

        # Invoiced / Uninvoiced breakdown
        domain_invoiced = domain_orders + [("invoice_status", "=", "invoiced")]
        invoiced_month_orders = request.env["sale.order"].search(domain_invoiced)
        invoiced_month_total = sum(invoiced_month_orders.mapped("amount_total"))
        invoiced_month_count = len(invoiced_month_orders)

        domain_uninvoiced = domain_orders + [("invoice_status", "=", "to invoice")]
        uninvoiced_month_orders = request.env["sale.order"].search(domain_uninvoiced)
        uninvoiced_month_total = sum(uninvoiced_month_orders.mapped("amount_total"))
        uninvoiced_month_count = len(uninvoiced_month_orders)

        order_data = []
        for order in recent_orders:
            order_data.append(
                {
                    "name": order.name,
                    "partner_name": order.sudo().partner_id.name,
                    "date_order": order.date_order,
                    "amount_total_fmt": _fmt(order.amount_total),
                    "commission_total_fmt": _fmt(order.commission_total),
                    "state": order.state,
                    "invoice_status": order.invoice_status,
                }
            )

        invoiced_order_data = []
        for order in invoiced_month_orders:
            invoiced_order_data.append(
                {
                    "name": order.name,
                    "partner_name": order.sudo().partner_id.name,
                    "date_order": order.date_order,
                    "amount_total_fmt": _fmt(order.amount_total),
                }
            )

        uninvoiced_order_data = []
        for order in uninvoiced_month_orders:
            uninvoiced_order_data.append(
                {
                    "name": order.name,
                    "partner_name": order.sudo().partner_id.name,
                    "date_order": order.date_order,
                    "amount_total_fmt": _fmt(order.amount_total),
                }
            )

        return request.render(
            "crm_commissions.commission_dashboard",
            {
                "partner": partner,
                "current_target": current_target,
                "target_amount_fmt": _fmt(target_amount),
                "achieved_amount_fmt": _fmt(achieved_amount),
                "gap_fmt": _fmt(max(0, target_amount - achieved_amount)),
                "current_commission_total_fmt": _fmt(current_commission_total),
                "pending_total_fmt": _fmt(pending_total),
                "invoiced_total_fmt": _fmt(invoiced_total),
                "quarterly_total_target_fmt": _fmt(quarterly_total_target),
                "quarterly_total_achieved_fmt": _fmt(quarterly_total_achieved),
                "quarterly_pct": quarterly_pct,
                "lead_data": lead_data,
                "pipeline_total_fmt": _fmt(pipeline_total),
                "estimated_pipeline_commission_fmt": _fmt(estimated_pipeline_commission),
                "order_data": order_data,
                "settlement_data": settlement_data,
                "quarterly_bonus": quarterly_bonus,
                "invoiced_month_total_fmt": _fmt(invoiced_month_total),
                "invoiced_month_count": invoiced_month_count,
                "uninvoiced_month_total_fmt": _fmt(uninvoiced_month_total),
                "uninvoiced_month_count": uninvoiced_month_count,
                "invoiced_order_data": invoiced_order_data,
                "uninvoiced_order_data": uninvoiced_order_data,
            },
        )
