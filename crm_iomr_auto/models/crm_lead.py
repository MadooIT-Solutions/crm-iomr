from odoo import api, fields, models


class CRMLead(models.Model):
    """Extends crm.lead for adding more functions in it"""
    _inherit = 'crm.lead'

    referred_partner = fields.Many2many('res.partner', relation='crmlead_rel_res_partner', column1='lead_id', column2='partner_id', string='Indicações', copy=False, domain=[('type_partner', '!=', 'convenio')])
    convenio = fields.Many2one('res.partner', string='Convênio', domain=[('type_partner', '=', 'convenio')])
    doctor = fields.Many2one('res.partner', string='Doctor', domain=['|',('type_partner', '=', 'doctorext'),('type_partner', '=', 'doctorint')])
    procedure = fields.Char(string='Procedure')
    id_orc = fields.Integer(string='ID do Orçamento')
    date = fields.Date(strign='Data')
    date_contact = fields.Date(string='Data do Contato')
    motives = fields.Char(string='Motives')
    state_klingo = fields.Char(string='State Klingo')
    