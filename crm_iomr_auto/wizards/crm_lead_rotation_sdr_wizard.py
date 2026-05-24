from odoo import api, fields, models


class CrmLeadRotationSdrWizard(models.TransientModel):
    _name = 'crm.lead.rotation.sdr.wizard'
    _description = 'Confirmação de Encaminhamento para SDR'

    lead_id = fields.Many2one('crm.lead', string='Oportunidade', required=True, readonly=True)
    sdr_user_id = fields.Many2one('res.users', string='SDR', required=True, readonly=True)

    def action_confirm(self):
        self.lead_id.write({
            'user_id': self.sdr_user_id.id,
            'rotation_type': 'lost_sdr',
            'all_sellers_exhausted': True,
        })
        return {'type': 'ir.actions.act_window_close'}
