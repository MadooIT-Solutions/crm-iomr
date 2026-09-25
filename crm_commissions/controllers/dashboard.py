# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date, datetime, time

import pytz
from dateutil.relativedelta import relativedelta

from odoo import fields, http
from odoo.http import request
from odoo.tools import format_date

_DASHBOARD_GROUPS = (
    "crm_commissions.group_crm_commission_user",
    "crm_commissions.group_crm_commission_manager",
    "crm_commissions.group_crm_commission_orientadora",
    "crm_commissions.group_crm_commission_sdr",
    "sales_team.group_sale_salesman",
    "sales_team.group_sale_manager",
)
_INVOICED_STATUSES = frozenset({"invoiced", "upselling"})
_UNINVOICED_STATUSES = frozenset({"to invoice", "no"})
_SETTLEMENT_ROWS_LIMIT = 10


def _fmt(value):
    return f"R$ {value or 0.0:,.2f}"


def _pct(value):
    return f"{value or 0.0:.1f}"


def _dashboard_user_allowed(env):
    """Return whether the current user may open the commission dashboard."""
    return any(env.user.has_group(group_xmlid) for group_xmlid in _DASHBOARD_GROUPS)


def _parse_dashboard_period(env, params, today):
    """Return an inclusive period and a user-facing validation message.

    With no parameters, the dashboard defaults to the current month. When only
    one boundary is supplied, its containing month supplies the other boundary.
    Invalid input falls back to the current month instead of failing the page.
    """
    month_start = today.replace(day=1)
    month_end = month_start + relativedelta(months=1, days=-1)
    raw_date_from = params.get("date_from")
    raw_date_to = params.get("date_to")
    error = False

    date_from = month_start
    if raw_date_from:
        try:
            date_from = date.fromisoformat(raw_date_from)
        except (TypeError, ValueError):
            error = env._("Data inicial inválida; foi aplicado o mês atual.")

    date_to = month_end
    if raw_date_to:
        try:
            date_to = date.fromisoformat(raw_date_to)
        except (TypeError, ValueError):
            error = env._("Data final inválida; foi aplicado o mês atual.")

    if error:
        return month_start, month_end, error

    if raw_date_from and not raw_date_to:
        date_to = date_from.replace(day=1) + relativedelta(months=1, days=-1)
    elif not raw_date_from and raw_date_to:
        date_from = date_to.replace(day=1)

    if date_from > date_to:
        error = env._(
            "A data inicial não pode ser posterior à data final; "
            "foi aplicado o mês atual."
        )
        return month_start, month_end, error
    return date_from, date_to, error


def _is_invoiced_status(invoice_status):
    return invoice_status in _INVOICED_STATUSES


def _is_uninvoiced_status(invoice_status):
    return invoice_status in _UNINVOICED_STATUSES


def _agent_commissions_by_order(orders, partner):
    """Return only the commission amount assigned to ``partner`` on each order."""
    amounts = {}
    for order in orders:
        agent_lines = order.order_line.agent_ids.filtered(
            lambda line_agent: line_agent.agent_id == partner
        )
        amounts[order.id] = sum(agent_lines.mapped("amount"))
    return amounts


def _estimate_lead_commission(env, lead, commission, performance_pct):
    """Estimate the commission of one opportunity at its current probability.

    An opportunity-specific percentage always wins. Otherwise progressive
    policies reuse the same calculator as the commission lines, including the
    IS-CRM bonus or penalty and evaluates the policy at 100% when no target
    is present in the selected period.
    """
    probability_factor = lead.probability / 100.0
    if lead.commission_percent:
        return (
            lead.expected_revenue * probability_factor * lead.commission_percent / 100.0
        )
    if commission and commission.commission_type == "coordinator":
        policy = (
            env["commission.policy"]
            .sudo()
            .search([("active", "=", True)], order="date_start desc", limit=1)
        )
        rate = policy.coordinator_rate if policy else 0.0
        return lead.expected_revenue * probability_factor * rate / 100.0
    if commission and commission.commission_type == "progressive":
        base_commission = commission.compute_progressive_commission(
            lead.expected_revenue,
            performance_pct,
            lead.is_crm_score >= 95.0,
        )
        return base_commission * probability_factor
    rate = commission.fix_qty if commission else 0.0
    return lead.expected_revenue * probability_factor * rate / 100.0


