# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestTargetTeam(TransactionCase):
    """Metas Mensais: modo 'Equipe de Vendas' aplica a mesma meta a todos os
    membros da equipe selecionada."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Target = cls.env["crm.commission.target"]
        cls.Partner = cls.env["res.partner"]
        cls.Team = cls.env["crm.team"]
        cls.TeamMember = cls.env["crm.team.member"]
        cls.Member = cls.env["commission.member"]
        cls.User = cls.env["res.users"]

    def _make_user(self, name, login, type_partner=False):
        """Contato + usuário, como os usuários do CRM são cadastrados de fato.

        ``type_partner`` fica vazio por padrão de propósito: nos dados reais
        quase nenhum contato tem o perfil 'Orientadora' preenchido, e era
        exatamente esse o bug da meta de equipe.
        """
        values = {"name": name}
        if type_partner:
            values.update(
                {
                    "type_partner": type_partner,
                    "agent": True,
                    "agent_type": type_partner,
                }
            )
        partner = self.Partner.create(values)
        user = self.User.create(
            {
                "name": name,
                "login": login,
                "partner_id": partner.id,
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        return partner, user

    def _make_team(self, partners_users):
        team = self.Team.create({"name": "Equipe Teste Metas"})
        for _partner, user in partners_users:
            if not user:
                continue
            self.TeamMember.create({"crm_team_id": team.id, "user_id": user.id})
        return team

    def _apply(self, team, target_date, amount, split=False, mode=None):
        """Cria a meta de equipe e aplica, confirmando o que houver em conflito.

        Sem ``mode`` a confirmação é respondida com 'manter' para não travar o
        teste; com 'substituir' ou 'manter' a escolha é exercitada.
        """
        target = self.Target.create(
            {
                "target_scope": "team",
                "team_id": team.id,
                "target_date": target_date,
                "target_amount": amount,
                "split_team_target": split,
            }
        )
        action = target.action_apply_team()
        if action.get("res_model") == "crm.commission.target.team.apply":
            wizard = self.env[action["res_model"]].browse(action["res_id"])
            self.assertTrue(wizard.conflict_ids)
            wizard.apply_mode = mode or "keep"
            action = wizard.action_confirm()
        return target, action

    def _targets_of(self, partners, target_date):
        return self.Target.search(
            [
                ("target_scope", "=", "salesperson"),
                ("target_date", "=", target_date),
                ("agent_id", "in", partners.ids),
            ]
        )

    def test_01_apply_team_creates_one_target_per_member(self):
        p1, u1 = self._make_user("Ori A", "ori_a_teste", "orientadora")
        p2, u2 = self._make_user("Ori B", "ori_b_teste", "orientadora")
        team = self._make_team([(p1, u1), (p2, u2)])
        target_date = date(2026, 9, 1)

        target = self.Target.create(
            {
                "target_scope": "team",
                "team_id": team.id,
                "target_date": target_date,
                "target_amount": 5000.0,
            }
        )
        target.action_apply_team()

        created = self._targets_of(p1 + p2, target_date)
        self.assertEqual(len(created), 2)
        self.assertEqual(set(created.mapped("agent_id.id")), {p1.id, p2.id})
        for rec in created:
            self.assertEqual(rec.target_amount, 5000.0)
            self.assertEqual(rec.is_crm_score, 100.0)
        # o registro temporário de equipe é removido
        self.assertFalse(self.Target.browse(target.id).exists())

    def test_02_apply_team_asks_before_touching_existing_targets(self):
        """Com meta já existente a confirmação é exigida antes de aplicar."""
        p1, u1 = self._make_user("Ori A", "ori_a_skip", "orientadora")
        p2, u2 = self._make_user("Ori B", "ori_b_skip", "orientadora")
        team = self._make_team([(p1, u1), (p2, u2)])
        target_date = date(2026, 10, 1)
        p1_target = self.Target.create(
            {
                "target_scope": "salesperson",
                "agent_id": p1.id,
                "target_date": target_date,
                "target_amount": 3000.0,
            }
        )
        target = self.Target.create(
            {
                "target_scope": "team",
                "team_id": team.id,
                "target_date": target_date,
                "target_amount": 6000.0,
            }
        )

        action = target.action_apply_team()

        self.assertEqual(action["res_model"], "crm.commission.target.team.apply")
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        self.assertEqual(wizard.conflict_ids, p1)
        self.assertEqual(wizard.apply_mode, "keep")
        # nada foi criado enquanto o usuário não decide
        self.assertFalse(self._targets_of(p2, target_date))
        self.assertEqual(p1_target.target_amount, 3000.0)
        self.assertTrue(target.exists())

    def test_02b_apply_team_keeps_existing_when_confirmed_to_keep(self):
        p1, u1 = self._make_user("Ori A", "ori_a_skip", "orientadora")
        p2, u2 = self._make_user("Ori B", "ori_b_skip", "orientadora")
        team = self._make_team([(p1, u1), (p2, u2)])
        target_date = date(2026, 10, 1)
        self.Target.create(
            {
                "target_scope": "salesperson",
                "agent_id": p1.id,
                "target_date": target_date,
                "target_amount": 3000.0,
            }
        )

        self._apply(team, target_date, 6000.0, mode="keep")

        created = self._targets_of(p1 + p2, target_date)
        self.assertEqual(len(created), 2)
        # o alvo já existente do p1 não é sobrescrito/duplicado
        p1_target = created.filtered(lambda t: t.agent_id == p1)
        self.assertEqual(p1_target.target_amount, 3000.0)
        p2_target = created.filtered(lambda t: t.agent_id == p2)
        self.assertEqual(p2_target.target_amount, 6000.0)

    def test_02c_apply_team_replaces_existing_when_confirmed_to_replace(self):
        """Escolhendo 'substituir', a meta existente passa a ser a da equipe."""
        p1, u1 = self._make_user("Ori A", "ori_a_repl", "orientadora")
        p2, u2 = self._make_user("Ori B", "ori_b_repl", "orientadora")
        team = self._make_team([(p1, u1), (p2, u2)])
        target_date = date(2026, 10, 1)
        old = self.Target.create(
            {
                "target_scope": "salesperson",
                "agent_id": p1.id,
                "target_date": target_date,
                "target_amount": 3000.0,
            }
        )

        self._apply(team, target_date, 6000.0, mode="replace")

        created = self._targets_of(p1 + p2, target_date)
        # substituído, não duplicado
        self.assertEqual(len(created), 2)
        replaced = created.filtered(lambda t: t.agent_id == p1)
        self.assertEqual(replaced.id, old.id)
        self.assertEqual(replaced.target_amount, 6000.0)
        self.assertEqual(replaced.team_id, team)
        self.assertEqual(
            created.filtered(lambda t: t.agent_id == p2).target_amount, 6000.0
        )

    def test_03_team_without_members_raises(self):
        team = self.Team.create({"name": "Equipe Vazia"})
        target_date = date(2026, 11, 1)
        target = self.Target.create(
            {
                "target_scope": "team",
                "team_id": team.id,
                "target_date": target_date,
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
        partner, _user = self._make_user("Ori Individual", "ori_ind")
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
        p1, u1 = self._make_user("Ori M1", "ori_m1", "orientadora")
        p2, u2 = self._make_user("Ori M2", "ori_m2", "orientadora")
        team = self._make_team([(p1, u1), (p2, u2)])
        target_date = date(2026, 9, 1)

        manager = self.User.create(
            {
                "name": "Gerente Vendas",
                "login": "gerente_vendas_teste",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("commission_oca.group_commission_manager").id,
                            self.env.ref("sales_team.group_sale_salesman").id,
                        ],
                    ),
                ],
            }
        )
        manager_env = self.env(user=manager.id)

        # meta individual para outra orientadora
        manager_env["crm.commission.target"].create(
            {
                "target_scope": "salesperson",
                "agent_id": p1.id,
                "target_date": target_date,
                "target_amount": 1000.0,
            }
        )

        # meta de equipe + aplicar (p1 já tem meta, então há confirmação)
        manager_target = manager_env["crm.commission.target"].create(
            {
                "target_scope": "team",
                "team_id": team.id,
                "target_date": target_date,
                "target_amount": 5000.0,
            }
        )
        action = manager_target.action_apply_team()

        self.assertEqual(action["res_model"], "crm.commission.target.team.apply")
        wizard = manager_env[action["res_model"]].browse(action["res_id"])
        self.assertEqual(wizard.conflict_ids, p1)
        wizard.action_confirm()

        created = self._targets_of(p1 + p2, target_date)
        self.assertEqual(len(created), 2)
        # a meta individual de 1000 foi preservada e a equipe criou a de p2
        self.assertEqual(
            created.filtered(lambda t: t.agent_id == p1).target_amount, 1000.0
        )
        self.assertEqual(
            created.filtered(lambda t: t.agent_id == p2).target_amount, 5000.0
        )

    def test_08_commission_user_salesman_not_manager_still_blocked(self):
        """Usuário de comissão + vendedor (sem ser gestor) continua impedido de
        criar metas para outras orientadoras (regra own only)."""
        p1, _u1 = self._make_user("Ori S1", "ori_s1", "orientadora")

        user = self.User.create(
            {
                "name": "Usuario Comissao Vendedor",
                "login": "usuario_comissao_vendedor_teste",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("commission_oca.group_commission_user").id,
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

    def test_09_members_without_orientadora_profile_are_included(self):
        """Regressão do bug reportado.

        A equipe tem 4 pessoas e nenhuma tem o perfil 'Orientadora' no
        contato. Antes, só quem tivesse o perfil exato entrava e a meta saía
        para 2 pessoas (ou nenhuma); agora entra todo mundo da equipe.
        """
        members = [
            self._make_user("Sem Perfil A", "sem_perfil_a"),
            self._make_user("Sem Perfil B", "sem_perfil_b"),
            self._make_user("Sem Perfil C", "sem_perfil_c"),
            self._make_user("Sem Perfil D", "sem_perfil_d"),
        ]
        team = self._make_team(members)
        target_date = date(2026, 12, 1)

        self._apply(team, target_date, 7000.0)

        created = self._targets_of(
            self.Partner.browse([p.id for p, _u in members]), target_date
        )
        self.assertEqual(len(created), 4)
        self.assertEqual(
            set(created.mapped("agent_id.id")), {p.id for p, _u in members}
        )

    def test_10_sdr_and_coordenadora_are_included(self):
        """SDR e coordenadora também recebem a meta da equipe."""
        members = [
            self._make_user("SDR Teste", "sdr_meta_teste", "sdr"),
            self._make_user("Coordenadora Teste", "coord_meta_teste", "coordenadora"),
        ]
        team = self._make_team(members)
        target_date = date(2026, 12, 1)

        self._apply(team, target_date, 4000.0)

        created = self._targets_of(
            self.Partner.browse([p.id for p, _u in members]), target_date
        )
        self.assertEqual(len(created), 2)

    def test_11_union_of_the_three_team_sources_without_duplicates(self):
        """Equipe cadastrada em lugares diferentes deve gerar uma meta só."""
        crm_p, crm_u = self._make_user("Fonte CRM", "fonte_crm")
        member_p, _member_u = self._make_user("Fonte Membro", "fonte_membro")
        partner_p, _partner_u = self._make_user("Fonte Contato", "fonte_contato")
        other_p, other_u = self._make_user("Outra Equipe", "outra_equipe")
        team = self.Team.create({"name": "Equipe Multi Fonte"})
        self.TeamMember.create({"crm_team_id": team.id, "user_id": crm_u.id})
        # o mesmo contato também aparece no Membro de Comissão
        self.Member.create(
            {
                "name": "Fonte CRM",
                "member_type": "orientadora",
                "partner_id": crm_p.id,
                "team_id": team.id,
            }
        )
        self.Member.create(
            {
                "name": "Fonte Membro",
                "member_type": "orientadora",
                "partner_id": member_p.id,
                "team_id": team.id,
            }
        )
        partner_p.crm_team_id = team
        other_team = self.Team.create({"name": "Outra Equipe"})
        self.TeamMember.create({"crm_team_id": other_team.id, "user_id": other_u.id})
        target_date = date(2026, 12, 1)

        self._apply(team, target_date, 2500.0)

        created = self._targets_of(crm_p + member_p + partner_p, target_date)
        self.assertEqual(len(created), 3)
        # ninguém de outra equipe entrou
        self.assertFalse(self._targets_of(other_p, target_date))
        # a meta preserva a equipe em todos os registros
        self.assertEqual(set(created.mapped("team_id.id")), {team.id})

    def test_12_inactive_member_is_not_included(self):
        active_p, active_u = self._make_user("Membro Ativo", "membro_ativo")
        inactive_p, _inactive_u = self._make_user("Membro Inativo", "inativo_x")
        team = self._make_team([(active_p, active_u)])
        # só aparece na equipe via um Membro de Comissão arquivado
        self.Member.create(
            {
                "name": "Membro Arquivado",
                "member_type": "orientadora",
                "partner_id": inactive_p.id,
                "team_id": team.id,
                "active": False,
            }
        )
        target_date = date(2026, 12, 1)

        self._apply(team, target_date, 1500.0)

        self.assertTrue(self._targets_of(active_p, target_date))
        self.assertFalse(self._targets_of(inactive_p, target_date))

    def test_13_kept_members_are_reported_to_the_user(self):
        """Quem teve a meta mantida é avisado, em vez de sumir em silêncio."""
        p1, u1 = self._make_user("Aviso A", "aviso_a", "orientadora")
        p2, u2 = self._make_user("Aviso B", "aviso_b", "orientadora")
        team = self._make_team([(p1, u1), (p2, u2)])
        target_date = date(2026, 12, 1)
        self.Target.create(
            {
                "target_scope": "salesperson",
                "agent_id": p1.id,
                "target_date": target_date,
                "target_amount": 1000.0,
            }
        )

        with patch.object(type(self.env.user), "_bus_send", autospec=True) as bus_send:
            self._apply(team, target_date, 9000.0, mode="keep")

        self.assertEqual(bus_send.call_count, 1)
        notification = bus_send.call_args[0][2]
        self.assertIn(p1.name, notification["message"])
        self.assertNotIn(p2.name, notification["message"])
        self.assertEqual(notification["type"], "warning")

    def test_14_no_notification_when_nothing_is_kept(self):
        p1, u1 = self._make_user("Sem Aviso", "sem_aviso", "orientadora")
        team = self._make_team([(p1, u1)])
        target_date = date(2026, 12, 1)

        with patch.object(type(self.env.user), "_bus_send", autospec=True) as bus_send:
            self._apply(team, target_date, 9000.0)

        bus_send.assert_not_called()

    def test_15_split_flag_divides_equally_between_members(self):
        p1, u1 = self._make_user("Split A", "split_a")
        p2, u2 = self._make_user("Split B", "split_b")
        team = self._make_team([(p1, u1), (p2, u2)])
        target_date = date(2027, 1, 1)

        self._apply(team, target_date, 10000.0, split=True)

        created = self._targets_of(p1 + p2, target_date)
        self.assertEqual(len(created), 2)
        self.assertEqual(sorted(created.mapped("target_amount")), [5000.0, 5000.0])

    def test_16_split_flag_keeps_whole_amount_when_not_checked(self):
        p1, u1 = self._make_user("Sem Split A", "sem_split_a")
        p2, u2 = self._make_user("Sem Split B", "sem_split_b")
        team = self._make_team([(p1, u1), (p2, u2)])
        target_date = date(2027, 1, 1)

        self._apply(team, target_date, 10000.0, split=False)

        created = self._targets_of(p1 + p2, target_date)
        self.assertEqual(sorted(created.mapped("target_amount")), [10000.0, 10000.0])

    def test_17_split_distributes_remainder_cents(self):
        """1000 por 3 não fecha: a sobra vai para as primeiras, sem furar a soma."""
        members = [
            self._make_user("Resto A", "resto_a"),
            self._make_user("Resto B", "resto_b"),
            self._make_user("Resto C", "resto_c"),
        ]
        team = self._make_team(members)
        target_date = date(2027, 1, 1)

        self._apply(team, target_date, 1000.0, split=True)

        created = self._targets_of(
            self.Partner.browse([p.id for p, _u in members]), target_date
        )
        amounts = sorted(created.mapped("target_amount"))
        self.assertEqual(amounts, [333.33, 333.33, 333.34])
        self.assertAlmostEqual(sum(amounts), 1000.0, places=2)

    def test_18_split_remainder_is_at_most_one_cent_each(self):
        members = [
            self._make_user(f"Cent {letter}", f"cent_{letter.lower()}")
            for letter in "ABCDEFG"
        ]
        team = self._make_team(members)
        target_date = date(2027, 1, 1)

        self._apply(team, target_date, 1000000.0, split=True)

        created = self._targets_of(
            self.Partner.browse([p.id for p, _u in members]), target_date
        )
        amounts = created.mapped("target_amount")
        self.assertEqual(len(amounts), 7)
        self.assertAlmostEqual(sum(amounts), 1000000.0, places=2)
        self.assertLessEqual(max(amounts) - min(amounts), 0.01)

    def test_19_split_divides_only_among_who_receives_now(self):
        """Mantendo a meta existente, o total é dividido entre as demais."""
        p1, u1 = self._make_user("Div A", "div_a", "orientadora")
        p2, u2 = self._make_user("Div B", "div_b", "orientadora")
        team = self._make_team([(p1, u1), (p2, u2)])
        target_date = date(2027, 1, 1)
        self.Target.create(
            {
                "target_scope": "salesperson",
                "agent_id": p1.id,
                "target_date": target_date,
                "target_amount": 1000.0,
            }
        )

        self._apply(team, target_date, 9000.0, split=True, mode="keep")

        created = self._targets_of(p1 + p2, target_date)
        self.assertEqual(len(created), 2)
        self.assertEqual(
            created.filtered(lambda t: t.agent_id == p1).target_amount, 1000.0
        )
        self.assertEqual(
            created.filtered(lambda t: t.agent_id == p2).target_amount, 9000.0
        )

    def test_20_split_replaces_existing_with_the_divided_amount(self):
        """Substituindo, o total da equipe é dividido por todos os membros."""
        p1, u1 = self._make_user("Rep A", "rep_a", "orientadora")
        p2, u2 = self._make_user("Rep B", "rep_b", "orientadora")
        team = self._make_team([(p1, u1), (p2, u2)])
        target_date = date(2027, 1, 1)
        self.Target.create(
            {
                "target_scope": "salesperson",
                "agent_id": p1.id,
                "target_date": target_date,
                "target_amount": 1000.0,
            }
        )

        self._apply(team, target_date, 9000.0, split=True, mode="replace")

        created = self._targets_of(p1 + p2, target_date)
        self.assertEqual(len(created), 2)
        self.assertEqual(sorted(created.mapped("target_amount")), [4500.0, 4500.0])
        self.assertAlmostEqual(sum(created.mapped("target_amount")), 9000.0, places=2)

    def test_21_split_with_zero_amount_does_not_break(self):
        p1, u1 = self._make_user("Zero A", "zero_a")
        p2, u2 = self._make_user("Zero B", "zero_b")
        team = self._make_team([(p1, u1), (p2, u2)])
        target_date = date(2027, 1, 1)

        self._apply(team, target_date, 0.0, split=True)

        created = self._targets_of(p1 + p2, target_date)
        self.assertEqual(len(created), 2)
        self.assertEqual(sorted(created.mapped("target_amount")), [0.0, 0.0])

    def test_22_split_flag_visible_only_for_team_scope(self):
        arch = self.env["crm.commission.target"].get_view(
            self.env.ref("crm_commissions.crm_commission_target_form").id, "form"
        )["arch"]
        self.assertIn('name="split_team_target"', arch)
        self.assertIn("invisible=\"target_scope != 'team'\"", arch)
