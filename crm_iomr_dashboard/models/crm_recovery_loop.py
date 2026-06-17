from datetime import timedelta

from odoo import fields, models


class CrmRecoveryLoop(models.Model):
    _name = "crm.recovery.loop"
    _description = "Loop de Recuperação de Leads"
    _rec_name = "lead_id"

    lead_id = fields.Many2one("crm.lead", string="Lead Original", required=True)
    lost_date = fields.Date(string="Data da Perda")
    recovery_start_date = fields.Date(string="Início da Recuperação")
    recovered_date = fields.Date(string="Data da Recuperação")
    recovered_value = fields.Monetary(
        string="Valor Recuperado", currency_field="currency_id"
    )
    state = fields.Selection(
        [
            ("draft", "Aguardando 30 Dias"),
            ("active", "Em Recuperação"),
            ("recovered", "Recuperado"),
            ("failed", "Perda Definitiva"),
        ],
        default="draft",
        string="Status",
    )

    recovery_value = fields.Monetary(
        related="lead_id.expected_revenue",
        string="Valor em Recuperação",
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        "res.currency", related="lead_id.company_id.currency_id"
    )

    def check_leads_for_recovery(self):
        limit_date = fields.Date.today() - timedelta(days=30)
        lost_leads = self.env["crm.lead"].search(
            [
                ("active", "=", False),
                ("probability", "=", 0),
                ("date_closed", "<=", limit_date),
            ]
        )
        for lead in lost_leads:
            exists = self.search([("lead_id", "=", lead.id)])
            if not exists:
                self.create(
                    {
                        "lead_id": lead.id,
                        "lost_date": fields.Date.to_date(
                            lead.date_closed or lead.write_date
                        ),
                        "recovery_start_date": fields.Date.today(),
                        "state": "active",
                    }
                )

    def action_mark_recovered(self):
        self.ensure_one()
        lead = self.lead_id
        self.write(
            {
                "state": "recovered",
                "recovered_date": fields.Date.today(),
                "recovered_value": lead.expected_revenue
                if lead.probability == 100
                else 0,
            }
        )

    def action_mark_failed(self):
        self.write({"state": "failed"})
