from odoo import api, fields, models


class CrmLeadRotation(models.Model):
    _name = "crm.lead.rotation"
    _description = "Histórico de Rotação de Oportunidades"
    _order = "date_rotation desc"

    lead_id = fields.Many2one(
        "crm.lead", string="Oportunidade", required=True, ondelete="cascade"
    )
    user_from_id = fields.Many2one("res.users", string="Vendedor Anterior")
    user_to_id = fields.Many2one("res.users", string="Vendedor Atual")
    rotation_sequence = fields.Integer(string="Sequência")
    rotation_type = fields.Selection(
        [
            ("manual", "Manual"),
            ("automatic", "Automática"),
            ("lost_sdr", "Perdida para SDR"),
        ],
        string="Tipo de Rotação",
        default="manual",
    )
    days_with_seller = fields.Integer(string="Dias com Vendedor")
    date_rotation = fields.Datetime(
        string="Data da Rotação", default=fields.Datetime.now
    )
    notes = fields.Text(string="Observações")

    @api.model
    def action_rotation_report(self):
        domain = []
        if not self.env.user.has_group("sales_team.group_sale_manager"):
            domain = [("user_from_id", "=", self.env.user.id)]
        return {
            "type": "ir.actions.act_window",
            "name": "Histórico de Rotações",
            "res_model": "crm.lead.rotation",
            "view_mode": "list,form",
            "domain": domain,
            "context": dict(
                self.env.context,
                search_default_group_by_user_from_id=1,
            ),
        }

    @api.model
    def check_rotation_rules(self):
        """
        Verifica e aplica regras de rotação para todas as oportunidades
        Chamado por um Scheduled Action
        """
        config = self.env["ir.config_parameter"].sudo()
        daysrule_enabled = config.get_param("crm.daysrule", False)

        if not daysrule_enabled:
            return

        # Buscar oportunidades em andamento (não ganhas, não perdidas)
        leads = self.env["crm.lead"].search(
            [
                ("active", "=", True),
                ("probability", ">", 0),
                ("probability", "<", 100),
                ("user_id", "!=", False),
            ]
        )

        leads.rotate_seller_automatic()

    @api.model
    def validate_next_activity_requirement(self):
        """
        Valida se vendedores têm próxima atividade agendada
        """
        config = self.env["ir.config_parameter"].sudo()
        require_activity = config.get_param("crm.require_next_activity", False)

        if not require_activity:
            return

        # Buscar vendedores com oportunidades em andamento
        users = self.env["res.users"].search([("active", "=", True)])

        for user in users:
            # Verificar se tem atividades futuras
            today = fields.Date.today()
            activities = self.env["mail.activity"].search(
                [
                    ("user_id", "=", user.id),
                    ("date_deadline", ">=", today),
                    ("done", "=", False),
                ]
            )

            if not activities:
                # Log: Vendedor sem atividade
                self.env["ir.logging"].create(
                    {
                        "name": "CRM Rotation",
                        "type": "server",
                        "level": "WARNING",
                        "message": f"Vendedor {user.name} não possui próxima atividade agendada",
                        "path": "crm.lead.rotation",
                        "func_name": "validate_next_activity_requirement",
                    }
                )
