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
            summary_cards_html += (
                '<div class="card o_portal_commission_card" style="min-width:160px">'
                '<div class="card-body py-3 px-3 text-center" style="background:linear-gradient(90deg, #A4D4C0 0%, #7EAE96 100%);border-radius:12px">'
                '<div class="fw-bold small text-uppercase mb-1" style="color:#ffffff">%s</div>'
                "<div>"
                '<span class="badge me-1" style="background:rgba(255,255,255,0.2);color:#ffffff">%d</span>'
                '<span class="ms-1 small fw-bold" style="color:#ffffff">R$ %s</span>'
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

        total_commission_fmt = "{:,.2f}".format(total_commission_val)
        total_card_html = (
            '<div class="card o_portal_commission_card" style="min-width:160px">'
            '<div class="card-body py-3 px-3 text-center" style="background:linear-gradient(90deg, #A4D4C0 0%, #7EAE96 100%);border-radius:12px">'
            '<div class="fw-bold small text-uppercase mb-1" style="color:#ffffff">Total</div>'
            "<div>"
            '<span class="badge me-1" style="background:rgba(255,255,255,0.2);color:#ffffff">'
            + str(total_opps)
            + '</span>'
            '<span class="ms-1 small fw-bold" style="color:#ffffff">R$ '
            + total_commission_fmt
            + "</span>"
            "</div></div></div>"
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
                '<summary class="fw-bold py-2 px-3" style="background-color:#3B5239;color:#ffffff;border-radius:8px;font-size:12px;text-transform:uppercase;letter-spacing:0.5px">'
                "%s"
                '<span class="badge ms-2" style="background-color:#6A6D70;color:#ffffff">%d</span>'
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
