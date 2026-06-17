# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    type_partner = fields.Selection(
        selection_add=[
            ("orientadora", "Orientadora"),
            ("sdr", "SDR (Pré-orientadora)"),
            ("coordenadora", "Coordenadora"),
        ],
        ondelete={
            "orientadora": "set default",
            "sdr": "set default",
            "coordenadora": "set default",
        },
    )
    agent_type = fields.Selection(
        selection_add=[
            ("orientadora", "Orientadora"),
            ("sdr", "SDR"),
            ("coordenadora", "Coordenadora"),
            ("doctor", "Médico(a)"),
        ],
        ondelete={
            "orientadora": "set default",
            "sdr": "set default",
            "coordenadora": "set default",
            "doctor": "set default",
        },
    )
    crm_team_id = fields.Many2one(
        "crm.team",
        string="Sales team",
    )
    target_ids = fields.One2many(
        "crm.commission.target",
        inverse_name="agent_id",
        string="Monthly targets",
    )
    quarterly_bonus_ids = fields.One2many(
        "crm.commission.quarterly.bonus",
        inverse_name="agent_id",
        string="Quarterly bonuses",
    )
    sdr_agent_ids = fields.Many2many(
        "res.partner",
        relation="orientadora_sdr_rel",
        column1="orientadora_id",
        column2="sdr_id",
        string="Linked SDRs",
        domain=[("type_partner", "=", "sdr")],
    )
    is_crm_target = fields.Float(
        string="IS-CRM target (%)",
        default=95.0,
    )

    @api.onchange("type_partner")
    def _onchange_type_partner(self):
        if self.type_partner == "orientadora":
            self.agent = True
            if not self.agent_type or self.agent_type == "agent":
                self.agent_type = "orientadora"
        elif self.type_partner == "sdr":
            self.agent = True
            self.agent_type = "sdr"
        elif self.type_partner == "coordenadora":
            self.agent = True
            self.agent_type = "coordenadora"
        elif self.type_partner in ("doctorint", "doctorext"):
            self.agent = True
            self.agent_type = "doctor"
