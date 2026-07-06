from odoo import http
from odoo.http import request


class CustomerPortal(http.Controller):
    @http.route(
        ["/my/opportunities", "/my/opportunities/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def my_opportunities(self, page=1, **kw):
        partner = request.env.user.partner_id
        if partner.type_partner not in ("doctorint", "doctorext"):
            return request.redirect("/my")

        open_opportunities = request.env["crm.lead"].search(
            [
                ("doctor", "=", partner.id),
                ("type", "=", "opportunity"),
                ("probability", "<", 100),
            ],
            order="create_date desc",
        )

        commission_rate = partner.commission_id.fix_qty or 0.0

        stages = open_opportunities.mapped("stage_id").sorted("sequence")
        opportunities_by_stage = []
        total_opps = 0
        total_commission_val = 0.0
        summary_cards_html = ""
        for stage in stages:
            opps = open_opportunities.filtered(lambda l: l.stage_id == stage)
            stage_name = stage.sudo().name
            stage_count = len(opps)
            stage_commission = sum(
                opp.expected_revenue * (opp.commission_percent or commission_rate)
                / 100.0
                for opp in opps
            )
            total_opps += stage_count
            total_commission_val += stage_commission
            summary_cards_html += (
                '<div class="card" style="min-width:160px">'
                '<div class="card-body py-2 px-3 text-center">'
                '<div class="fw-bold small">%s</div>'
                "<div>"
                '<span class="badge bg-secondary">%d</span>'
                '<span class="ms-1 small">R$ %s</span>'
                "</div></div></div>"
                % (stage_name, stage_count, "{:,.2f}".format(stage_commission))
            )
            opportunity_data = [
                {
                    "id": opp.id,
                    "name": opp.name,
                    "partner_name": opp.sudo().partner_id.name or "-",
                    "date_str": opp.create_date.strftime("%d/%m/%Y")
                    if opp.create_date
                    else "-",
                    "referred_names": ", ".join(
                        opp.sudo().referred_partner.mapped("name")
                    )
                    or "-",
                    "expected_revenue_fmt": "{:,.2f}".format(opp.expected_revenue or 0.0),
                    "commission_fmt": "{:,.2f}".format(
                        opp.expected_revenue
                        * (opp.commission_percent or commission_rate)
                        / 100.0
                    ),
                    "url": "/my/opportunity/%d" % opp.id,
                }
                for opp in opps
            ]
            opportunities_by_stage.append(
                {
                    "stage_name": stage_name,
                    "count": stage_count,
                    "data": opportunity_data,
                }
            )

        total_card_html = (
            '<div class="card border-primary" style="min-width:160px">'
            '<div class="card-body py-2 px-3 text-center bg-primary text-white">'
            '<div class="fw-bold small">Total</div>'
            "<div>"
            '<span class="badge bg-light text-primary">%d</span>'
            '<span class="ms-1 small fw-bold">R$ %s</span>'
            "</div></div></div>"
            % (total_opps, "{:,.2f}".format(total_commission_val))
        )

        accordion_html = ""
        for group in opportunities_by_stage:
            rows = ""
            for d in group["data"]:
                rows += (
                    "<tr>"
                    '<td><a href="%s">%s</a></td>'
                    "<td>%s</td><td>%s</td><td>%s</td>"
                    "<td>R$ %s</td><td>R$ %s</td>"
                    "</tr>"
                    % (
                        d["url"],
                        d["name"],
                        d["partner_name"],
                        d["date_str"],
                        d["referred_names"],
                        d["expected_revenue_fmt"],
                        d["commission_fmt"],
                    )
                )
            accordion_html += (
                '<details class="mb-3" style="cursor:pointer">'
                '<summary class="fw-bold py-2 px-3 bg-light rounded">'
                "%s"
                '<span class="badge bg-secondary ms-2">%d</span>'
                "</summary>"
                '<table class="table table-striped mb-0 mt-2">'
                "<thead><tr>"
                "<th>Oportunidade</th><th>Paciente</th>"
                "<th>Data da Indica\u00e7\u00e3o</th><th>Indica\u00e7\u00e3o</th>"
                "<th>Expectativa</th><th>Repasse</th>"
                "</tr></thead><tbody>%s</tbody></table></details>"
                % (group["stage_name"], group["count"], rows)
            )

        commissions = request.env["commission.settlement"].search(
            [("agent_id", "=", partner.id)],
            order="date_from desc",
        )

        settlement_data = []
        for settlement in commissions:
            info = {
                "settlement": settlement,
                "lines": [],
            }
            for line in settlement.line_ids:
                order_name = ""
                invoice_state = ""
                payment_state = ""
                agent_line = line.invoice_agent_line_id
                if agent_line:
                    inv_line = agent_line.invoice_line_id
                    if inv_line and inv_line.move_id:
                        invoice_state = inv_line.move_id.state
                        payment_state = inv_line.move_id.payment_state
                        order_name = inv_line.move_id.invoice_origin or ""
                info["lines"].append(
                    {
                        "line": line,
                        "order_name": order_name,
                        "invoice_state": invoice_state,
                        "payment_state": payment_state,
                    }
                )
            settlement_data.append(info)

        return request.render(
            "crm_commissions.portal_my_opportunities_list",
            {
                "open_opportunities": open_opportunities,
                "summary_cards_html": summary_cards_html,
                "total_card_html": total_card_html,
                "accordion_html": accordion_html,
                "settlements": settlement_data,
            },
        )

    @http.route(
        ["/my/opportunity/<int:lead_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def my_opportunity_detail(self, lead_id, **kw):
        partner = request.env.user.partner_id
        if partner.type_partner not in ("doctorint", "doctorext"):
            return request.redirect("/my")
        lead = request.env["crm.lead"].browse(lead_id)
        if lead.doctor.id != partner.id:
            return request.redirect("/my")
        return request.render(
            "crm_commissions.portal_my_opportunity_detail",
            {"lead": lead},
        )
