from odoo import api, fields, models
from odoo.exceptions import UserError


class CRMLead(models.Model):
    """Extends crm.lead for adding more functions in it"""
    _inherit = 'crm.lead'

    priority = fields.Selection(tracking=True)
    date_deadline = fields.Date(tracking=True)
    tag_ids = fields.Many2many(tracking=True)
    campaign_id = fields.Many2one(tracking=True)
    medium_id = fields.Many2one(tracking=True)
    source_id = fields.Many2one(tracking=True)

    referred_partner = fields.Many2many('res.partner', relation='crmlead_rel_res_partner', column1='lead_id', column2='partner_id', string='Indicações', copy=False, domain=[('type_partner', '!=', 'convenio')], tracking=True)
    convenio = fields.Many2one('res.partner', string='Convênio', domain=[('type_partner', '=', 'convenio')], tracking=True)
    doctor = fields.Many2one('res.partner', string='Doctor', domain=['|',('type_partner', '=', 'doctorext'),('type_partner', '=', 'doctorint')], tracking=True)
    procedure = fields.Char(string='Procedure', tracking=True)
    id_orc = fields.Integer(string='ID do Orçamento', tracking=True)
    date = fields.Date(string='Data', tracking=True)
    date_contact = fields.Date(string='Data do Contato', tracking=True)
    motives = fields.Char(string='Motives', tracking=True)
    state_klingo = fields.Char(string='State Klingo', tracking=True)

    rotation_count = fields.Integer(
        string='Contagem de Rotações',
        default=0,
        tracking=True,
        help='Quantas vezes a oportunidade foi rotacionada'
    )

    date_assigned_to_seller = fields.Datetime(
        string='Data Atribuída ao Vendedor',
        tracking=True,
        help='Data em que a oportunidade foi atribuída ao vendedor atual'
    )

    rotation_history_ids = fields.One2many(
        'crm.lead.rotation',
        'lead_id',
        string='Histórico de Rotação'
    )

    last_activity_date = fields.Datetime(
        string='Última Atividade',
        compute='_compute_last_activity_date',
        store=True
    )

    days_with_current_seller = fields.Integer(
        string='Dias com Vendedor Atual',
        compute='_compute_days_with_seller'
    )

    all_sellers_exhausted = fields.Boolean(
        string='Todos Vendedores Esgotados',
        default=False,
        tracking=True,
        help='Indica se a oportunidade já passou por todos os vendedores da equipe'
    )

    can_rotate = fields.Boolean(
        string='Pode Rotacionar',
        compute='_compute_can_rotate',
        help='Indica se o usuário atual pode rotacionar esta oportunidade'
    )

    def _compute_can_rotate(self):
        is_manager = self.env.user.has_group('sales_team.group_sale_manager')
        for lead in self:
            lead.can_rotate = is_manager or lead.user_id == self.env.user

    @api.depends('activity_ids')
    def _compute_last_activity_date(self):
        for lead in self:
            activities = lead.activity_ids.sorted('date_deadline', reverse=True)
            lead.last_activity_date = activities[0].date_deadline if activities else None

    def _compute_days_with_seller(self):
        for lead in self:
            if lead.date_assigned_to_seller:
                days = (fields.Datetime.now() - lead.date_assigned_to_seller).days
                lead.days_with_current_seller = max(0, days)
            elif lead.rotation_history_ids:
                last = lead.rotation_history_ids.sudo()[0]
                if last.date_rotation:
                    days = (fields.Datetime.now() - last.date_rotation).days
                    lead.days_with_current_seller = max(0, days)
                else:
                    lead.days_with_current_seller = 0
            else:
                lead.days_with_current_seller = 0

    @api.model_create_multi
    def create(self, vals_list):
        leads = super().create(vals_list)
        for lead in leads:
            if lead.user_id:
                lead.date_assigned_to_seller = fields.Datetime.now()
        return leads

    def write(self, vals):
        if 'user_id' in vals:
            for lead in self:
                if lead.user_id.id != vals['user_id']:
                    self.env['crm.lead.rotation'].create({
                        'lead_id': lead.id,
                        'user_from_id': lead.user_id.id,
                        'user_to_id': vals['user_id'],
                        'rotation_sequence': lead.rotation_count + 1,
                        'rotation_type': vals.get('rotation_type', 'manual'),
                        'days_with_seller': lead.days_with_current_seller,
                    })
                    vals['rotation_count'] = lead.rotation_count + 1
                    vals['date_assigned_to_seller'] = fields.Datetime.now()

        write_vals = {k: v for k, v in vals.items() if k in self._fields}
        return super().write(write_vals)

    def _get_config_bool(self, key, default=False):
        val = self.env['ir.config_parameter'].sudo().get_param(key, default)
        if isinstance(val, str):
            return val.lower() in ('true', '1', 'yes')
        return bool(val)

    def rotate_seller_automatic(self):
        """
        Rotaciona vendedor automaticamente baseado nas regras
        """
        config = self.env['ir.config_parameter'].sudo()

        daysrule_enabled = self._get_config_bool('crm.daysrule')
        daystochange = int(config.get_param('crm.daystochange', 7))
        total_days = int(config.get_param('crm.total_days', 30))
        lost_sdr_enabled = self._get_config_bool('crm.lost_sdr')
        sdr_user_id = int(config.get_param('crm.sdr_user_id', 0))

        if not daysrule_enabled:
            return False

        for lead in self:
            if lead.days_with_current_seller >= daystochange:
                # Obter próximo vendedor
                next_seller = lead._get_next_seller()

                if next_seller:
                    lead.write({
                        'user_id': next_seller.id,
                        'rotation_type': 'automatic',
                    })

                # Se passou total_days, ir para SDR
                elif lead.days_with_current_seller >= total_days and lost_sdr_enabled and sdr_user_id:
                    lead.write({
                        'user_id': sdr_user_id,
                        'rotation_type': 'lost_sdr',
                        'all_sellers_exhausted': True,
                    })

        return True

    def _get_next_seller(self):
        """
        Obtém o próximo vendedor da equipe que ainda não foi atribuído à oportunidade
        """
        self.ensure_one()

        team = self.user_id.sale_team_id
        if not team or not team.member_ids:
            return None

        used_sellers = set()
        used_sellers.add(self.user_id.id)
        for rotation in self.rotation_history_ids.sudo():
            if rotation.user_to_id:
                used_sellers.add(rotation.user_to_id.id)

        available_sellers = team.member_ids.filtered(
            lambda u: u.id not in used_sellers and u.active
        )

        if not available_sellers:
            return None

        return available_sellers[0]

    def action_open_rotation_history(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Histórico de Rotação',
            'res_model': 'crm.lead.rotation',
            'view_mode': 'list,form',
            'domain': [('lead_id', '=', self.id)],
            'context': {'default_lead_id': self.id},
        }

    def action_rotate_seller(self):
        """
        Ação manual para rotacionar vendedor
        """
        if not (self.env.user.has_group('sales_team.group_sale_manager') or self.user_id == self.env.user):
            raise UserError("Você não pode rotacionar esta oportunidade.")

        if not self.user_id:
            raise UserError("Oportunidade não tem vendedor atribuído")

        next_seller = self._get_next_seller()

        if not next_seller:
            config = self.env['ir.config_parameter'].sudo()
            sdr_user_id = int(config.get_param('crm.sdr_user_id', 0))
            if not sdr_user_id:
                raise UserError("Não há vendedores disponíveis e nenhum SDR configurado.")
            return {
                'type': 'ir.actions.act_window',
                'name': 'Encaminhar para SDR',
                'res_model': 'crm.lead.rotation.sdr.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_lead_id': self.id,
                    'default_sdr_user_id': sdr_user_id,
                },
            }

        self.write({'user_id': next_seller.id})
        return True