from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    daysrule = fields.Boolean(
        string="Ativar Regra de Dias",
        config_parameter='crm.daysrule',
    )
    daystochange = fields.Integer(
        string='Dias para Mudar',
        config_parameter='crm.daystochange',
        default=7,
    )
    total_days = fields.Integer(
        string='Total de Dias',
        config_parameter='crm.total_days',
        default=30,
    )
    next_activity = fields.Boolean(
        string='Próxima Atividade',
        config_parameter='crm.next_activity',
    )
    require_next_activity = fields.Boolean(
        string='Exigir Próxima Atividade',
        config_parameter='crm.require_next_activity',
    )
    lost_sdr = fields.Boolean(
        string='Perdido para SDR',
        config_parameter='crm.lost_sdr',
    )
    sdr_user_id = fields.Many2one(
        'res.users',
        string='Usuário SDR',
        config_parameter='crm.sdr_user_id',
        help='Usuário padrão para quando a oportunidade for perdida para SDR',
    )
