from odoo import api, fields, models


class CRMLead(models.Model):
    """Extends crm.lead for adding more functions in it"""
    _inherit = 'crm.lead'

    referred_partner = fields.Many2many('res.partner', relation='crmlead_rel_res_partner', column1='lead_id', column2='partner_id', string='Indicações', copy=False)
