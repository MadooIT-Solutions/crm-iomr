from odoo import models, fields, api


class CrmProductivitySla(models.Model):
    _name = 'crm.productivity.sla'
    _description = 'Análise de Produtividade e SLA'
    _rec_name = 'user_id'
    _order = 'create_date desc'

    user_id = fields.Many2one('res.users', string="Vendedor/SDR")
    period = fields.Char(string="Período")
    avg_response_time = fields.Float(string="Tempo Médio Resposta (h)")
    conversion_rate = fields.Float(string="Taxa Conversão MQL->SQL (%)")
    overdue_activities_count = fields.Integer(string="Atividades em Atraso")

    def update_productivity_metrics(self):
        today = fields.Date.today()
        current_period = today.strftime('%m/%Y')
        users = self.env['res.users'].search([('share', '=', False)])

        for user in users:
            leads = self.env['crm.lead'].search([('user_id', '=', user.id)])
            sql_leads = leads.filtered(lambda l: l.is_sql)

            conv_rate = (len(sql_leads) / len(leads) * 100) if leads else 0
            avg_resp = sum(leads.mapped('response_time_hours')) / (len(leads) or 1)

            overdue = self.env['mail.activity'].search_count([
                ('user_id', '=', user.id),
                ('date_deadline', '<', today),
            ])

            existing = self.search([
                ('user_id', '=', user.id),
                ('period', '=', current_period),
            ])
            if existing:
                existing.write({
                    'avg_response_time': avg_resp,
                    'conversion_rate': conv_rate,
                    'overdue_activities_count': overdue,
                })
            else:
                self.create({
                    'user_id': user.id,
                    'period': current_period,
                    'avg_response_time': avg_resp,
                    'conversion_rate': conv_rate,
                    'overdue_activities_count': overdue,
                })