# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Remove linhas de fechamento já existentes com valor zerado.

    Essas linhas vinham de adiantamentos/entradas sem comissão e ficavam
    escondidas na tela, mas continuavam poluindo a lista. Como valem zero,
    removê-las não altera o total de nenhuma liquidação.

    A exclusão é feita por SQL para não disparar o recompute do ``total``:
    alguns fechamentos antigos têm um total histórico que não deve ser
    reescrito por uma limpeza cosmética da lista de linhas.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    zero_lines = env["commission.settlement.line"].search(
        [
            ("settled_amount", ">=", -0.005),
            ("settled_amount", "<=", 0.005),
        ]
    )
    if not zero_lines:
        return
    line_ids = zero_lines.ids
    cr.execute(
        "DELETE FROM commission_settlement_line WHERE id = ANY(%s)", (line_ids,)
    )
    _logger.info("Removidas %d linhas de liquidação com valor zero", len(line_ids))
