# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Aplica as regras de comissão das coordenadoras por categoria:

- Taxa de Sala, MAT/MED, COLA ORGANICA e TAXA DE EQUIPAMENTO -> comissão fixa
  de 0,25% (líquido).
- Nas demais categorias, a comissão é a política de coordenador (0,5% líquido).

Também garante que a política de coordenador use a base líquida (impostos da
linha + taxa de cartão).

Uso (odoo shell):
    from set_coordenadora_extra_commission import run
    run(env.cr)
"""

from odoo import SUPERUSER_ID, api

EXTRAS_COMMISSION_NAME = (
    "Comissão Coordenador(a) 0,25% (Taxa Sala / Mat-Med / Cola / Taxa Equipamento)"
)
EXTRAS_COMMISSION_XMLID = "crm_commissions.commission_coordinator_extras_025"
POLICY_XMLID = "crm_commissions.commission_coordinator_policy"
EXTRA_CATEGORIES = [
    "TAXA DE SALA",
    "MAT/MED",
    "COLA ORGANICA",
    "TAXA DE EQUIPAMENTO",
]


def get_or_create_extras_commission(env):
    extras = env.ref(EXTRAS_COMMISSION_XMLID, raise_if_not_found=False)
    if not extras:
        extras = env["commission"].search(
            [("name", "ilike", "Coordenador(a) 0,25%")], limit=1
        )
    if not extras:
        extras = env["commission"].create(
            {
                "name": EXTRAS_COMMISSION_NAME,
                "commission_type": "fixed",
                "fix_qty": 0.25,
                "amount_base_type": "net_amount_deduction",
                "deduct_taxes": True,
                "deduct_card_fee": True,
                "settlement_type": "sale_invoice",
            }
        )
        env["ir.model.data"].create(
            {
                "module": "crm_commissions",
                "name": EXTRAS_COMMISSION_XMLID.split(".")[1],
                "model": "commission",
                "res_id": extras.id,
            }
        )
    return extras


def ensure_policy_net_base(env):
    policy = env.ref(POLICY_XMLID, raise_if_not_found=False)
    if not policy:
        policy = env["commission"].search(
            [("commission_type", "=", "coordinator")], limit=1
        )
    if policy and (
        policy.amount_base_type != "net_amount_deduction"
        or not policy.deduct_taxes
        or not policy.deduct_card_fee
    ):
        policy.write(
            {
                "amount_base_type": "net_amount_deduction",
                "deduct_taxes": True,
                "deduct_card_fee": True,
            }
        )
    return policy


def apply_rules_for_coordenadoras(env, extras, extra_cats):
    created = 0
    updated = 0
    partners = env["res.partner"].search([("type_partner", "=", "coordenadora")])
    extra_ids = set(extra_cats.ids)
    for partner in partners:
        rules = env["commission.agent.rule"].search([("agent_id", "=", partner.id)])
        matching = rules.filtered(lambda r: set(r.categ_ids.ids) & extra_ids)
        if matching:
            rule = matching[0]
            rule.commission_id = extras.id
            missing = extra_ids - set(rule.categ_ids.ids)
            if missing:
                rule.categ_ids = [(6, 0, list(set(rule.categ_ids.ids) | extra_ids))]
            updated += 1
        else:
            env["commission.agent.rule"].create(
                {
                    "agent_id": partner.id,
                    "commission_id": extras.id,
                    "categ_ids": [(6, 0, list(extra_ids))],
                    "sequence": 10,
                }
            )
            created += 1
    return created, updated


def recompute_extra_category_lines(env, extra_cats):
    """Recalcula agent_id/comissão das linhas de venda nas categorias extras."""
    domain = []
    for cat in extra_cats:
        domain.append(("product_id.categ_id", "child_of", cat.id))
    lines = env["sale.order.line"].search(["|"] * (len(domain) - 1) + domain)
    lines._compute_agent_ids()
    return len(lines)


def run(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})
    policy = ensure_policy_net_base(env)
    extras = get_or_create_extras_commission(env)
    extra_cats = env["product.category"].search([("name", "in", EXTRA_CATEGORIES)])
    missing = set(EXTRA_CATEGORIES) - set(extra_cats.mapped("name"))
    if missing:
        print(f"ATENÇÃO: categorias não encontradas: {sorted(missing)}")
    created, updated = apply_rules_for_coordenadoras(env, extras, extra_cats)
    recomputed = recompute_extra_category_lines(env, extra_cats)
    print(f"Política coordenador (base líquida): {policy.id if policy else 'NENHUMA'}")
    print(f"Comissão fixa 0,25%: {extras.id} - {extras.name}")
    print(f"Categorias extras: {sorted(extra_cats.mapped('complete_name'))}")
    print(f"Regras criadas: {created} | regras atualizadas: {updated}")
    print(f"Linhas de venda recalculadas: {recomputed}")
    cr.commit()
    return {
        "policy_id": policy.id if policy else False,
        "extras_commission_id": extras.id,
        "created_rules": created,
        "updated_rules": updated,
        "recomputed_lines": recomputed,
    }
