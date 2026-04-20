from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    type_partner = fields.Selection([('patient', 'Paciente'), ('doctorint', 'Médico Interno'),('doctorext','Médico Externo'),('employee', 'Funcionário'),
                                     ('supplier', 'Fornecedor'),('convenio','Convênio'),('gov','Governamental'),('others', 'Outros')], string='Tipo de Contato', default='others')