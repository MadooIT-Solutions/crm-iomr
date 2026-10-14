# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Coordenador(a): base líquida, comissão por categoria e funil Defensoria.

A comissão da coordenadora era uma única taxa global sobre o valor bruto, o
que permitia que ela recebesse o mesmo percentual da orientadora (quando seu
``res.partner.commission_id`` era igual ao dela) e nunca a matriz por categoria
da clínica. Esta migração:

1. Converte a política de coordenador para a base líquida (impostos da linha +
   taxa de cartão), a mesma regra do repasse.
2. Cria a comissão fixa de 0,25% para as quatro categorias extras.
3. Cria as regras ``commission.agent.rule`` por coordenadora para essas
   categorias, o mesmo modelo usado pelas orientadoras.
4. Recalcula as linhas de venda para aplicar as novas comissões.

O funil Defensoria Pública (1% fixo) é tratado em código e não precisa de dados.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

COORDINATOR_POLICY_XMLID = "crm_commissions.commission_coordinator_policy"
COORDINATOR_EXTRAS_XMLID = "crm_commissions.commission_coordinator_extras_025"
COORDINATOR_EXTRA_CATEGORY_NAMES = (
    "TAXA DE SALA",
    "MAT/MED",
    "COLA ORGANICA",
    "TAXA DE EQUIPAMENTO",
)


def set_coordinator_policy_net_base(env):
    """Turn the coordinator policy into a net base (taxes + card fee)."""
    commission = env.ref(COORDINATOR_POLICY_XMLID, raise_if_not_found=False)
    if not commission:
        commission = env["commission"].search(
            [("commission_type", "=", "coordinator")], limit=1
        )
    if not commission:
        return False
    if (
        commission.amount_base_type != "net_amount_deduction"
        or not commission.deduct_taxes
        or not commission.deduct_card_fee
    ):
        commission.write(
            {
                "amount_base_type": "net_amount_deduction",
                "deduct_taxes": True,
                "deduct_card_fee": True,
            }
        )
    return commission


def get_or_create_coordinator_extras_commission(env):
    """Create the 0,25% fixed commission for the coordinator extras."""
    extras = env.ref(COORDINATOR_EXTRAS_XMLID, raise_if_not_found=False)
    if not extras:
        extras = env["commission"].search(
            [("name", "ilike", "Coordenador(a) 0,25%")], limit=1
        )
    if not extras:
        extras = env["commission"].create(
            {
                "name": "Comissão Coordenador(a) 0,25% (Taxa Sala / Mat-Med / Cola / Taxa Equipamento)",
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
                "name": COORDINATOR_EXTRAS_XMLID.split(".")[1],
                "model": "commission",
                "res_id": extras.id,
            }
        )
    return extras


def apply_coordinator_extra_rules(env, extras):
    """Create/update the per-coordinator agent rules for the extras categories."""
    extra_cats = env["product.category"].search(
        [("name", "in", COORDINATOR_EXTRA_CATEGORY_NAMES)]
    )
    missing = set(COORDINATOR_EXTRA_CATEGORY_NAMES) - set(extra_cats.mapped("name"))
    if missing:
        _logger.warning(
            "Coordinator extras: categorias não encontradas: %s", sorted(missing)
        )
    if not extra_cats:
        return 0, 0
    extra_ids = set(extra_cats.ids)
    created = 0
    updated = 0
    partners = env["res.partner"].search([("type_partner", "=", "coordenadora")])
    for partner in partners:
        rules = env["commission.agent.rule"].search([("agent_id", "=", partner.id)])
        matching = rules.filtered(lambda r: set(r.categ_ids.ids) & extra_ids)
        if matching:
            rule = matching[0]
            rule.commission_id = extras.id
            missing_ids = extra_ids - set(rule.categ_ids.ids)
            if missing_ids:
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


def recompute_sale_lines(env):
    lines = env["sale.order.line"].search([])
    lines._compute_agent_ids()
    return len(lines)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    commission = set_coordinator_policy_net_base(env)
    _logger.info(
        "Coordinator policy: %s (%s)",
        commission.id if commission else "NENHUMA",
        commission.name if commission else "-",
    )
    extras = get_or_create_coordinator_extras_commission(env)
    _logger.info("Coordinator extras commission: %s (%s)", extras.id, extras.name)
    created, updated = apply_coordinator_extra_rules(env, extras)
    _logger.info(
        "Coordinator extras rules: %s criadas, %s atualizadas", created, updated
    )
    recomputed = recompute_sale_lines(env)
    _logger.info("Sale lines recomputed: %s", recomputed)
