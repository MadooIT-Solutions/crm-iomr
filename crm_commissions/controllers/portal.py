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
                ("doctor_id", "=", partner.id),
                ("type", "=", "opportunity"),
                ("probability", "<", 100),
            ],
            order="create_date desc",
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
        if lead.doctor_id.id != partner.id:
            return request.redirect("/my")
        return request.render(
            "crm_commissions.portal_my_opportunity_detail",
            {"lead": lead},
        )
