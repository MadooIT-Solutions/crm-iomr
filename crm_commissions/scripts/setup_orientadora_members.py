# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Cadastra a Equipe de Repasses (commission.member) e tipa os partners dos
usuários conforme o grupo de função do usuário:

- Usuários no grupo Orientadora  -> type_partner/agent_type = 'orientadora' e member orientadora
- Usuários no grupo SDR          -> type_partner/agent_type = 'sdr'          e member sdr
- Usuários no grupo Coordenadora -> type_partner/agent_type = 'coordenadora' e member coordenadora

Sem esses registros o menu Equipe fica vazio e as record rules de orientadora
(que filtram por member_id.partner_id.user_ids) nunca devolvem nada, deixando
os menus Vendas/Metas/Resultados/Recuperação sem informação mesmo quando houver
dados cadastrados.

Regras do script (idempotente, pode rodar várias vezes):
- Só altera type_partner quando o valor atual for neutro ('others', vazio) ou
  'employee'. Nunca sobrescreve 'doctorint'/'doctorext'/'patient'/'convenio'/
  'supplier' — nesses casos apenas avisa e não mexe.
- Cria o commission.member somente se ainda não existir para aquele partner.

Uso (odoo shell):
    from setup_orientadora_members import run
    run(env.cr)
"""

from odoo import SUPERUSER_ID, api

# (grupo, member_type) — a ordem importa; em caso de conflito vence a última.
ROLE_MAP = [
    ("crm_commissions.group_crm_commission_orientadora", "orientadora"),
    ("crm_commissions.group_crm_commission_sdr", "sdr"),
    ("crm_commissions.group_commission_coordinator", "coordenadora"),
]

# type_partner que nunca devem ser sobrescritos pelo script.
PROTECTED_TYPES = {"doctorint", "doctorext", "patient", "convenio", "supplier"}

NEUTRAL_TYPES = {False, "", "others", "employee"}


def _get_or_create_member(env, partner, member_type):
    Member = env["commission.member"]
    member = Member.search([("partner_id", "=", partner.id)], limit=1)
    if member:
        if member.member_type != member_type:
            member.member_type = member_type
        return member, False
    member = Member.create(
        {
            "name": partner.name,
            "member_type": member_type,
            "partner_id": partner.id,
        }
    )
    return member, True


def run(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})
    typed = 0
    skipped = []
    members_created = 0
    members_existing = 0
    for xmlid, member_type in ROLE_MAP:
        group = env.ref(xmlid, raise_if_not_found=False)
        if not group:
            continue
        users = env["res.users"].search(
            [("groups_id", "in", [group.id]), ("share", "=", False)]
        )
        for user in users:
            partner = user.partner_id
            if not partner:
                skipped.append((user.login, "sem partner vinculado"))
                continue
            current = partner.type_partner
            if current in PROTECTED_TYPES:
                skipped.append(
                    (user.login, "type_partner protegido: %s" % current)
                )
                continue
            if current not in NEUTRAL_TYPES and current != member_type:
                # Outro tipo ativo (ex.: já é sdr/orientadora) — avisa e segue
                # sem sobrescrever.
                skipped.append(
                    (user.login, "type_partner inesperado: %s" % current)
                )
                continue
            if current != member_type:
                partner.write(
                    {
                        "type_partner": member_type,
                        "agent": True,
                        "agent_type": member_type,
                    }
                )
                typed += 1
            _, created = _get_or_create_member(env, partner, member_type)
            if created:
                members_created += 1
            else:
                members_existing += 1

    members = env["commission.member"].search([], order="name")
    print("Partners tipados: %d" % typed)
    print("commission.member criados: %d | já existiam: %d" % (
        members_created, members_existing))
    print("Total de membros na Equipe: %d" % len(members))
    for m in members:
        print("  - %s [%s] %s" % (m.name, m.member_type, m.user_id.login or "-"))
    if skipped:
        print("Pulados (não alterados):")
        for login, reason in skipped:
            print("  - %s: %s" % (login, reason))
    cr.commit()
    return {
        "typed_partners": typed,
        "members_created": members_created,
        "members_existing": members_existing,
        "members_total": len(members),
        "skipped": skipped,
    }