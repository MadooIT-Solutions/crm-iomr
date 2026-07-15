import os
from datetime import date, timedelta

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

        show_all = partner.show_all_values
        today = date.today()
        date_from = kw.get("date_from")
        date_to = kw.get("date_to")
        if not date_from:
            date_from = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        if not date_to:
            date_to = today.strftime("%Y-%m-%d")

        domain_open = [
            ("doctor", "=", partner.id),
            ("type", "=", "opportunity"),
            ("probability", ">", 0),
            ("probability", "<", 100),
        ]
        if date_from:
            domain_open.append(("create_date", ">=", date_from + " 00:00:00"))
        if date_to:
            domain_open.append(("create_date", "<=", date_to + " 23:59:59"))

        open_opportunities = request.env["crm.lead"].search(
            domain_open, order="create_date desc",
        )

        domain_lost = [
            ("doctor", "=", partner.id),
            ("type", "=", "opportunity"),
            ("probability", "=", 0),
        ]
        if date_from:
            domain_lost.append(("create_date", ">=", date_from + " 00:00:00"))
        if date_to:
            domain_lost.append(("create_date", "<=", date_to + " 23:59:59"))

        lost_opportunities = request.env["crm.lead"].with_context(active_test=False).search(
            domain_lost, order="create_date desc",
        )

        commission_rate = partner.commission_id.fix_qty or 0.0

        follow_up = request.env["crm.stage"].search([("name", "=", "Follow-up")], limit=1)
        negociacao = request.env["crm.stage"].search([("name", "=", "Negociação")], limit=1)
        wanted_stages = [s for s in (follow_up, negociacao) if s]
        wanted_stages.sort(key=lambda s: s.sequence)

        opportunities_by_stage = []
        total_opps = 0
        total_commission_val = 0.0
        summary_cards_html = ""
        for stage in wanted_stages:
            opps = open_opportunities.filtered(lambda l, s=stage: l.stage_id == s)
            stage_name = stage.sudo().name
            stage_count = len(opps)
            stage_commission = sum(
                opp.expected_revenue * (opp.commission_percent or commission_rate)
                / 100.0
                for opp in opps
            )
            total_opps += stage_count
            total_commission_val += stage_commission
            stage_commission_fmt = "{:,.2f}".format(stage_commission)
            card_html = (
                '<div class="card o_portal_commission_card" style="min-width:160px">'
                '<div class="card-body py-3 px-3 text-center" style="background-color:#8EBAA6;border-radius:12px">'
                '<div class="fw-bold small text-uppercase mb-1" style="color:#ffffff">'
                + stage_name
                + '</div>'
                "<div>"
                '<span class="badge me-1" style="background:rgba(255,255,255,0.2);color:#ffffff">'
                + str(stage_count)
            )
            if show_all:
                card_html += (
                    '</span>'
                    '<span class="ms-1 small fw-bold" style="color:#ffffff">R$ '
                    + stage_commission_fmt
                )
            card_html += "</span></div></div></div>"
            summary_cards_html += card_html

            opportunity_data = [
                {
                    "id": opp.id,
                    "name": opp.name,
                    "stage_name": stage_name,
                    "partner_name": opp.sudo().partner_id.name or "-",
                    "email_from": opp.email_from or "",
                    "phone": opp.phone or "",
                    "mobile": opp.mobile or "",
                    "date_str": opp.create_date.strftime("%d/%m/%Y")
                    if opp.create_date
                    else "-",
                    "referred_names": ", ".join(
                        opp.sudo().referred_partner.mapped("name")
                    )
                    or "-",
                    "expected_revenue_fmt": "{:,.2f}".format(opp.expected_revenue or 0.0) if show_all else "",
                    "commission_fmt": "{:,.2f}".format(
                        opp.expected_revenue
                        * (opp.commission_percent or commission_rate)
                        / 100.0
                    ) if show_all else "",
                    "probability": opp.probability or 0,
                    "priority": opp.priority or "",
                    "date_deadline": opp.date_deadline.strftime("%d/%m/%Y")
                    if opp.date_deadline
                    else "",
                    "user_name": opp.user_id.sudo().name or "",
                    "team_name": opp.team_id.sudo().name or "",
                    "source_name": opp.source_id.sudo().name or "",
                    "campaign_name": opp.campaign_id.sudo().name or "",
                    "tag_names": ", ".join(opp.sudo().tag_ids.mapped("name")) or "",
                    "street": opp.street or "",
                    "street2": opp.street2 or "",
                    "city": opp.city or "",
                    "state_name": opp.state_id.sudo().name or "",
                    "zip": opp.zip or "",
                    "create_date": opp.create_date.strftime("%d/%m/%Y %H:%M")
                    if opp.create_date
                    else "",
                    "date_open": opp.date_open.strftime("%d/%m/%Y")
                    if opp.date_open
                    else "",
                    "commission_percent": opp.commission_percent or 0,
                    "discount_percent": opp.discount_percent or 0,
                    "margin_percent": opp.margin_percent or 0,
                    "is_crm_score": opp.is_crm_score or 0,
                    "description": opp.description or "",
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

        total_commission_fmt = "{:,.2f}".format(total_commission_val) if show_all else ""
        total_card_html = (
            '<div class="card o_portal_commission_card" style="min-width:160px">'
            '<div class="card-body py-3 px-3 text-center" style="background-color:#8EBAA6;border-radius:12px">'
            '<div class="fw-bold small text-uppercase mb-1" style="color:#ffffff">Total</div>'
            "<div>"
            '<span class="badge me-1" style="background:rgba(255,255,255,0.2);color:#ffffff">'
            + str(total_opps)
        )
        if show_all:
            total_card_html += (
                '</span>'
                '<span class="ms-1 small fw-bold" style="color:#ffffff">R$ '
                + total_commission_fmt
            )
        total_card_html += "</span></div></div></div>"

        accordion_html = ""
        for group in opportunities_by_stage:
            rows = ""
            for d in group["data"]:
                if show_all:
                    rows += (
                        "<tr>"
                        "<td>%s</td>"
                        "<td>%s</td><td>%s</td><td>%s</td>"
                        "<td>R$ %s</td><td>R$ %s</td>"
                        "</tr>"
                        % (
                            d["name"],
                            d["partner_name"],
                            d["date_str"],
                            d["referred_names"],
                            d["expected_revenue_fmt"],
                            d["commission_fmt"],
                        )
                    )
                else:
                    rows += (
                        "<tr>"
                        "<td>%s</td>"
                        "<td>%s</td><td>%s</td><td>%s</td>"
                        "</tr>"
                        % (
                            d["name"],
                            d["partner_name"],
                            d["date_str"],
                            d["referred_names"],
                        )
                    )
            headers = "<th>Oportunidade</th><th>Paciente</th><th>Data da Indica\u00e7\u00e3o</th><th>Indica\u00e7\u00e3o</th>"
            if show_all:
                headers += "<th>Expectativa</th><th>Repasse</th>"
            accordion_html += (
                '<details class="mb-3" style="cursor:pointer">'
                '<summary class="fw-bold py-2 px-3" style="background-color:#8EBAA6;color:#ffffff;border-radius:8px;font-size:12px;text-transform:uppercase;letter-spacing:0.5px">'
                "%s"
                '<span class="badge ms-2" style="background-color:#6A6D70;color:#ffffff">%d</span>'
                "</summary>"
                '<table class="table table-striped mb-0 mt-2">'
                "<thead><tr>%s</tr></thead><tbody>%s</tbody></table></details>"
                % (group["stage_name"], group["count"], headers, rows)
            )

        commissions = request.env["commission.settlement"].sudo().search(
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

        settled_order_names = set()
        for s in settlement_data:
            for line_data in s["lines"]:
                if line_data["order_name"]:
                    for name in line_data["order_name"].split(", "):
                        settled_order_names.add(name.strip())

        pending_agents = request.env["sale.order.line.agent"].sudo().search([
            ("agent_id", "=", partner.id),
            ("object_id.order_id.state", "=", "sale"),
        ])

        pending_data = []
        pending_by_order = {}
        for agent_line in pending_agents:
            order = agent_line.object_id.order_id
            if order.name in settled_order_names:
                continue
            order_id = order.id
            opportunity = order.opportunity_id
            if order_id not in pending_by_order:
                pending_by_order[order_id] = {
                    "order_name": order.name,
                    "partner_name": order.sudo().partner_id.name or "-",
                    "order_date": order.date_order.strftime("%d/%m/%Y") if order.date_order else "",
                    "opportunity_name": opportunity.name if opportunity else "-",
                    "referred_names": ", ".join(
                        order.sudo().referred_partner.mapped("name")
                    ) or "-",
                    "amount": 0.0,
                }
            pending_by_order[order_id]["amount"] += agent_line.amount or 0.0
        for vals in pending_by_order.values():
            vals["amount_fmt"] = "{:,.2f}".format(vals["amount"])
            pending_data.append(vals)

        uninvoiced_orders = request.env["sale.order"].search([
            ("doctor_id", "=", partner.id),
            ("state", "=", "sale"),
            ("invoice_status", "=", "to invoice"),
        ], order="date_order desc")

        uninvoiced_orders_data = []
        for order in uninvoiced_orders:
            opportunity = order.opportunity_id
            comm_pct = (
                opportunity.commission_percent
                if opportunity and opportunity.commission_percent
                else commission_rate
            )
            uninvoiced_orders_data.append({
                "order_name": order.name,
                "partner_name": order.sudo().partner_id.name or "-",
                "order_date": order.date_order.strftime("%d/%m/%Y") if order.date_order else "",
                "opportunity_name": opportunity.name if opportunity else "-",
                "commission_fmt": "{:,.2f}".format(
                    (order.amount_total or 0.0) * comm_pct / 100.0
                ),
            })

        ganhos_total = 0.0
        faturado_total = 0.0
        nao_faturado_total = 0.0
        for s in settlement_data:
            state = s["settlement"].state
            for line_data in s["lines"]:
                val = line_data["line"].settled_amount or 0.0
                if state != "cancel":
                    ganhos_total += val
                if line_data["invoice_state"] == "posted":
                    faturado_total += val
                elif state not in ("cancel",):
                    nao_faturado_total += val

        for pd in pending_data:
            amt = pd["amount"] or 0.0
            ganhos_total += amt
            nao_faturado_total += amt

        ganhos_total_fmt = "{:,.2f}".format(ganhos_total) if show_all else ""
        faturado_total_fmt = "{:,.2f}".format(faturado_total) if show_all else ""
        nao_faturado_total_fmt = "{:,.2f}".format(nao_faturado_total) if show_all else ""

        lost_data = []
        for opp in lost_opportunities:
            lost_data.append({
                "name": opp.name,
                "partner_name": opp.sudo().partner_id.name or "-",
                "date_str": opp.create_date.strftime("%d/%m/%Y")
                if opp.create_date
                else "-",
                "referred_names": ", ".join(
                    opp.sudo().referred_partner.mapped("name")
                )
                or "-",
                "expected_revenue_fmt": "{:,.2f}".format(opp.expected_revenue or 0.0) if show_all else "",
                "lost_reason": opp.lost_reason_id.sudo().name or "-",
            })

        return request.render(
            "crm_commissions.portal_my_opportunities_list",
            {
                "open_opportunities": open_opportunities,
                "summary_cards_html": summary_cards_html,
                "total_card_html": total_card_html,
                "accordion_html": accordion_html,
                "settlements": settlement_data,
                "pending_data": pending_data,
                "uninvoiced_orders_data": uninvoiced_orders_data,
                "ganhos_total_fmt": ganhos_total_fmt,
                "faturado_total_fmt": faturado_total_fmt,
                "nao_faturado_total_fmt": nao_faturado_total_fmt,
                "lost_data": lost_data,
                "show_all_values": show_all,
                "date_from": date_from,
                "date_to": date_to,
            },
        )

    @http.route(
        ["/my/opportunity/<int:lead_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def my_opportunity_detail(self, lead_id, **kw):
        return request.redirect("/my/opportunities")

    @http.route(
        ["/my/repasse-rules"],
        type="http",
        auth="user",
        website=True,
    )
    def repasse_rules(self, **kw):
        groups = [
            {
                "name": "Consulta",
                "rows": [
                    {"tipo": "Honorário", "convenio": "Particular", "repasse": "60%", "base": "Receita Líquida", "equacao": "[preço consulta - impostos - taxa cartão] x 60%", "obs": "Taxa cartão varia conforme forma de pgto. Impostos: 16,33%"},
                    {"tipo": "Honorário", "convenio": "Convênios", "repasse": "60%", "base": "Receita Líquida", "equacao": "[preço consulta - impostos] x 60%", "obs": "Impostos: 16,33%"},
                    {"tipo": "Honorário", "convenio": "Unimed*", "repasse": "60%", "base": "Receita Líquida", "equacao": "[preço consulta - impostos - taxas] x 60%", "obs": "Impostos: 27,5% | Taxas: 2,50%"},
                    {"tipo": "Honorário", "convenio": "Humana", "repasse": "R$ 35,00", "base": "Valor Fixo", "equacao": "Não se aplica", "obs": "-"},
                ],
            },
            {
                "name": "Exames realizados por médico",
                "rows": [
                    {"tipo": "Honorário + Taxa", "convenio": "Particular", "repasse": "50%", "base": "Receita Líquida", "equacao": "[preço exame - impostos - taxa cartão] x 50%", "obs": "Taxa cartão varia. Impostos: 11,73%"},
                    {"tipo": "Honorário + Taxa", "convenio": "Convênios", "repasse": "50%", "base": "Receita Líquida", "equacao": "[preço exame - impostos] x 50%", "obs": "Impostos: 11,73%"},
                    {"tipo": "Honorário + Taxa", "convenio": "Unimed*", "repasse": "50%", "base": "Receita Líquida", "equacao": "[preço exame - impostos - taxas] x 50%", "obs": "Impostos: 27,5% | Taxas: 2,50%"},
                    {"tipo": "Honorário + Taxa", "convenio": "Humana", "repasse": "Tabela", "base": "Tabela Humana", "equacao": "Não se aplica", "obs": "Baseada no valor líquido que o médico recebe da Unimed."},
                ],
            },
            {
                "name": "Exames realizados por técnico",
                "rows": [
                    {"tipo": "Honorário + Taxa", "convenio": "Particular", "repasse": "25%", "base": "Receita Líquida", "equacao": "[preço exame - impostos - taxa cartão] x 25%", "obs": "Taxa cartão varia. Impostos: 11,73%"},
                    {"tipo": "Honorário + Taxa", "convenio": "Convênios", "repasse": "25%", "base": "Receita Líquida", "equacao": "[preço exame - impostos] x 25%", "obs": "Impostos: 11,73%"},
                    {"tipo": "Honorário + Taxa", "convenio": "Unimed*", "repasse": "25%", "base": "Receita Líquida", "equacao": "[preço exame - impostos - taxas] x 25%", "obs": "Impostos: 27,5% | Taxas: 2,50%"},
                    {"tipo": "Honorário + Taxa", "convenio": "Humana", "repasse": "-", "base": "N/A", "equacao": "Não se aplica", "obs": "Não gera repasse."},
                ],
            },
            {
                "name": "Lente de contato",
                "rows": [
                    {"tipo": "Rígidas e Gelatinosas", "convenio": "Particular", "repasse": "20%", "base": "Receita Bruta", "equacao": "preço de venda da lente x 20%", "obs": "-"},
                ],
            },
            {
                "name": "Cirurgia (honorário)",
                "rows": [
                    {"tipo": "Honorário", "convenio": "Particular", "repasse": "100%", "base": "Receita Líquida", "equacao": "[preço honorário - impostos - taxa cartão] x 100%", "obs": "Taxa cartão varia. Impostos: 11,73%"},
                    {"tipo": "Honorário", "convenio": "Convênios", "repasse": "100%", "base": "Receita Líquida", "equacao": "[preço honorário - impostos] x 100%", "obs": "Impostos: 11,73%"},
                    {"tipo": "Honorário", "convenio": "Unimed", "repasse": "-", "base": "Receita Líquida", "equacao": "[preço honorário - impostos - taxas] x % de repasse", "obs": "-"},
                    {"tipo": "Honorário", "convenio": "Humana", "repasse": "Tabela", "base": "Tabela Humana", "equacao": "Não se aplica", "obs": "Baseada no valor líquido que o médico recebe da Unimed."},
                ],
            },
            {
                "name": "LIO (Lente Intraocular)",
                "rows": [
                    {"tipo": "Trifocal Tórica", "convenio": "Particular", "repasse": "R$ 1.900,00", "base": "Valor Fixo", "equacao": "N/A", "obs": "Desconto comercial também aplicado ao repasse."},
                    {"tipo": "Trifocal", "convenio": "Particular", "repasse": "R$ 1.700,00", "base": "Valor Fixo", "equacao": "N/A", "obs": ""},
                    {"tipo": "Foco Estendido Tórica", "convenio": "Particular", "repasse": "R$ 1.900,00", "base": "Valor Fixo", "equacao": "N/A", "obs": ""},
                    {"tipo": "Foco Estendido", "convenio": "Particular", "repasse": "R$ 1.700,00", "base": "Valor Fixo", "equacao": "N/A", "obs": ""},
                    {"tipo": "Monofocal Plus Tórica", "convenio": "Particular", "repasse": "R$ 1.400,00", "base": "Valor Fixo", "equacao": "N/A", "obs": ""},
                    {"tipo": "Monofocal Plus", "convenio": "Particular", "repasse": "R$ 1.400,00", "base": "Valor Fixo", "equacao": "N/A", "obs": ""},
                    {"tipo": "Bifocal", "convenio": "Particular", "repasse": "R$ 1.400,00", "base": "Valor Fixo", "equacao": "N/A", "obs": ""},
                    {"tipo": "Tórica", "convenio": "Particular", "repasse": "R$ 1.400,00", "base": "Valor Fixo", "equacao": "N/A", "obs": ""},
                    {"tipo": "Asférica", "convenio": "Particular", "repasse": "R$ 1.100,00", "base": "Valor Fixo", "equacao": "N/A", "obs": ""},
                    {"tipo": "Esférica", "convenio": "Particular", "repasse": "R$ 645,00", "base": "Valor Fixo", "equacao": "N/A", "obs": ""},
                    {"tipo": "SA60AT", "convenio": "Particular", "repasse": "R$ 250,00", "base": "Valor Fixo", "equacao": "N/A", "obs": ""},
                    {"tipo": "Una MFA5", "convenio": "Particular", "repasse": "R$ 180,00", "base": "Valor Fixo", "equacao": "N/A", "obs": ""},
                ],
            },
            {
                "name": "Cola Orgânica",
                "rows": [
                    {"tipo": "Cola Orgânica", "convenio": "Particular", "repasse": "R$ 200,00", "base": "Valor Fixo", "equacao": "N/A", "obs": ""},
                ],
            },
        ]

        return request.render(
            "crm_commissions.portal_repasse_rules",
            {"groups": groups},
        )

    @http.route(
        ["/my/repasse-rules/download"],
        type="http",
        auth="user",
        website=True,
    )
    def repasse_rules_download(self, **kw):
        partner = request.env.user.partner_id
        if partner.type_partner not in ("doctorint", "doctorext"):
            return request.redirect("/my")
        xlsx_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "..",
            "Regras de Repasse dos Médicos Sócios.xlsx",
        )
        if os.path.isfile(xlsx_path):
            with open(xlsx_path, "rb") as f:
                content = f.read()
            headers = [
                ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                ("Content-Disposition", "attachment; filename=Regras de Repasse dos Médicos Sócios.xlsx"),
                ("Content-Length", str(len(content))),
            ]
            return request.make_response(content, headers=headers)
        return request.redirect("/my/repasse-rules")
