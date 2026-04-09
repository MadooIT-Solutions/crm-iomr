from odoo import api, fields, models


class CRMLead(models.Model):
    """Extends crm.lead for adding more functions in it"""
    _inherit = 'crm.lead'

    referred_partner = fields.Many2one(
        'res.partner',
    )
