# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Reconstrói a origem das linhas de comissão já fechadas.

O formulário de settlement passou a mostrar, em cada linha de comissão, de
onde ela veio: a meta mensal (``target_id``), o bônus trimestral
(``quarterly_bonus_id``) ou o pedido de venda. Os dois primeiros são gravados
na criação da linha pelo wizard de fechamento, então as linhas lançadas antes
desses campos existirem ficaram sem origem e as colunas apareciam vazia -- o
mesmo caso do backfill do ``18.0.1.4.0``.

O pedido de venda não precisa de backfill: ``sale_order_id`` é calculado a
cada leitura, subindo da linha da fatura até ``sale_line_ids`` e daí ao
pedido.

Roda como *pós*-migração porque os dois syncs vivem nos modelos deste
módulo.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    targets = env["crm.commission.target"]
    targets._sync_settlement_line_targets()
    targets._sync_settlement_line_quarterly_bonuses()
    lines = env["commission.settlement.line"].sudo()
    still_without_origin = lines.search(
        [
            "|",
            "&",
            ("target_id", "=", False),
            ("settlement_id.settlement_type", "=", "crm_performance"),
            "&",
            ("quarterly_bonus_id", "=", False),
            (
                "settlement_id.settlement_type",
                "=",
                "crm_quarterly_recovery",
            ),
        ]
    )
    if still_without_origin:
        _logger.warning(
            "%s linha(s) fechada(s) do CRM continuam sem origem (meta ou "
            "bônus) e as colunas ficarão vazias. Ids: %s",
            len(still_without_origin),
            still_without_origin.ids,
        )