def _get_company_quarterly_totals(env, bonus):
    """Return quarterly totals restricted to the current company."""
    targets = bonus.monthly_targets.filtered(
        lambda target: target.company_id == env.company
    )
    total_target = sum(targets.mapped("target_amount"))
    total_achieved = sum(targets.mapped("achieved_amount"))
    quarterly_pct = total_achieved / total_target * 100.0 if total_target else 0.0
    return total_target, total_achieved, quarterly_pct


def _get_datetime_period_bounds(env, date_from, date_to):
    """Return UTC-naive bounds for an inclusive local-date period."""
    local_start = datetime.combine(date_from, time.min)
    local_end_exclusive = datetime.combine(date_to + relativedelta(days=1), time.min)
    timezone_name = env.context.get("tz") or env.user.tz
    if not timezone_name:
        return local_start, local_end_exclusive

    try:
        user_timezone = pytz.timezone(timezone_name)
    except pytz.UnknownTimeZoneError:
        return local_start, local_end_exclusive

    utc_start = user_timezone.localize(local_start).astimezone(pytz.utc)
    utc_end = user_timezone.localize(local_end_exclusive).astimezone(pytz.utc)
    return utc_start.replace(tzinfo=None), utc_end.replace(tzinfo=None)


def _serialize_order(env, order, partner_commission):
    return {
        "name": order.name,
        "partner_name": order.partner_id.name or "-",
        "date_order": order.date_order,
        "date_order_fmt": format_date(
            env, fields.Datetime.context_timestamp(order, order.date_order).date()
        ),
        "amount_total_fmt": _fmt(order.amount_total),
        "commission_total_fmt": _fmt(partner_commission),
        "state": order.state,
        "invoice_status": order.invoice_status,
    }


