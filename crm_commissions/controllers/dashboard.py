from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import http
from odoo.http import request


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

        open_leads = request.env["crm.lead"].search(
            [
                ("orientadora_id", "=", partner.id),
                ("type", "=", "opportunity"),
                ("probability", "<", 100),
            ],
            order="probability desc, expected_revenue desc",
        )

        pipeline_total = sum(
            lead.expected_revenue * (lead.probability / 100.0) for lead in open_leads
        )
        rate = partner.commission_id.fix_qty or 0.0
        estimated_pipeline_commission = pipeline_total * (rate / 100.0)

        recent_orders = request.env["sale.order"].search(
            [
                ("orientadora_id", "=", partner.id),
                ("state", "in", ["sale", "done"]),
                ("date_order", ">=", month_start),
                ("date_order", "<", next_month),
            ]
        )
        current_commission_total = sum(recent_orders.mapped("commission_total"))

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

        return request.render(
            "crm_commissions.commission_dashboard",
            {
                "partner": partner,
                "current_target": current_target,
                "quarterly_total_target": quarterly_total_target,
                "quarterly_total_achieved": quarterly_total_achieved,
                "quarterly_pct": quarterly_pct,
                "open_leads": open_leads,
                "pipeline_total": pipeline_total,
                "estimated_pipeline_commission": estimated_pipeline_commission,
                "recent_orders": recent_orders,
                "current_commission_total": current_commission_total,
                "settlements": settlements,
                "pending_total": pending_total,
                "invoiced_total": invoiced_total,
                "quarterly_bonus": quarterly_bonus,
            },
        )
