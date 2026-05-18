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

    rotation_count = fields.Integer(
        string='Contagem de Rotações',
        default=0,
        help='Quantas vezes a oportunidade foi rotacionada'
    )

    date_assigned_to_seller = fields.Datetime(
        string='Data Atribuída ao Vendedor',
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

    # Campo para indicar se passou por todos os vendedores
    all_sellers_exhausted = fields.Boolean(
        string='Todos Vendedores Esgotados',
        default=False,
        help='Indica se a oportunidade já passou por todos os vendedores da equipe'
    )

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
        # Detectar mudança de vendedor
        if 'user_id' in vals:
            for lead in self:
                if lead.user_id.id != vals['user_id']:
                    old_user = lead.user_id
                    new_user = self.env['res.users'].browse(vals['user_id'])

                    # Registrar rotação
                    self.env['crm.lead.rotation'].create({
                        'lead_id': lead.id,
                        'user_from_id': old_user.id,
                        'user_to_id': new_user.id,
                        'rotation_sequence': lead.rotation_count + 1,
                        'rotation_type': 'manual',
                        'days_with_seller': lead.days_with_current_seller
                    })

                    vals['rotation_count'] = lead.rotation_count + 1
                    vals['date_assigned_to_seller'] = fields.Datetime.now()

        return super().write(vals)

    def rotate_seller_automatic(self):
        """
        Rotaciona vendedor automaticamente baseado nas regras
        """
        config = self.env['ir.config_parameter'].sudo()

        daysrule_enabled = config.get_param('crm.daysrule', False)
        daystochange = int(config.get_param('crm.daystochange', 7))
        total_days = int(config.get_param('crm.total_days', 30))
        lost_sdr_enabled = config.get_param('crm.lost_sdr', False)
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
                        'rotation_count': lead.rotation_count + 1,
                        'date_assigned_to_seller': fields.Datetime.now()
                    })

                    # Registrar rotação
                    self.env['crm.lead.rotation'].create({
                        'lead_id': lead.id,
                        'user_from_id': lead.user_id.id,
                        'user_to_id': next_seller.id,
                        'rotation_sequence': lead.rotation_count,
                        'rotation_type': 'automatic',
                        'days_with_seller': lead.days_with_current_seller
                    })

                # Se passou total_days, ir para SDR
                elif lead.days_with_current_seller >= total_days and lost_sdr_enabled and sdr_user_id:
                    sdr_user = self.env['res.users'].browse(sdr_user_id)
                    lead.write({
                        'user_id': sdr_user.id,
                        'all_sellers_exhausted': True,
                        'date_assigned_to_seller': fields.Datetime.now()
                    })

                    self.env['crm.lead.rotation'].create({
                        'lead_id': lead.id,
                        'user_from_id': lead.user_id.id,
                        'user_to_id': sdr_user.id,
                        'rotation_type': 'lost_sdr',
                        'days_with_seller': lead.days_with_current_seller
                    })

        return True

    def _get_next_seller(self):
        """
        Obtém o próximo vendedor da equipe que ainda não foi atribuído à oportunidade
        """
        config = self.env['ir.config_parameter'].sudo()
        team_id = int(config.get_param('crm.default_team_id', self.team_id.id or 0))

        # Obter all vendedores da equipe
        team = self.env['crm.team'].browse(team_id) if team_id else self.team_id

        if not team or not team.member_ids:
            return None

        # Obter histórico de vendedores que já trabalharam nesta oportunidade
        rotation_history = self.rotation_history_ids.mapped('user_to_id')
        used_sellers = set([self.user_id.id] + rotation_history.ids)

        # Obter vendedores disponíveis
        available_sellers = team.member_ids.filtered(
            lambda u: u.id not in used_sellers and u.active
        )

        if not available_sellers:
            self.write({'all_sellers_exhausted': True})
            return None

        # Retornar primeiro vendedor disponível (ou ordenar por critério)
        return available_sellers[0]

    def action_rotate_seller(self):
        """
        Ação manual para rotacionar vendedor
        """
        if not self.user_id:
            raise UserError("Oportunidade não tem vendedor atribuído")

        next_seller = self._get_next_seller()

        if not next_seller:
            raise UserError(
                "Não há mais vendedores disponíveis na equipe. "
                "A oportunidade será passada para o SDR."
            )

        self.write({'user_id': next_seller.id})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sucesso',
                'message': f'Oportunidade rotacionada para {next_seller.name}',
                'type': 'success',
            }
        }