def get_dashboard_values(env, date_from, date_to):
    """Build the dashboard data for one user and one inclusive date period."""
    partner = env.user.partner_id
    datetime_from, datetime_to_exclusive = _get_datetime_period_bounds(
        env, date_from, date_to
    )

    # Monthly targets are stored on the first day of their month. Include every
    # month touched by the selected interval, even when its boundary is mid-month.
    target_month_start = date_from.replace(day=1)
    target_month_end = date_to.replace(day=1) + relativedelta(months=1)
    targets = (
        env["crm.commission.target"]
        .sudo()
        .search(
            [
                ("agent_id", "=", partner.id),
                ("company_id", "=", env.company.id),
                ("target_date", ">=", target_month_start),
                ("target_date", "<", target_month_end),
            ],
            order="target_date",
        )
    )
    target_amount = sum(targets.mapped("target_amount"))
    achieved_amount = sum(targets.mapped("achieved_amount"))
    target_pct = achieved_amount / target_amount * 100.0 if target_amount else 0.0

    # SDRs only see their own opportunities. Only Orientadoras may see the
    # opportunities of the SDRs linked to them.
    lead_owner_ids = [partner.id]
    is_sdr = env.user.has_group("crm_commissions.group_crm_commission_sdr")
    is_orientadora = env.user.has_group(
        "crm_commissions.group_crm_commission_orientadora"
    ) or (partner.type_partner == "orientadora" and not is_sdr)
    if is_orientadora:
        lead_owner_ids.extend(partner.sudo().sdr_agent_ids.ids)
    open_leads = (
        env["crm.lead"]
        .sudo()
        .search(
            [
                ("type", "=", "opportunity"),
                ("company_id", "=", env.company.id),
                ("active", "=", True),
                ("probability", ">", 0),
                ("probability", "<", 100),
                ("date_open", ">=", datetime_from),
                ("date_open", "<", datetime_to_exclusive),
                ("user_id.partner_id", "in", lead_owner_ids),
            ],
            order="probability desc, expected_revenue desc, id desc",
        )
    )
    pipeline_total = sum(
        lead.expected_revenue * (lead.probability / 100.0) for lead in open_leads
    )
    commission = partner.sudo().commission_id
    pipeline_performance_pct = target_pct if targets else 100.0
    estimated_pipeline_commission = sum(
        _estimate_lead_commission(env, lead, commission, pipeline_performance_pct)
        for lead in open_leads
    )

    # A person sees an order when they are an agent on at least one of its lines.
    # This intentionally includes partial-agent orders and orders assigned to a
    # different salesperson.
    recent_orders = (
        env["sale.order"]
        .sudo()
        .search(
            [
                ("state", "in", ["sale", "done"]),
                ("company_id", "=", env.company.id),
                ("date_order", ">=", datetime_from),
                ("date_order", "<", datetime_to_exclusive),
                ("order_line.agent_ids.agent_id", "=", partner.id),
            ],
            order="date_order desc, id desc",
        )
    )
    commissions_by_order = _agent_commissions_by_order(recent_orders, partner)
    current_commission_total = sum(commissions_by_order.values())

    invoiced_orders = recent_orders.filtered(
        lambda order: _is_invoiced_status(order.invoice_status)
    )
    uninvoiced_orders = recent_orders.filtered(
        lambda order: _is_uninvoiced_status(order.invoice_status)
    )
    invoiced_total = sum(invoiced_orders.mapped("amount_total"))
    uninvoiced_total = sum(uninvoiced_orders.mapped("amount_total"))

    settlements = (
        env["commission.settlement"]
        .sudo()
        .search(
            [
                ("agent_id", "=", partner.id),
                ("company_id", "=", env.company.id),
                ("date_from", "<=", date_to),
                ("date_to", ">=", date_from),
            ],
            order="date_from desc, id desc",
        )
    )
    repasse_settlements = settlements.filtered(
        lambda settlement: settlement.settlement_type != "crm_performance"
    )
    performance_settlements = settlements - repasse_settlements
    pending_total = sum(
        settlement.total
        for settlement in repasse_settlements
        if settlement.state == "settled"
    )
    invoiced_settlements_total = sum(
        settlement.total
        for settlement in repasse_settlements
        if settlement.state == "invoiced"
    )
    performance_settlements_total = sum(
        settlement.total
        for settlement in performance_settlements
        if settlement.state != "cancel"
    )
    invoice_exception_total = sum(
        settlement.total
        for settlement in repasse_settlements
        if settlement.state == "except_invoice"
    )

    quarterly_bonuses = (
        env["crm.commission.quarterly.bonus"]
        .sudo()
        .search(
            [
                ("agent_id", "=", partner.id),
                ("date_from", "<=", date_to),
                ("date_to", ">=", date_from),
            ],
            order="year desc, quarter desc",
        )
    )
    quarterly_bonus_totals = {
        bonus.id: _get_company_quarterly_totals(env, bonus)
        for bonus in quarterly_bonuses
    }
    quarterly_total_target = sum(
        totals[0] for totals in quarterly_bonus_totals.values()
    )
    quarterly_total_achieved = sum(
        totals[1] for totals in quarterly_bonus_totals.values()
    )
    quarterly_pct = (
        quarterly_total_achieved / quarterly_total_target * 100.0
        if quarterly_total_target
        else 0.0
    )

    settlement_data = []
    for settlement in repasse_settlements[:_SETTLEMENT_ROWS_LIMIT]:
        settlement_data.append(
            {
                "date_from": settlement.date_from,
                "date_to": settlement.date_to,
                "date_from_fmt": format_date(env, settlement.date_from),
                "date_to_fmt": format_date(env, settlement.date_to),
                "total_fmt": _fmt(settlement.total),
                "state": settlement.state,
            }
        )

    lead_data = []
    for lead in open_leads:
        weighted = lead.expected_revenue * lead.probability / 100.0
        lead_data.append(
            {
                "name": lead.name,
                "partner_name": lead.partner_id.name or "-",
                "expected_revenue_fmt": _fmt(lead.expected_revenue),
                "probability": lead.probability,
                "weighted_fmt": _fmt(weighted),
                "stage_name": lead.stage_id.name,
            }
        )

    order_data = [
        _serialize_order(env, order, commissions_by_order[order.id])
        for order in recent_orders
    ]
    invoiced_order_data = [
        _serialize_order(env, order, commissions_by_order[order.id])
        for order in invoiced_orders
    ]
    uninvoiced_order_data = [
        _serialize_order(env, order, commissions_by_order[order.id])
        for order in uninvoiced_orders
    ]
    quarterly_bonus_data = [
        {
            "name": bonus.name,
            "quarterly_pct": quarterly_bonus_totals[bonus.id][2],
            "recovered_amount_fmt": _fmt(bonus.lost_commission_recovered),
            "bonus_amount_fmt": _fmt(bonus.bonus_amount),
            "state": bonus.state,
        }
        for bonus in quarterly_bonuses
    ]

    return {
        "partner": partner,
        "date_from": date_from,
        "date_to": date_to,
        "date_from_str": date_from.isoformat(),
        "date_to_str": date_to.isoformat(),
        "date_from_fmt": format_date(env, date_from),
        "date_to_fmt": format_date(env, date_to),
        "has_targets": bool(targets),
        "target_amount": target_amount,
        "target_amount_fmt": _fmt(target_amount),
        "achieved_amount": achieved_amount,
        "achieved_amount_fmt": _fmt(achieved_amount),
        "target_pct": target_pct,
        "target_pct_fmt": _pct(target_pct),
        "gap_fmt": _fmt(max(0.0, target_amount - achieved_amount)),
        "current_commission_total": current_commission_total,
        "current_commission_total_fmt": _fmt(current_commission_total),
        "pending_total": pending_total,
        "pending_total_fmt": _fmt(pending_total),
        "invoiced_settlements_total": invoiced_settlements_total,
        "invoiced_settlements_total_fmt": _fmt(invoiced_settlements_total),
        "performance_settlements_total": performance_settlements_total,
        "performance_settlements_total_fmt": _fmt(performance_settlements_total),
        "invoice_exception_total": invoice_exception_total,
        "invoice_exception_total_fmt": _fmt(invoice_exception_total),
        "settlement_count": len(repasse_settlements),
        "settlement_data": settlement_data,
        "quarterly_total_target": quarterly_total_target,
        "quarterly_total_target_fmt": _fmt(quarterly_total_target),
        "quarterly_total_achieved": quarterly_total_achieved,
        "quarterly_total_achieved_fmt": _fmt(quarterly_total_achieved),
        "quarterly_pct": quarterly_pct,
        "quarterly_pct_fmt": _pct(quarterly_pct),
        "quarterly_bonus_data": quarterly_bonus_data,
        "pipeline_total": pipeline_total,
        "pipeline_total_fmt": _fmt(pipeline_total),
        "estimated_pipeline_commission": estimated_pipeline_commission,
        "estimated_pipeline_commission_fmt": _fmt(estimated_pipeline_commission),
        "lead_data": lead_data,
        "order_count": len(recent_orders),
        "order_data": order_data,
        "invoiced_total": invoiced_total,
        "invoiced_count": len(invoiced_orders),
        "invoiced_total_fmt": _fmt(invoiced_total),
        "invoiced_order_data": invoiced_order_data,
        "uninvoiced_total": uninvoiced_total,
        "uninvoiced_count": len(uninvoiced_orders),
        "uninvoiced_total_fmt": _fmt(uninvoiced_total),
        "uninvoiced_order_data": uninvoiced_order_data,
    }


class CommissionDashboard(http.Controller):
    @http.route(
        "/dashboard/commission",
        type="http",
        auth="user",
        website=True,
    )
    def commission_dashboard(self, **kwargs):
        if not _dashboard_user_allowed(request.env):
            return request.not_found()
        date_from, date_to, date_error = _parse_dashboard_period(
            request.env,
            kwargs,
            fields.Date.context_today(request.env.user),
        )
        values = get_dashboard_values(request.env, date_from, date_to)
        values["date_error"] = date_error
        return request.render("crm_commissions.commission_dashboard", values)
