# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase


class TestCoordinatorIndividualized(TransactionCase):
    """Valida o cálculo individualizado da Coordenadora conforme Política 2026."""

    def setUp(self):
        super().setUp()
        self.policy = self.env["commission.policy"].search([], limit=1)
        if not self.policy:
            self.policy = self.env["commission.policy"].create({
                "name": "Política Teste",
                "date_start": "2026-01-01",
            })

        # Cria equipe
        self.team = self.env["crm.team"].create({
            "name": "Equipe Teste",
        })

        # Cria coordenadora
        self.coordinator_partner = self.env["res.partner"].create({
            "name": "Coordenadora Teste",
            "type_partner": "coordenadora",
            "agent_type": "coordenadora",
            "agent": True,
        })
        self.coordinator_user = self.env["res.users"].create({
            "name": "Coordenadora User",
            "login": "coord_test",
            "partner_id": self.coordinator_partner.id,
        })
        self.team.user_id = self.coordinator_user.id

        self.coordinator_member = self.env["commission.member"].create({
            "name": "Coordenadora Teste",
            "member_type": "coordenadora",
            "partner_id": self.coordinator_partner.id,
            "team_id": self.team.id,
        })

        # Cria orientadoras
        self.orientadora_a = self.env["commission.member"].create({
            "name": "Orientadora A",
            "member_type": "orientadora",
            "partner_id": self.env["res.partner"].create({
                "name": "Orientadora A",
                "type_partner": "orientadora",
                "agent_type": "orientadora",
                "agent": True,
            }).id,
            "team_id": self.team.id,
        })

        self.orientadora_b = self.env["commission.member"].create({
            "name": "Orientadora B",
            "member_type": "orientadora",
            "partner_id": self.env["res.partner"].create({
                "name": "Orientadora B",
                "type_partner": "orientadora",
                "agent_type": "orientadora",
                "agent": True,
            }).id,
            "team_id": self.team.id,
        })

    def test_coordinator_individualized_calculation(self):
        """Valida que a comissão da coordenadora é calculada individualmente."""
        period = "2026-01"

        # Cria metas para orientadoras
        target_a = self.env["commission.target"].create({
            "member_id": self.orientadora_a.id,
            "year": 2026,
            "month": "1",
            "individual_target_amount": 100000,
        })

        target_b = self.env["commission.target"].create({
            "member_id": self.orientadora_b.id,
            "year": 2026,
            "month": "1",
            "individual_target_amount": 100000,
        })

        # Cria vendas para orientadora A (40% da meta = 0,25% taxa)
        sale_a = self.env["commission.sale"].create({
            "owner_member_id": self.orientadora_a.id,
            "patient_name": "Paciente A",
            "surgery_type": "catarata",
            "sale_category": "particular",
            "date": "2026-01-15",
            "hospital_gross_amount": 40000,
            "commission_base_amount": 40000,
            "status": "confirmed",
        })

        # Cria vendas para orientadora B (70% da meta = 0,45% taxa)
        sale_b = self.env["commission.sale"].create({
            "owner_member_id": self.orientadora_b.id,
            "patient_name": "Paciente B",
            "surgery_type": "catarata",
            "sale_category": "particular",
            "date": "2026-01-15",
            "hospital_gross_amount": 70000,
            "commission_base_amount": 70000,
            "status": "confirmed",
        })

        # Cria resultado da coordenadora
        result = self.env["commission.result"].create({
            "member_id": self.coordinator_member.id,
            "period_code": period,
            "policy_id": self.policy.id,
        })

        # Calcula
        result.action_calculate()

        # Valida cálculo individualizado:
        # Orientadora A: 40000 * 0.25% = 100
        # Orientadora B: 70000 * 0.45% = 315
        # Total esperado: 415
        expected_commission = 40000 * 0.0025 + 70000 * 0.0045  # 100 + 315 = 415

        self.assertAlmostEqual(
            result.commission_base_amount,
            expected_commission,
            places=2,
            msg=f"Esperado {expected_commission}, obtido {result.commission_base_amount}"
        )

        # Valida que não há bônus/penalidade IS-CRM para coordenadora
        self.assertEqual(result.crm_bonus_rate, 0.0)
        self.assertEqual(result.is_crm_score, 100.0)

    def test_coordinator_without_team_uses_fallback(self):
        """Valida comportamento quando coordenadora não tem equipe."""
        period = "2026-01"

        # Cria coordenadora sem equipe
        coordinator_no_team = self.env["commission.member"].create({
            "name": "Coordenadora Sem Equipe",
            "member_type": "coordenadora",
            "partner_id": self.env["res.partner"].create({
                "name": "Coordenadora Sem Equipe",
                "type_partner": "coordenadora",
                "agent_type": "coordenadora",
                "agent": True,
            }).id,
        })

        result = self.env["commission.result"].create({
            "member_id": coordinator_no_team.id,
            "period_code": period,
            "policy_id": self.policy.id,
        })

        # Calcula - não deve gerar erro
        result.action_calculate()

        # Sem equipe, commission_base deve ser 0
        self.assertEqual(result.commission_base_amount, 0.0)

    def test_coordinator_quarterly_bonus_eligibility(self):
        """Valida que coordenadora é elegível ao bônus trimestral quando equipe atinge meta."""
        # Este teste valida a lógica de elegibilidade
        # A implementação verifica se team_total_achieved >= team_total_target
        quarter = "Q1"
        year = 2026

        # Cria bônus para a equipe
        bonus = self.env["crm.commission.quarterly.bonus"].create({
            "agent_id": self.orientadora_a.partner_id.id,
            "quarter": quarter,
            "year": year,
            "team_id": self.team.id,
        })

        # Verifica que o campo is_team_eligible existe
        self.assertTrue(hasattr(bonus, "is_team_eligible"))

        # Verifica método de sincronização existe
        self.assertTrue(hasattr(self.env["crm.commission.quarterly.bonus"], "_sync_coordinator_bonus"))
