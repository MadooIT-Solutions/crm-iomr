from odoo import api, fields, models

class SaleOrder(models.Model):
    _inherit = "sale.order"

    prontuario = fields.Char(
        string="Prontuário",
        related="partner_id.prontuario",
        readonly=False,
    )

    convenio = fields.Many2one(
        "res.partner",
        string="Convênio",
        domain=[("type_partner", "=", "convenio")],
        tracking=True,
    )

    doctor_id = fields.Many2one(
        "res.partner",
        string="Doctor/Médico",
        domain=[("type_partner", "in", ("doctorint", "doctorext"))],
    )

    referred_partner = fields.Many2many(
        "res.partner",
        relation="sale_order_rel_res_partner",
        column1="order_id",
        column2="partner_id",
        string="Indicações",
        copy=False,
        domain=[("type_partner", "!=", "convenio")],
    )

    @api.onchange("opportunity_id")
    def _onchange_opportunity_id(self):
        if self.opportunity_id:
            self.doctor_id = self.opportunity_id.doctor
            self.referred_partner = self.opportunity_id.referred_partner
            self.convenio = self.opportunity_id.convenio
        else:
            self.doctor_id = False
            self.referred_partner = False
            self.convenio = False

    def action_confirm(self):
        for rec in self:
            if not rec.doctor_id:
                raise UserError(
                    _("O campo Médico é obrigatório para confirmar o pedido.")
                )
            if not rec.opportunity_id:
                raise UserError(
                    _("O campo Oportunidade é obrigatório para confirmar o pedido.")
                )
            if not rec.convenio:
                raise UserError(
                    _("O campo Convênio é obrigatório para confirmar o pedido.")
                )
        return super().action_confirm()
