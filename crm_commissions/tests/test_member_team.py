# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase


class TestMemberSalesTeam(TransactionCase):
    """The Equipe menu must show the sales team of each member.

    The team is maintained on the contact (``res.partner.crm_team_id``); members
    are filled from it so the "Equipe de Vendas" column is never empty.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env["res.partner"]
        cls.Member = cls.env["commission.member"]
        cls.team_a = cls.env["crm.team"].create({"name": "Equipe Alpha"})
        cls.team_b = cls.env["crm.team"].create({"name": "Equipe Beta"})

    def _create_partner(self, name, team=None):
        return self.Partner.create(
            {
                "name": name,
                "type_partner": "orientadora",
                "agent": True,
                "agent_type": "orientadora",
                "crm_team_id": team.id if team else False,
            }
        )

    def _create_member(self, name, partner, team=None):
        vals = {
            "name": name,
            "member_type": "orientadora",
            "partner_id": partner.id,
        }
        if team:
            vals["team_id"] = team.id
        return self.Member.create(vals)

    def test_01_member_inherits_team_from_partner_on_create(self):
        partner = self._create_partner("Membro com equipe", self.team_a)

        member = self._create_member("Membro com equipe", partner)

        self.assertEqual(member.team_id, self.team_a)

    def test_02_partner_team_change_fills_empty_member_team(self):
        partner = self._create_partner("Membro sem equipe")
        member = self._create_member("Membro sem equipe", partner)
        self.assertFalse(member.team_id)

        partner.write({"crm_team_id": self.team_b.id})

        self.assertEqual(member.team_id, self.team_b)

    def test_03_manual_team_is_preserved(self):
        partner = self._create_partner("Membro com equipe manual", self.team_a)

        member = self._create_member(
            "Membro com equipe manual", partner, team=self.team_b
        )

        self.assertEqual(member.team_id, self.team_b)
        member.write({"team_id": self.team_a.id})
        self.assertEqual(member.team_id, self.team_a)

    def test_04_changing_partner_refills_missing_team(self):
        partner_without_team = self._create_partner("Contato sem equipe")
        partner_with_team = self._create_partner("Contato com equipe", self.team_a)
        member = self._create_member("Membro trocando de contato", partner_without_team)
        self.assertFalse(member.team_id)

        member.write({"partner_id": partner_with_team.id})

        self.assertEqual(member.team_id, self.team_a)

    def test_05_legacy_members_are_backfilled(self):
        partner = self._create_partner("Contato legado", self.team_a)
        legacy_member = self.Member.with_context(
            crm_commissions_skip_member_team_sync=True
        ).create(
            {
                "name": "Membro legado",
                "member_type": "orientadora",
                "partner_id": partner.id,
            }
        )
        self.assertFalse(legacy_member.team_id)

        legacy_member._sync_team_from_partner()

        self.assertEqual(legacy_member.team_id, self.team_a)

    def test_06_team_field_is_visible_in_the_equipe_views(self):
        arch = self.env.ref("crm_commissions.commission_member_tree").arch
        self.assertIn('name="team_id"', arch)
        search_arch = self.env.ref("crm_commissions.commission_member_search").arch
        self.assertIn('name="team_id"', search_arch)
        self.assertEqual(
            self.env["commission.member"]._fields["team_id"].string,
            "Equipe de Vendas",
        )
