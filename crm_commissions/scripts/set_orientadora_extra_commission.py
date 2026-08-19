# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Aplica as regras de comissão das orientadoras por categoria:

- Taxa de Sala, MAT/MED e COLA ORGANICA -> comissão fixa de 1%.
- Comissão Progressiva LIOs -> somente para a categoria LIO (e subcategorias).

Uso (odoo shell):
    from set_orientadora_extra_commission import run
    run(env.cr)
"""

from odoo import SUPERUSER_ID, api

FIXED_COMMISSION_NAME = "Comissão Fixa 1% (Taxa Sala / Mat-Med / Cola)"
FIXED_COMMISSION_XMLID = "crm_commissions.commission_fixed_1pct_extras"
PROGRESSIVE_XMLID = "crm_commissions.commission_progressive_lios"
EXTRA_CATEGORIES = ["TAXA DE SALA", "MAT/MED", "COLA ORGANICA"]
LIO_CATEGORY_NAME = "LIO"


def _get_category(env, name):
    return env["product.category"].search([("name", "=", name)], limit=1)


def get_or_create_fixed_commission(env):
    fixed = env.ref(FIXED_COMMISSION_XMLID, raise_if_not_found=False)
    if not fixed:
        fixed = env["commission"].search(
            [("name", "=", FIXED_COMMISSION_NAME)], limit=1
        )
    if not fixed:
        fixed = env["commission"].create(
            {
                "name": FIXED_COMMISSION_NAME,
                "commission_type": "fixed",
                "fix_qty": 1.0,
                "amount_base_type": "gross_amount",
                "settlement_type": "sale_invoice",
            }
        )
        env["ir.model.data"].create(
            {
                "module": "crm_commissions",
                "name": FIXED_COMMISSION_XMLID.split(".")[1],
                "model": "commission",
                "res_id": fixed.id,
            }
        )
    return fixed


def restrict_progressive_to_lio(env):
    """A progressão LIOs só vale para a categoria LIO e subcategorias."""
    prog = env.ref(PROGRESSIVE_XMLID, raise_if_not_found=False)
    if not prog:
        prog = env["commission"].search(
            [("name", "ilike", "Progressiva LIO")], limit=1
        )
    lio = _get_category(env, LIO_CATEGORY_NAME)
    if not prog or not lio:
        return [prog, lio]
    lio_cats = env["product.category"].search([("id", "child_of", lio.id)])
    prog.categ_ids = [(6, 0, lio_cats.ids)]
    return [prog, lio_cats]


def apply_rules_for_orientadoras(env, fixed, extra_cats):
    created = 0
    updated = 0
    partners = env["res.partner"].search([("type_partner", "=", "orientadora")])
    extra_ids = set(extra_cats.ids)
    for partner in partners:
        rules = env["commission.agent.rule"].search([("agent_id", "=", partner.id)])
        matching = rules.filtered(
            lambda r: set(r.categ_ids.ids) & extra_ids
        )
        if matching:
            rule = matching[0]
            rule.commission_id = fixed.id
            missing = extra_ids - set(rule.categ_ids.ids)
            if missing:
                rule.categ_ids = [
                    (6, 0, list(set(rule.categ_ids.ids) | extra_ids))
                ]
            updated += 1
        else:
            env["commission.agent.rule"].create(
                {
                    "agent_id": partner.id,
                    "commission_id": fixed.id,
                    "categ_ids": [(6, 0, list(extra_ids))],
                    "sequence": 10,
                }
            )
            created += 1
    return created, updated


def recompute_extra_category_lines(env, extra_cats):
    """Recalcula agent_id/commissão das linhas de venda nas categorias extras."""
    domain = []
    for cat in extra_cats:
        domain.append(("product_id.categ_id", "child_of", cat.id))
    lines = env["sale.order.line"].search(["|"] * (len(domain) - 1) + domain)
    lines._compute_agent_ids()
    return len(lines)


def run(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})
    fixed = get_or_create_fixed_commission(env)
    prog, lio_cats = restrict_progressive_to_lio(env)
    extra_cats = env["product.category"].search(
        [("name", "in", EXTRA_CATEGORIES)]
    )
    created, updated = apply_rules_for_orientadoras(env, fixed, extra_cats)
    recomputed = recompute_extra_category_lines(env, extra_cats)
    print(f"Comissão fixa: {fixed.id} - {fixed.name}")
    print(f"Progressiva {prog.id} restrita a LIO: {sorted(lio_cats.ids)}")
    print(f"Categorias extras: {sorted(extra_cats.mapped('complete_name'))}")
    print(f"Regras criadas: {created} | regras atualizadas: {updated}")
    print(f"Linhas de venda recalculadas: {recomputed}")
    cr.commit()
    return {
        "fixed_commission_id": fixed.id,
        "created_rules": created,
        "updated_rules": updated,
        "recomputed_lines": recomputed,
    }