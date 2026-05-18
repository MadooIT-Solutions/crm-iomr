from odoo import models, fields, api


class CrmIomrSnapshot(models.Model):
    _name = 'crm.iomr.snapshot'
    _description = 'Snapshot Semanal de KPIs CRM'
    _order = 'date desc'

    date = fields.Date(string="Data do Snapshot", default=fields.Date.context_today)
    total_weighted_forecast = fields.Monetary(string="Total Forecast Ponderado", currency_field='currency_id')
    avg_ticket = fields.Monetary(string="Ticket Médio", currency_field='currency_id')
    avg_roi = fields.Float(string="ROI Médio (%)")
    total_surgeries_value = fields.Monetary(string="Valor Total Cirurgias", currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string="Moeda", default=lambda self: self.env.company.currency_id)

    def action_generate_weekly_snapshot(self):
        leads = self.env['crm.lead'].search([('active', '=', True)])
        won_leads = self.env['crm.lead'].search([('probability', '=', 100)])

        total_forecast = sum(leads.mapped('weighted_forecast'))
        total_revenue = sum(won_leads.mapped('expected_revenue'))
        qty_won = len(won_leads) or 1
        avg_ticket = total_revenue / qty_won

        surgeries = leads.filtered(lambda l: l.is_surgery)
        total_surgeries = sum(surgeries.mapped('surgery_value'))

        self.create({
            'date': fields.Date.today(),
            'total_weighted_forecast': total_forecast,
            'avg_ticket': avg_ticket,
            'total_surgeries_value': total_surgeries,
        })