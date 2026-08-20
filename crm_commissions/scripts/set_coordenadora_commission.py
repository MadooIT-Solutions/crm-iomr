# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Vincula as orientadoras à sua coordenadora e espelha a comissão:

- Todas as orientadoras passam a ter coordenadora_id = Wanessa Santos.
- Garante a comissão "Coordenadora (via política)" (commission_type coordinator).
- Recalcula as linhas de venda para aplicar o espelhamento 0,5%.

Uso (odoo shell):
    from set_coordenadora_commission import run
    run(env.cr)
"""

from odoo import SUPERUSER_ID, api

COORDINATOR_NAME = "Wanessa Santos"
COORDINATOR_TYPE = "coordenadora"
COMMISSION_NAME = "Comissão Coordenadora (via política)"
COMMISSION_XMLID = "crm_commissions.commission_coordinator_policy"


def get_coordinator(env):
    coach = env["res.partner"].search(
        [
            ("type_partner", "=", COORDINATOR_TYPE),
            ("name", "=", COORDINATOR_NAME),
        ],
        limit=1,
    )
    if not coach:
        coach = env["res.partner"].search(
            [("type_partner", "=", COORDINATOR_TYPE)], limit=1
        )
    return coach


def get_or_create_coordinator_commission(env):
    commission = env.ref(COMMISSION_XMLID, raise_if_not_found=False)
    if not commission:
        commission = env["commission"].search(
            [("name", "=", COMMISSION_NAME)], limit=1
        )
    if not commission:
        commission = env["commission"].create(
            {
                "name": COMMISSION_NAME,
                "commission_type": "coordinator",
                "amount_base_type": "gross_amount",
                "settlement_type": "sale_invoice",
            }
        )
        env["ir.model.data"].create(
            {
                "module": "crm_commissions",
                "name": COMMISSION_XMLID.split(".")[1],
                "model": "commission",
                "res_id": commission.id,
            }
        )
    return commission


def link_orientadoras_to_coordinator(env, coach):
    domain = [("type_partner", "=", "orientadora")]
    if coach:
        domain.append(("coordenadora_id", "!=", coach.id))
    partners = env["res.partner"].search(domain)
    partners.write({"coordenadora_id": coach.id if coach else False})
    return len(partners)


def ensure_policy_rate(env, rate=0.5):
    policy = env["commission.policy"].search(
        [("active", "=", True)], order="date_start desc", limit=1
    )
    if policy and policy.coordinator_rate != rate:
        policy.coordinator_rate = rate
    return policy


def recompute_all_sale_lines(env):
    lines = env["sale.order.line"].search([])
    lines._compute_agent_ids()
    return len(lines)


def run(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})
    coach = get_coordinator(env)
    commission = get_or_create_coordinator_commission(env)
    policy = ensure_policy_rate(env)
    linked = link_orientadoras_to_coordinator(env, coach)
    recomputed = recompute_all_sale_lines(env)
    print(f"Coordenadora: {coach.id} - {coach.name}" if coach else "Coordenadora: NENHUMA")
    print(f"Comissão coordenadora: {commission.id} - {commission.name}")
    print(
        f"Política ativa: {policy.id} - coordinator_rate={policy.coordinator_rate}"
        if policy
        else "Política ativa: NENHUMA"
    )
    print(f"Orientadoras vinculadas: {linked}")
    print(f"Linhas de venda recalculadas: {recomputed}")
    cr.commit()
    return {
        "coordinadora_id": coach.id if coach else False,
        "commission_id": commission.id,
        "policy_rate": policy.coordinator_rate if policy else False,
        "linked_orientadoras": linked,
        "recomputed_lines": recomputed,
    }