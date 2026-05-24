from odoo import models, fields, api
from datetime import timedelta


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    # Forecast e Saúde Financeira
    weighted_forecast = fields.Monetary(string="Forecast Ponderado", currency_field='company_currency', compute="_compute_weighted_forecast", store=True)
    acquisition_cost = fields.Monetary(string="Custo de Aquisição", currency_field='company_currency')
    roi_value = fields.Float(string="ROI (%)", compute="_compute_roi", store=True)

    # Dados de Cirurgia (Manual)
    is_surgery = fields.Boolean(string="É Cirurgia?")
    surgery_type = fields.Selection([
        ('catarata', 'Catarata'),
        ('refrativa', 'Refrativa'),
        ('glaucoma', 'Glaucoma'),
        ('outros', 'Outros')
    ], string="Tipo de Cirurgia")
    surgery_value = fields.Monetary(string="Valor da Cirurgia", currency_field='company_currency')
    surgery_date = fields.Date(string="Data da Cirurgia")

    # Produtividade
    sdr_id = fields.Many2one('res.users', string="SDR Responsável")
    is_sql = fields.Boolean(string="Convertido em SQL", default=False)
    first_response_date = fields.Datetime(string="Primeira Resposta")
    response_time_hours = fields.Float(string="Tempo de Resposta (Horas)", compute="_compute_response_time", store=True)

    # Recovery Loop / Transferência entre OCs
    transferred_from_id = fields.Many2one('res.users', string="Transferido de (OC)", index=True)
    transferred_date = fields.Datetime(string="Data da Transferência")
    inactivity_days = fields.Integer(string="Dias Inativos Antes da Transferência", compute="_compute_inactivity_days", store=True)

    @api.depends('expected_revenue', 'probability')
    def _compute_weighted_forecast(self):
        for lead in self:
            lead.weighted_forecast = (lead.expected_revenue * lead.probability) / 100

    @api.depends('expected_revenue', 'acquisition_cost')
    def _compute_roi(self):
        for lead in self:
            if lead.acquisition_cost > 0:
                lead.roi_value = ((lead.expected_revenue - lead.acquisition_cost) / lead.acquisition_cost) * 100
            else:
                lead.roi_value = 0.0

    @api.depends('create_date', 'first_response_date')
    def _compute_response_time(self):
        for lead in self:
            if lead.create_date and lead.first_response_date:
                diff = lead.first_response_date - lead.create_date
                lead.response_time_hours = diff.total_seconds() / 3600
            else:
                lead.response_time_hours = 0.0

    @api.depends('transferred_date', 'write_date')
    def _compute_inactivity_days(self):
        for lead in self:
            if lead.transferred_date and lead.write_date:
                delta = lead.write_date - lead.transferred_date
                lead.inactivity_days = delta.days
            else:
                lead.inactivity_days = 0