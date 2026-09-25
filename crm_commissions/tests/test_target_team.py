# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestTargetTeam(TransactionCase):
    """Metas Mensais: modo 'Equipe de Vendas' aplica a mesma meta a todos os
    vendedores (orientadoras) da equipe selecionada."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Target = cls.env["crm.commission.target"]
        cls.Partner = cls.env["res.partner"]
        cls.Team = cls.env["crm.team"]
        cls.TeamMember = cls.env["crm.team.member"]
        cls.User = cls.env["res.users"]

    def _make_orientadora(self, name, login):
        partner = self.Partner.create(
            {
                "name": name,
                "type_partner": "orientadora",
                "agent": True,
                "agent_type": "orientadora",
            }
        )
        user = self.User.create(
            {
                "name": name,
                "login": login,
                "partner_id": partner.id,
                "groups_id": [
                    (6, 0, [self.env.ref("base.group_user").id])
                ],
            }
        )
        return partner, user

    def _make_team(self, partners_users):
        team = self.Team.create({"name": "Equipe Teste Metas"})
        for _partner, user in partners_users:
            self.TeamMember.create(
                {"crm_team_id": team.id, "user_id": user.id}
            )
        return team

    def test_01_apply_team_creates_one_target_per_orientadora(self):
        p1, u1 = self._make_orientadora("Ori A", "ori_a_teste")
        p2, u2 = self._make_orientadora("Ori B", "ori_b_teste")
        team = self._make_team([(p1, u1), (p2, u2)])

        target = self.Target.create(
            {
                "target_scope": "team",
                "team_id": team.id,
                "target_date": date(2026, 9, 1),
                "target_amount": 5000.0,
            }
        )
        target.action_apply_team()

        created = self.Target.search(
            [
                ("target_scope", "=", "salesperson"),
                ("target_date", "=", date(2026, 9, 1)),
                ("agent_id", "in", (p1 + p2).ids),
            ]
        )
        self.assertEqual(len(created), 2)
        self.assertEqual(set(created.mapped("agent_id.id")), {p1.id, p2.id})
        for rec in created:
            self.assertEqual(rec.target_amount, 5000.0)
            self.assertEqual(rec.is_crm_score, 100.0)
        # o registro temporário de equipe é removido
        self.assertFalse(self.Target.browse(target.id).exists())

    def test_02_apply_team_skips_existing_and_keeps_them(self):
        p1, u1 = self._make_orientadora("Ori A", "ori_a_skip")
        p2, u2 = self._make_orientadora("Ori B", "ori_b_skip")
        team = self._make_team([(p1, u1), (p2, u2)])
        self.Target.create(
            {
                "target_scope": "salesperson",
                "agent_id": p1.id,
                "target_date": date(2026, 10, 1),
                "target_amount": 3000.0,
            }
        )
        target = self.Target.create(
            {
                "target_scope": "team",
                "team_id": team.id,
                "target_date": date(2026, 10, 1),
                "target_amount": 6000.0,
            }
        )
        target.action_apply_team()

        created = self.Target.search(
            [
                ("target_scope", "=", "salesperson"),
                ("target_date", "=", date(2026, 10, 1)),
                ("agent_id", "in", (p1 + p2).ids),
            ]
        )
        self.assertEqual(len(created), 2)
        # o alvo já existente do p1 não é sobrescrito/duplicado
        p1_target = created.filtered(lambda t: t.agent_id == p1)
        self.assertEqual(p1_target.target_amount, 3000.0)
        p2_target = created.filtered(lambda t: t.agent_id == p2)
        self.assertEqual(p2_target.target_amount, 6000.0)

    def test_03_team_without_orientadoras_raises(self):
        partner = self.Partner.create({"name": "Colaborador"})
        user = self.User.create(
            {
                "name": "Colaborador",
                "login": "colab_teste",
                "partner_id": partner.id,
                "groups_id": [
                    (6, 0, [self.env.ref("base.group_user").id])
                ],
            }
        )
        team = self._make_team([(partner, user)])
        target = self.Target.create(
            {
                "target_scope": "team",
                "team_id": team.id,
                "target_date": date(2026, 11, 1),
                "target_amount": 2000.0,
            }
        )
        with self.assertRaises(UserError):
            target.action_apply_team()

    def test_04_salesperson_scope_requires_agent(self):
        with self.assertRaises(ValidationError):
            self.Target.create(
                {
                    "target_scope": "salesperson",
                    "target_date": date(2026, 9, 1),
                    "target_amount": 1000.0,
                }
            )

    def test_05_team_scope_requires_team(self):
        with self.assertRaises(ValidationError):
            self.Target.create(
                {
                    "target_scope": "team",
                    "target_date": date(2026, 9, 1),
                    "target_amount": 1000.0,
                }
            )

    def test_06_individual_scope_still_works(self):
        partner, _user = self._make_orientadora("Ori Individual", "ori_ind")
        target = self.Target.create(
            {
                "target_scope": "salesperson",
                "agent_id": partner.id,
                "target_date": date(2026, 9, 1),
                "target_amount": 2500.0,
            }
        )
        self.assertEqual(target.team_id.id, False)
        self.assertEqual(target.agent_id, partner)

    def test_07_manager_in_sales_group_can_create_for_others(self):
        """Gestor que também é vendedor (ex.: Rodrigo) pode criar metas para
        outras orientadoras e aplicar metas de equipe (regra manager all)."""
        p1, u1 = self._make_orientadora("Ori M1", "ori_m1")
        p2, u2 = self._make_orientadora("Ori M2", "ori_m2")
        team = self._make_team([(p1, u1), (p2, u2)])

        manager = self.User.create(
            {
                "name": "Gerente Vendas",
                "login": "gerente_vendas_teste",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref(
                                "commission_oca.group_commission_manager"
                            ).id,
                            self.env.ref("sales_team.group_sale_salesman").id,
                        ],
                    ),
                ],
            }
        )
        manager_env = self.env(user=manager.id)

        # meta individual para outra orientadora
        ind = manager_env["crm.commission.target"].create(
            {
                "target_scope": "salesperson",
                "agent_id": p1.id,
                "target_date": date(2026, 9, 1),
                "target_amount": 1000.0,
            }
        )
        self.assertTrue(ind)

        # meta de equipe + aplicar
        team_target = manager_env["crm.commission.target"].create(
            {
                "target_scope": "team",
                "team_id": team.id,
                "target_date": date(2026, 9, 1),
                "target_amount": 5000.0,
            }
        )
        team_target.action_apply_team()

        created = self.Target.search(
            [
                ("target_scope", "=", "salesperson"),
                ("target_date", "=", date(2026, 9, 1)),
                ("agent_id", "in", (p1 + p2).ids),
            ]
        )
        self.assertEqual(len(created), 2)

    def test_08_commission_user_salesman_not_manager_still_blocked(self):
        """Usuário de comissão + vendedor (sem ser gestor) continua impedido de
        criar metas para outras orientadoras (regra own only)."""
        p1, u1 = self._make_orientadora("Ori S1", "ori_s1")

        user = self.User.create(
            {
                "name": "Usuario Comissao Vendedor",
                "login": "usuario_comissao_vendedor_teste",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref(
                                "commission_oca.group_commission_user"
                            ).id,
                            self.env.ref("sales_team.group_sale_salesman").id,
                        ],
                    ),
                ],
            }
        )
        user_env = self.env(user=user.id)
        with self.assertRaises(AccessError):
            user_env["crm.commission.target"].create(
                {
                    "target_scope": "salesperson",
                    "agent_id": p1.id,
                    "target_date": date(2026, 9, 1),
                    "target_amount": 1000.0,
                }
            )