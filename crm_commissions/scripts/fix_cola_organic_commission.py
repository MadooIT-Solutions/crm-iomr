# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Corrige comissões de COLA ORGANICA e demais categorias extras.

A comissão progressiva (``Comissão Progressiva LIOs``) só deve valer para as
vendas do catálogo LIO. As categorias extras -- TAXA DE SALA, MAT/MED, COLA
ORGANICA e TAXA DE EQUIPAMENTO -- devem pagar a comissão fixa de 1% da
orientadora (SDR 1%, quando criado direto pelo SDR) e a comissão de
coordenadora correspondente.

Este script localiza as linhas de agente de fatura (``account.invoice.line.agent``)
que carregam a comissão progressiva sobre uma categoria extra e as realinha com
a comissão/split vindos da linha de venda de origem (``sale_order_line.agent``),
que é a fonte usada para montar a linha da fatura.

Linhas de settlement já fechadas que receberam a comissão errada são
revisadas também, para o próximo fechamento não reprocessar nada.

É idempotente. Uso (odoo shell):

    from fix_cola_organic_commission import run
    run(env.cr, commit=True)
"""

from odoo import SUPERUSER_ID, api

EXTRA_CATEGORY_NAMES = (
    "TAXA DE SALA",
    "MAT/MED",
    "COLA ORGANICA",
    "TAXA DE EQUIPAMENTO",
)


def _extra_category_ids(env):
    """Ids (e subcategorias) das categorias extras de repasse."""
    categories = env["product.category"].search(
        [("name", "in", list(EXTRA_CATEGORY_NAMES))]
    )
    ids = set()
    for category in categories:
        ids.update(
            env["product.category"].search([("id", "child_of", category.id)]).ids
        )
    return ids


def _ancestor_ids(env, category):
    """Caminho completo de categorias (raiz inclusive) de um registro."""
    ids = set()
    current = category
    while current:
        ids.add(current.id)
        current = current.parent_id
    return ids


def _offending_lines(env):
    """Linhas de agente com comissão progressiva sobre categoria extra."""
    extra_ids = _extra_category_ids(env)
    progressive_lines = env["account.invoice.line.agent"].sudo().search(
        [
            ("commission_id.commission_type", "=", "progressive"),
            ("object_id.product_id", "!=", False),
        ]
    )
    offenders = []
    for line in progressive_lines:
        product = line.object_id.product_id
        if not product or not _ancestor_ids(env, product.categ_id) & extra_ids:
            continue
        offenders.append(line)
    return offenders


def _sync_line_from_sale_line(env, line):
    """Reaplica a comissão/split da linha de venda na linha de fatura."""
    source_lines = line.object_id.sale_line_ids
    source = source_lines[0] if source_lines else False
    if not source:
        return False
    matched = False
    for sale_agent in source.agent_ids.filtered("commission_id"):
        if sale_agent.agent_id.id != line.agent_id.id:
            continue
        line.commission_id = sale_agent.commission_id
        line.commission_split_percent = sale_agent.commission_split_percent or 100.0
        matched = True
    return matched


def _fallback_commission(env, agent):
    """Comissão correta quando a linha de venda não tem agente correspondente."""
    extras_commission = env["commission"].sudo().search(
        [
            ("name", "ilike", "Comissão Fixa 1%"),
            ("commission_type", "=", "fixed"),
        ],
        order="id desc",
        limit=1,
    )
    coordinator_commission = env["commission"].sudo().search(
        [
            ("name", "ilike", "Comissão Coordenadora"),
            ("commission_type", "=", "fixed"),
        ],
        order="id desc",
        limit=1,
    )
    sdr_commission = env["commission"].sudo().search(
        [("name", "=", "SDR 1% fixo"), ("commission_type", "=", "product")],
        limit=1,
    )
    commission = extras_commission
    if agent.type_partner == "coordenadora" and coordinator_commission:
        commission = coordinator_commission
    elif agent.type_partner == "sdr" and sdr_commission:
        commission = sdr_commission
    return commission


def _correction_amount(env, line, commission=None):
    """Valor da comissão da linha (com base líquida quando aplicável)."""
    invoice_line = line.object_id
    amount = line._get_commission_amount(
        commission or line.commission_id,
        invoice_line.price_subtotal,
        invoice_line.product_id,
        invoice_line.quantity,
    )
    if invoice_line.move_id and "refund" in invoice_line.move_id.move_type:
        amount = -amount
    return float(amount or 0.0)


def _corrected_commission_from_sale_line(env, line):
    """Comissão correta (sem escrever) a partir da linha de venda de origem."""
    source_lines = line.object_id.sale_line_ids
    source = source_lines[0] if source_lines else False
    commission = False
    if source:
        for sale_agent in source.agent_ids.filtered("commission_id"):
            if sale_agent.agent_id.id == line.agent_id.id:
                commission = sale_agent.commission_id
                break
    return commission or _fallback_commission(env, line.agent_id)


def run(cr, commit=True):
    env = api.Environment(cr, SUPERUSER_ID, {})
    offenders = _offending_lines(env)
    updated_lines = []
    corrected_settlements = []
    for line in offenders:
        agent = line.agent_id
        # Médicos têm comissão própria (Repasse por Categoria); apenas os
        # agentes de comissão lateral (orientadora/SDR/coordenadora) são
        # realinhados, e somente quando a categoria é extra.
        if agent.type_partner in ("doctorint", "doctorext"):
            continue
        if line.settled:
            # Linha já fechada: o OCA bloqueia a escrita pelo ORM, então a
            # linha de agente é corrigida por SQL (a raiz do problema: o
            # fechamento copia a comissão daqui) e a linha de settlement é
            # realinhada via ORM.
            commission = _corrected_commission_from_sale_line(env, line)
            amount = _correction_amount(env, line, commission)
            env.cr.execute(
                "UPDATE account_invoice_line_agent"
                " SET commission_id = %s, amount = %s WHERE id = %s",
                (commission.id, amount, line.id),
            )
            for settlement_line in line.settlement_line_ids:
                settlement_line.write(
                    {
                        "commission_id": commission.id,
                        "settled_amount": amount,
                    }
                )
                corrected_settlements.append(settlement_line.id)
            continue
        if _sync_line_from_sale_line(env, line):
            updated_lines.append(line)
            continue
        commission = _fallback_commission(env, agent)
        if commission and line.commission_id != commission:
            line.commission_id = commission
            updated_lines.append(line)

    updated_ids = [line.id for line in updated_lines]
    if updated_ids:
        for line in env["account.invoice.line.agent"].browse(updated_ids):
            line._compute_amount()

    env.flush_all()
    env.invalidate_all()
    if commit:
        cr.commit()
    return {
        "offending_lines": [line.id for line in offenders],
        "corrected_lines": updated_ids,
        "corrected_settlements": corrected_settlements,
    }
