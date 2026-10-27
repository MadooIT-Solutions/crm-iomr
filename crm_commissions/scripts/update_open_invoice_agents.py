# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Alinha os agentes das faturas abertas com as linhas de venda de origem.

A comissão progressiva passou a valer somente para LIO e as categorias extras
(TAXA DE SALA, MAT/MED, COLA ORGANICA e TAXA DE EQUIPAMENTO) passaram a pagar
a fixa de 1%. As linhas de pedido foram recalculadas, mas as faturas já
geradas continuavam com a comissão antiga (progressiva) ou sem a orientadora.

Este script espelha, nas linhas de fatura ainda abertas (rascunho e postadas
não pagas), os agentes da linha de venda de origem. Faturas pagas e linhas já
fechadas por settlement não são tocadas.

É idempotente. Uso (odoo shell):

    from update_open_invoice_agents import run
    run(env.cr, commit=True)
"""

from odoo import SUPERUSER_ID, api

EXTRA_CATEGORY_NAMES = (
    "TAXA DE SALA",
    "MAT/MED",
    "COLA ORGANICA",
    "TAXA DE EQUIPAMENTO",
)


def _extras_category_ids(env):
    categories = env["product.category"].search(
        [("name", "in", list(EXTRA_CATEGORY_NAMES))]
    )
    ids = set()
    for category in categories:
        ids.update(
            env["product.category"].search([("id", "child_of", category.id)]).ids
        )
    return ids


def _sync_line(line):
    """Mirror the source sale line agents into an open invoice line."""
    if not line.sale_line_ids:
        return {"skipped": "sem linha de venda"}
    if any(line.agent_ids.mapped("settled")):
        return {"skipped": "linha com settlement fechado"}
    source = line.sale_line_ids[0]
    expected = {
        agent.agent_id.id: agent for agent in source.agent_ids if agent.commission_id
    }
    current = {agent.agent_id.id: agent for agent in line.agent_ids}
    updated = []
    created = []
    for partner_id, sale_agent in expected.items():
        agent_line = current.get(partner_id)
        values = {
            "commission_id": sale_agent.commission_id.id,
            "commission_split_percent": sale_agent.commission_split_percent,
        }
        if agent_line:
            changed = any(
                agent_line[field] != value
                for field, value in (
                    ("commission_id", sale_agent.commission_id),
                    (
                        "commission_split_percent",
                        sale_agent.commission_split_percent,
                    ),
                )
            )
            if changed:
                values["applied_commission_id"] = False
                values["applied_commission_item_id"] = False
                agent_line.write(values)
                updated.append(agent_line.id)
        else:
            values.update({"object_id": line.id, "agent_id": partner_id})
            created.append(line.env["account.invoice.line.agent"].create(values).id)
    leftover = sorted(set(current) - set(expected))
    return {
        "updated": updated,
        "created": created,
        "leftover": leftover,
    }


def run(cr, commit=True):
    env = api.Environment(cr, SUPERUSER_ID, {})
    extra_ids = _extras_category_ids(env)
    invoices = env["account.move"].search(
        [
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("state", "in", ("draft", "posted")),
            ("payment_state", "in", ("not_paid", "partial")),
        ]
    )
    result = {"lines": [], "skipped": [], "leftover": []}
    for invoice in invoices:
        for line in invoice.invoice_line_ids:
            if (
                line.display_type != "product"
                or not line.product_id
                or line.product_id.categ_id.id not in extra_ids
            ):
                continue
            sync = _sync_line(line)
            if sync.get("skipped"):
                result["skipped"].append((line.id, sync["skipped"]))
                continue
            if sync["updated"] or sync["created"]:
                result["lines"].append(
                    {
                        "invoice": invoice.name or invoice.id,
                        "line": line.id,
                        "updated": sync["updated"],
                        "created": sync["created"],
                    }
                )
            if sync["leftover"]:
                result["leftover"].append((line.id, sync["leftover"]))
    env.flush_all()
    if commit:
        cr.commit()
    return result
