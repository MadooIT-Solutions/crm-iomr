import calendar
from datetime import date, timedelta

from odoo import api, fields, models


class CrmSaleOrderMonthly(models.Model):
    _name = "crm.sale.order.monthly"
    _description = "Dashboard Mensal de Pedidos de Venda"
    _rec_name = "month"

    month = fields.Date(
        string="Mês",
        default=lambda self: fields.Date.today().replace(day=1),
        required=True,
    )
    invoiced_count = fields.Integer(
        string="Pedidos Faturados",
        compute="_compute_data",
    )
    invoiced_total = fields.Monetary(
        string="Total Faturado",
        compute="_compute_data",
        currency_field="currency_id",
    )
    uninvoiced_count = fields.Integer(
        string="Pedidos Não Faturados",
        compute="_compute_data",
    )
    uninvoiced_total = fields.Monetary(
        string="Total Não Faturado",
        compute="_compute_data",
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Moeda",
        default=lambda self: self.env.company.currency_id,
    )

    def _get_month_range(self):
        today = fields.Date.today()
        if isinstance(today, str):
            today = date.fromisoformat(today)
        first_day = today.replace(day=1)
        last_day = today.replace(
            day=calendar.monthrange(today.year, today.month)[1]
        )
        return first_day, last_day

    @api.depends()
    def _compute_data(self):
        first_day, last_day = self._get_month_range()

        invoiced = self.env["sale.order"].search(
            [
                ("state", "=", "sale"),
                ("invoice_status", "=", "invoiced"),
                ("date_order", ">=", first_day),
                ("date_order", "<=", last_day),
            ]
        )
        uninvoiced = self.env["sale.order"].search(
            [
                ("state", "=", "sale"),
                ("invoice_status", "=", "to invoice"),
                ("date_order", ">=", first_day),
                ("date_order", "<=", last_day),
            ]
        )

        for record in self:
            record.invoiced_count = len(invoiced)
            record.invoiced_total = sum(invoiced.mapped("amount_total"))
            record.uninvoiced_count = len(uninvoiced)
            record.uninvoiced_total = sum(uninvoiced.mapped("amount_total"))

    @api.model
    def action_open_dashboard(self):
        record = self.search([], limit=1)
        if not record:
            record = self.create(
                {"month": fields.Date.today().replace(day=1)}
            )
        return {
            "type": "ir.actions.act_window",
            "name": "Pedidos do Mês",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": record.id,
            "target": "current",
        }

    def action_view_invoiced_orders(self):
        self.ensure_one()
        first_day, last_day = self._get_month_range()
        return {
            "type": "ir.actions.act_window",
            "name": "Pedidos Faturados - Mês",
            "res_model": "sale.order",
            "view_mode": "tree,form",
            "domain": [
                ("state", "=", "sale"),
                ("invoice_status", "=", "invoiced"),
                ("date_order", ">=", first_day),
                ("date_order", "<=", last_day),
            ],
        }

    def action_view_uninvoiced_orders(self):
        self.ensure_one()
        first_day, last_day = self._get_month_range()
        return {
            "type": "ir.actions.act_window",
            "name": "Pedidos Confirmados Não Faturados - Mês",
            "res_model": "sale.order",
            "view_mode": "tree,form",
            "domain": [
                ("state", "=", "sale"),
                ("invoice_status", "=", "to invoice"),
                ("date_order", ">=", first_day),
                ("date_order", "<=", last_day),
            ],
        }
