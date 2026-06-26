from odoo import api, fields, models


class CommissionMember(models.Model):
    _name = "commission.member"
    _description = "Commission Team Member"
    _order = "name"

    name = fields.Char(required=True)
    member_type = fields.Selection(
        [("orientadora", "Orientadora"),
         ("sdr", "SDR"),
         ("coordenadora", "Coordenadora")],
        required=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Related Contact",
        domain=[("type_partner", "in", ("orientadora", "sdr", "coordenadora"))],
        required=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="User",
        compute="_compute_user_id",
        inverse="_inverse_user_id",
        search="_search_user_id",
    )
    active = fields.Boolean(default=True)
    color = fields.Integer()
    team_id = fields.Many2one("crm.team", string="Sales Team")
    sdr_ids = fields.Many2many(
        "commission.member",
        "commission_member_sdr_rel",
        "orientadora_id",
        "sdr_id",
        string="Linked SDRs",
        domain=[("member_type", "=", "sdr")],
    )
    orientadora_id = fields.Many2one(
        "commission.member",
        string="Orientadora",
        domain=[("member_type", "=", "orientadora")],
    )
    target_ids = fields.One2many(
        "commission.target",
        "member_id",
        string="Targets",
    )
    result_ids = fields.One2many(
        "commission.result",
        "member_id",
        string="Results",
    )

    @api.depends("partner_id")
    def _compute_user_id(self):
        for rec in self:
            if rec.partner_id:
                user = self.env["res.users"].search(
                    [("partner_id", "=", rec.partner_id.id)], limit=1
                )
                rec.user_id = user
            else:
                rec.user_id = False

    def _inverse_user_id(self):
        for rec in self:
            if rec.user_id:
                rec.partner_id = rec.user_id.partner_id

    def _search_user_id(self, operator, value):
        partners = self.env["res.users"].search(
            [("partner_id", operator, value)]
        ).mapped("partner_id.id")
        return [("partner_id", "in", partners)]
