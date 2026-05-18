from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    daysrule = fields.Boolean(string="Days Rule")
    daystochange = fields.Integer(string='Days to change')
    total_days = fields.Integer(string='Total Days')
    next_activity = fields.Boolean(string='Next activity')
    lost_sdr = fields.Boolean(string='Lost Sdr')
    require_next_activity = fields.Boolean(
        string='Require Next Activity',
        help='Obriga vendedor a ter próxima atividade agendada'
    )

    # Campos relacionados ao SDR
    sdr_user_id = fields.Many2one(
        'res.users',
        string='SDR User',
        help='Usuário padrão para oportunidades perdidas'
    )
