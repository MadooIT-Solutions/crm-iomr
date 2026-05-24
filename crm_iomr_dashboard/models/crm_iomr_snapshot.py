from odoo import models, fields, api
from datetime import date


class CrmIomrSnapshot(models.Model):
    _name = 'crm.iomr.snapshot'
    _description = 'Snapshot Semanal de KPIs CRM'
    _order = 'date desc'

    date = fields.Date(string="Data do Snapshot", default=fields.Date.context_today)
    total_weighted_forecast = fields.Monetary(string="Total Forecast Ponderado", currency_field='currency_id')
    avg_ticket = fields.Monetary(string="Ticket Médio", currency_field='currency_id')
    avg_roi = fields.Float(string="ROI Médio (%)")
    total_surgeries_value = fields.Monetary(string="Valor Total Cirurgias", currency_field='currency_id')
    surgery_forecast_count = fields.Integer(string="Oportunidades em Marcação Cirúrgica")

    # Recovery
    recovered_revenue = fields.Monetary(string="Receita Recuperada", currency_field='currency_id')
    recovery_rate = fields.Float(string="Taxa de Recuperação (%)")

    # Produtividade
    avg_response_time = fields.Float(string="Tempo Médio de Resposta (h)")
    avg_conversion_rate = fields.Float(string="Taxa Média Conversão SQL (%)")

    # Pareto de Perdas
    loss_reason_pareto = fields.Text(string="Pareto de Motivos de Perda")

    # Efetividade Orientadora B
    transferred_leads_count = fields.Integer(string="Leads Transferidos")
    transferred_closure_rate = fields.Float(string="Taxa de Fechamento pós-Transferência (%)")

    currency_id = fields.Many2one('res.currency', string="Moeda", default=lambda self: self.env.company.currency_id)

    def _get_surgery_stage(self):
        return self.env.ref('crm_iomr_dashboard.stage_marcacao_cirurgica', raise_if_not_found=False)

    def action_generate_weekly_snapshot(self):
        today = fields.Date.today()
        leads = self.env['crm.lead'].search([('active', '=', True)])
        won_leads = self.env['crm.lead'].search([('probability', '=', 100)])

        # Forecast
        total_forecast = sum(leads.mapped('weighted_forecast'))
        total_revenue = sum(won_leads.mapped('expected_revenue'))
        qty_won = len(won_leads) or 1
        avg_ticket = total_revenue / qty_won

        # Cirurgias
        surgeries = leads.filtered(lambda l: l.is_surgery)
        total_surgeries = sum(surgeries.mapped('surgery_value'))

        surgery_stage = self._get_surgery_stage()
        surgery_forecast = 0
        if surgery_stage:
            surgery_forecast = self.env['crm.lead'].search_count([
                ('stage_id', '=', surgery_stage.id),
            ])

        # ROI
        leads_with_cost = leads.filtered(lambda l: l.acquisition_cost > 0)
        avg_roi = 0.0
        if leads_with_cost:
            avg_roi = sum(
                ((l.expected_revenue - l.acquisition_cost) / l.acquisition_cost) * 100
                for l in leads_with_cost
            ) / len(leads_with_cost)

        # Recovery
        recovered = self.env['crm.recovery.loop'].search([('state', '=', 'recovered')])
        recovered_revenue = sum(recovered.mapped('recovered_value') or [0])
        total_recovery = self.env['crm.recovery.loop'].search_count(
            [('state', 'in', ('recovered', 'failed'))]
        )
        recovery_rate = 0.0
        if total_recovery:
            recovered_count = len(recovered)
            recovery_rate = (recovered_count / total_recovery) * 100

        # Produtividade
        all_users = self.env['res.users'].search([('share', '=', False)])
        user_leads = {u.id: self.env['crm.lead'].search([('user_id', '=', u.id)]) for u in all_users}
        resp_times = []
        conv_rates = []
        for u in all_users:
            ul = user_leads[u.id]
            if ul:
                resp = ul.mapped('response_time_hours')
                resp_avg = sum(resp) / len(resp)
                resp_times.append(resp_avg)

                sql_count = len(ul.filtered(lambda l: l.is_sql))
                conv_rates.append((sql_count / len(ul)) * 100)

        avg_resp_time = sum(resp_times) / len(resp_times) if resp_times else 0
        avg_conv = sum(conv_rates) / len(conv_rates) if conv_rates else 0

        # Pareto de Perdas
        lost_leads = self.env['crm.lead'].search([
            ('active', '=', False),
            ('probability', '=', 0),
            ('lost_reason_id', '!=', False),
        ])
        loss_reasons = {}
        for lead in lost_leads:
            name = lead.lost_reason_id.name
            loss_reasons[name] = loss_reasons.get(name, 0) + 1
        sorted_reasons = sorted(loss_reasons.items(), key=lambda x: x[1], reverse=True)
        pareto_lines = [f"{r[0]}: {r[1]}" for r in sorted_reasons]
        pareto_text = "\n".join(pareto_lines) if pareto_lines else "Nenhum motivo registrado"

        # Transferências (Orientadora B)
        transferred = self.env['crm.lead'].search([('transferred_from_id', '!=', False)])
        transferred_count = len(transferred)
        closed_after_transfer = transferred.filtered(lambda l: l.probability == 100)
        transfer_closure = (len(closed_after_transfer) / transferred_count * 100) if transferred_count else 0

        snapshot = self.create({
            'date': today,
            'total_weighted_forecast': total_forecast,
            'avg_ticket': avg_ticket,
            'avg_roi': avg_roi,
            'total_surgeries_value': total_surgeries,
            'surgery_forecast_count': surgery_forecast,
            'recovered_revenue': recovered_revenue,
            'recovery_rate': recovery_rate,
            'avg_response_time': avg_resp_time,
            'avg_conversion_rate': avg_conv,
            'loss_reason_pareto': pareto_text,
            'transferred_leads_count': transferred_count,
            'transferred_closure_rate': transfer_closure,
        })

        self._send_snapshot_email(snapshot)
        return snapshot

    def _send_snapshot_email(self, snapshot):
        users = self.env['res.users'].search([
            ('groups_id', 'in', self.env.ref('sales_team.group_sale_manager').id),
            ('share', '=', False),
        ])
        for user in users:
            self.env['mail.activity'].create({
                'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                'summary': 'Snapshot Semanal de KPIs CRM',
                'note': self._format_snapshot_text(snapshot),
                'user_id': user.id,
                'date_deadline': fields.Date.today(),
            })

    def _format_snapshot_text(self, snapshot):
        return (
            f"Snapshot de KPIs - {snapshot.date}\n"
            f"{'='*40}\n\n"
            f"Forecast Ponderado: R$ {snapshot.total_weighted_forecast:,.2f}\n"
            f"Ticket Médio: R$ {snapshot.avg_ticket:,.2f}\n"
            f"ROI Médio: {snapshot.avg_roi:.1f}%\n"
            f"Oportunidades em Marcação Cirúrgica: {snapshot.surgery_forecast_count}\n"
            f"Valor Total Cirurgias: R$ {snapshot.total_surgeries_value:,.2f}\n\n"
            f"Receita Recuperada: R$ {snapshot.recovered_revenue:,.2f}\n"
            f"Taxa de Recuperação: {snapshot.recovery_rate:.1f}%\n\n"
            f"Tempo Médio Resposta: {snapshot.avg_response_time:.1f}h\n"
            f"Taxa Conversão SQL: {snapshot.avg_conversion_rate:.1f}%\n\n"
            f"Pareto de Perdas:\n{snapshot.loss_reason_pareto}\n\n"
            f"Leads Transferidos: {snapshot.transferred_leads_count}\n"
            f"Taxa Fechamento pós-Transferência: {snapshot.transferred_closure_rate:.1f}%"
        )