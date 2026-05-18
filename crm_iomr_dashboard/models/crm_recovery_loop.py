from odoo import models, fields, api
from datetime import timedelta


class CrmRecoveryLoop(models.Model):
    _name = 'crm.recovery.loop'
    _description = 'Loop de Recuperação de Leads'

    lead_id = fields.Many2one('crm.lead', string="Lead Original", required=True)
    lost_date = fields.Date(string="Data da Perda")
    recovery_start_date = fields.Date(string="Início da Recuperação")
    state = fields.Selection([
        ('draft', 'Aguardando 30 Dias'),
        ('active', 'Em Recuperação'),
        ('recovered', 'Recuperado'),
        ('failed', 'Perda Definitiva')
    ], default='draft', string="Status")

    recovery_value = fields.Monetary(related='lead_id.expected_revenue', string="Valor em Recuperação",
                                     currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='lead_id.company_id.currency_id')

    def check_leads_for_recovery(self):
        limit_date = fields.Date.today() - timedelta(days=30)
        lost_leads = self.env['crm.lead'].search([
            ('active', '=', False),
            ('probability', '=', 0),
            ('write_date', '<=', limit_date)
        ])
        for lead in lost_leads:
            exists = self.search([('lead_id', '=', lead.id)])
            if not exists:
                self.create({
                    'lead_id': lead.id,
                    'lost_date': lead.write_date.date(),
                    'recovery_start_date': fields.Date.today(),
                    'state': 'active'
                })