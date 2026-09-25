# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Aplica as regras de repasse dos médicos por categoria de produto:

- Categorias de CONSULTA -> Repasse Médico - Consulta (60% sobre receita
  líquida: subtotal - impostos 16,33% - taxa de cartão).
- Categorias de EXAME -> Repasse Médico - Exame (50% sobre receita
  líquida: subtotal - impostos 11,73% - taxa de cartão).
- Categorias de CIRURGIA -> Repasse Médico - Cirurgia (Honorário)
  (100% sobre receita líquida: subtotal - impostos 11,73% - taxa de cartão).
- As demais categorias (LIO, Cola Orgânica etc.) mantêm a comissão atual
  do médico e não sofrem dedução.

Uso (odoo shell):
    from set_doctor_repasse_commission import run
    run(env.cr)
"""

from odoo import SUPERUSER_ID, api

CONSULTA_XMLID = "crm_commissions.commission_doctor_consulta"
EXAME_XMLID = "crm_commissions.commission_doctor_exame"
CIRURGIA_XMLID = "crm_commissions.commission_doctor_cirurgia"

# Palavras-chave usadas para localizar as categorias de produto. Ajuste
# conforme os nomes das categorias existentes no banco.
CONSULTA_CATEGORY_TERMS = ["CONSULTA"]
EXAME_CATEGORY_TERMS = ["EXAME"]
CIRURGIA_CATEGORY_TERMS = ["CIRURGICA", "CIRURGIA", "PROCEDIMENTO CIRURGICO"]

COMMISSION_SPECS = [
    (CONSULTA_XMLID, "Repasse Médico - Consulta", 60.0, 16.33),
    (EXAME_XMLID, "Repasse Médico - Exame", 50.0, 11.73),
    (CIRURGIA_XMLID, "Repasse Médico - Cirurgia (Honorário)", 100.0, 11.73),
]


def _get_commission(env, xmlid, name, fix_qty, tax_pct):
    commission = env.ref(xmlid, raise_if_not_found=False)
    if not commission:
        commission = env["commission"].search([("name", "=", name)], limit=1)
    if not commission:
        commission = env["commission"].create(
            {
                "name": name,
                "commission_type": "fixed",
                "fix_qty": fix_qty,
                "amount_base_type": "net_amount_deduction",
                "tax_deduction_pct": tax_pct,
                "deduct_card_fee": True,
                "settlement_type": "sale_invoice",
            }
        )
    return commission


def _get_categories(env, terms):
    result = env["product.category"]
    for term in terms:
        result |= env["product.category"].search([("name", "ilike", term)])
    return result


def get_commissions(env):
    return {
        spec[0]: _get_commission(env, *spec)
        for spec in COMMISSION_SPECS
    }


def apply_rules_for_doctors(env, commissions, mapped_categories):
    created = 0
    updated = 0
    doctors = env["res.partner"].search(
        [("type_partner", "in", ("doctorint", "doctorext"))]
    )
    for partner in doctors:
        for xmlid, cats in mapped_categories.items():
            if not cats:
                continue
            commission = commissions[xmlid]
            cat_ids = cats.ids
            rules = env["commission.agent.rule"].search(
                [("agent_id", "=", partner.id)]
            )
            matching = rules.filtered(
                lambda r: set(r.categ_ids.ids) & set(cat_ids)
            )
            if matching:
                rule = matching[0]
                rule.commission_id = commission.id
                missing = set(cat_ids) - set(rule.categ_ids.ids)
                if missing:
                    rule.categ_ids = [
                        (6, 0, list(set(rule.categ_ids.ids) | set(cat_ids)))
                    ]
                updated += 1
            else:
                env["commission.agent.rule"].create(
                    {
                        "agent_id": partner.id,
                        "commission_id": commission.id,
                        "categ_ids": [(6, 0, cat_ids)],
                        "sequence": 10,
                    }
                )
                created += 1
    return created, updated


def recompute_repasse_lines(env, categories):
    cats = env["product.category"]
    for _xmlid, cat_set in categories.items():
        cats |= cat_set
    if not cats:
        return 0
    domain = []
    for cat in cats:
        domain.append(("product_id.categ_id", "child_of", cat.id))
    lines = env["sale.order.line"].search(["|"] * (len(domain) - 1) + domain)
    lines._compute_agent_ids()
    return len(lines)


def run(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})
    commissions = get_commissions(env)
    consulta_cats = _get_categories(env, CONSULTA_CATEGORY_TERMS)
    exame_cats = _get_categories(env, EXAME_CATEGORY_TERMS)
    cirurgia_cats = _get_categories(env, CIRURGIA_CATEGORY_TERMS)
    mapped = {
        CONSULTA_XMLID: consulta_cats,
        EXAME_XMLID: exame_cats,
        CIRURGIA_XMLID: cirurgia_cats,
    }
    created, updated = apply_rules_for_doctors(env, commissions, mapped)
    recomputed = recompute_repasse_lines(env, mapped)
    for xmlid, comm in commissions.items():
        print(f"Comissão: {comm.id} - {comm.name}")
    print(f"Categorias de consulta: {sorted(consulta_cats.mapped('complete_name'))}")
    print(f"Categorias de exame: {sorted(exame_cats.mapped('complete_name'))}")
    print(f"Categorias de cirurgia: {sorted(cirurgia_cats.mapped('complete_name'))}")
    print(f"Médicos com regras criadas: {created} | regras atualizadas: {updated}")
    print(f"Linhas de venda recalculadas: {recomputed}")
    cr.commit()
    return {
        "commissions": {k: v.id for k, v in commissions.items()},
        "created_rules": created,
        "updated_rules": updated,
        "recomputed_lines": recomputed,
    }