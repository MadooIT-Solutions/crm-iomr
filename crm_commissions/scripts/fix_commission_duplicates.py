# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Corrige cadastros de comissão antes da migração 18.0.2.9.2.

A comissão progressiva passou a valer somente para LIO e as categorias extras
(TAXA DE SALA, MAT/MED, COLA ORGANICA e TAXA DE EQUIPAMENTO) passaram a pagar
a fixa de 1%. Este script remove os cadastros que poderiam duplicar as novas
regras:

- arquiva a comissão fixa de 1% antiga (clone sem Taxa de Equipamento);
- completa a comissão padrão de orientadoras sem ``commission_id`` a partir
  da orientadora duplicada (mesmo e-mail) e arquiva a duplicata sem uso;
- garante que a coordenadora use a política de coordenador como padrão;
- inclui COLA ORGANICA nos itens do "SDR 1% fixo", que só paga quando a venda
  é criada diretamente pelo SDR.

É idempotente. Uso (odoo shell):

    from fix_commission_duplicates import run
    run(env.cr)
"""

from odoo import SUPERUSER_ID, api

FIXED_COMMISSION_XMLID = "crm_commissions.commission_fixed_1pct_extras"
COORDINATOR_POLICY_XMLID = "crm_commissions.commission_coordinator_policy"
SDR_COMMISSION_NAME = "SDR 1% fixo"
SDR_CATEGORY_NAMES = (
    "TAXA DE SALA",
    "MAT/MED",
    "COLA ORGANICA",
    "TAXA DE EQUIPAMENTO",
)


def _commission_in_use(env, commission):
    """Whether the commission is referenced by any business record."""
    checks = (
        ("sale.order.line.agent", [("commission_id", "=", commission.id)]),
        ("account.invoice.line.agent", [("commission_id", "=", commission.id)]),
        ("account.invoice.line.agent", [("applied_commission_id", "=", commission.id)]),
        ("res.partner", [("commission_id", "=", commission.id)]),
        ("commission.agent.rule", [("commission_id", "=", commission.id)]),
        ("commission.settlement.line", [("commission_id", "=", commission.id)]),
    )
    return any(env[model].search_count(domain) for model, domain in checks)


def archive_legacy_fixed_commission(env):
    """Archive old fixed 1% commissions superseded by the current one."""
    fixed = env.ref(FIXED_COMMISSION_XMLID, raise_if_not_found=False)
    if not fixed:
        return []
    legacy = env["commission"].search(
        [
            ("name", "ilike", "Comissão Fixa 1%"),
            ("id", "!=", fixed.id),
        ]
    )
    archived = env["commission"]
    for commission in legacy:
        if _commission_in_use(env, commission):
            continue
        commission.active = False
        archived |= commission
    return archived.ids


def _partner_in_use(env, partner):
    checks = (
        ("res.users", [("partner_id", "=", partner.id)]),
        ("sale.order", [("partner_id", "=", partner.id)]),
        ("crm.lead", [("partner_id", "=", partner.id)]),
        ("account.move", [("partner_id", "=", partner.id)]),
        ("sale.order.line.agent", [("agent_id", "=", partner.id)]),
        ("account.invoice.line.agent", [("agent_id", "=", partner.id)]),
        ("commission.agent.rule", [("agent_id", "=", partner.id)]),
    )
    return any(env[model].search_count(domain) for model, domain in checks)


def fix_orientadora_commissions(env):
    """Fill missing default commissions and archive unused duplicates."""
    orientadoras = env["res.partner"].search(
        [("type_partner", "=", "orientadora"), ("agent", "=", True)]
    )
    filled = env["res.partner"]
    for partner in orientadoras.filtered(lambda p: not p.commission_id):
        domain = [
            ("id", "!=", partner.id),
            ("type_partner", "=", "orientadora"),
            ("commission_id", "!=", False),
        ]
        twin = env["res.partner"]
        if partner.email:
            twin = env["res.partner"].search(
                domain + [("email", "=ilike", partner.email)], limit=1
            )
        if not twin:
            twin = env["res.partner"].search(
                domain + [("name", "=", partner.name)], limit=1
            )
        if twin:
            partner.commission_id = twin.commission_id
            filled |= partner

    archived = env["res.partner"]
    groups = {}
    for partner in orientadoras:
        key = (partner.email or partner.name or "").strip().lower()
        if key:
            groups.setdefault(key, env["res.partner"])
            groups[key] |= partner
    for partners in groups.values():
        if len(partners) < 2:
            continue
        # Keep the partner that has a user, then the one already used by the
        # commission rules; archive the leftovers only when they are unused.
        keep = (
            env["res.users"]
            .search([("partner_id", "in", partners.ids)])
            .mapped("partner_id")
        )
        if not keep:
            keep = partners.filtered(
                lambda p: env["sale.order.line.agent"].search_count(
                    [("agent_id", "=", p.id)]
                )
            )
        if not keep:
            keep = partners.filtered("commission_id")[:1]
        if not keep:
            keep = partners.sorted("id")[:1]
        for partner in partners - keep:
            if _partner_in_use(env, partner):
                continue
            partner.active = False
            archived |= partner
    return {
        "default_filled": filled.ids,
        "archived": archived.ids,
    }


def fix_coordenadora_commission(env):
    """Coordenadoras must default to the coordinator policy, never LIO."""
    coordinator = env.ref(COORDINATOR_POLICY_XMLID, raise_if_not_found=False)
    if not coordinator:
        coordinator = env["commission"].search(
            [("commission_type", "=", "coordinator")], limit=1
        )
    if not coordinator:
        return []
    fixed = env.ref(FIXED_COMMISSION_XMLID, raise_if_not_found=False)
    updated = env["res.partner"]
    coordenadoras = env["res.partner"].search(
        [("type_partner", "=", "coordenadora"), ("agent", "=", True)]
    )
    for partner in coordenadoras:
        current = partner.commission_id
        if current in (coordinator, fixed):
            continue
        if current and current.commission_type in ("coordinator", "fixed"):
            continue
        partner.commission_id = coordinator
        updated |= partner
    return updated.ids


def ensure_sdr_fixed_covers_categories(env):
    """Add the missing categories to the SDR fixed 1% commission."""
    sdr = env["commission"].search([("name", "=", SDR_COMMISSION_NAME)], limit=1)
    if not sdr:
        return []
    categories = env["product.category"].search(
        [("name", "in", list(SDR_CATEGORY_NAMES))]
    )
    present = set(sdr.item_ids.mapped("categ_id").ids)
    created = env["commission.item"]
    for category in categories:
        if category.id in present:
            continue
        created |= env["commission.item"].create(
            {
                "commission_id": sdr.id,
                "categ_id": category.id,
                "based_on": "sol",
                "applied_on": "2_product_category",
                "commission_type": "percentage",
                "percent_amount": 1.0,
            }
        )
    return created.ids


def run(cr, commit=True):
    env = api.Environment(cr, SUPERUSER_ID, {})
    result = {
        "legacy_archived": archive_legacy_fixed_commission(env),
        "orientadoras": fix_orientadora_commissions(env),
        "coordenadoras": fix_coordenadora_commission(env),
        "sdr_items": ensure_sdr_fixed_covers_categories(env),
    }
    env.flush_all()
    if commit:
        cr.commit()
    return result
