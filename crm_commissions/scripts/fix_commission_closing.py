# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Repara fechamentos de comissão já existentes (duplicados e valores).

A migração ``18.0.2.9.5`` faz a mesma reparação durante a atualização do
módulo. Este script existe para quem precisa rodar a correção em produção sem
atualizar o módulo, e é idempotente.

O que ele faz:

1. Preenche ``invoice_line_id`` nas linhas de fechamento antigas e religa as
   linhas órfãs ao agente atual, quando existe um único candidato.
2. Congela a base da comissão de fatura em ``invoice_base_amount``, para que o
   valor não seja zerado quando o ``amount`` do agente for recalculado.
3. Recria as linhas de detalhe de ``commission.sale`` que faltavam nos meses
   antigos (sem tocar em vendas que já têm detalhes).
4. Recalcula as linhas de CRM Performance ainda em valor zero e não faturadas.

Uso (odoo shell, da raiz do repo). O servidor precisa estar com o código novo
carregado (basta reiniciar; não é obrigatório rodar ``-u`` antes). Por
segurança o padrão é DRY_RUN: nada é gravado. Confira o relatório, mude
``DRY_RUN`` para ``False`` e rode de novo:

    /home/iomr/venv/bin/python /home/iomr/odoo/odoo-bin shell \
        -c /home/iomr/odoo/odoo.conf -d odoo18_prod --log-level=info --no-http \
        < crm_commissions/scripts/fix_commission_closing.py
"""

import importlib.util
import logging
import os

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

DRY_RUN = True
MIGRATION_VERSION = "18.0.2.9.5"


def _load_migration():
    """Load the post-migration module that holds the repair functions."""
    from odoo.addons import crm_commissions

    migration_path = os.path.join(
        os.path.dirname(crm_commissions.__file__),
        "migrations",
        MIGRATION_VERSION,
        "post-migrate.py",
    )
    spec = importlib.util.spec_from_file_location(
        "crm_commissions_fix_closing", migration_path
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def run(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})
    migration = _load_migration()

    # The script may run before ``-u crm_commissions``; in that case the new
    # column does not exist yet. Create it inside the transaction (rolled back
    # on DRY_RUN) so the repair can be evaluated safely.
    env.cr.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'commission_settlement_line' "
        "AND column_name = 'invoice_base_amount'"
    )
    if not env.cr.fetchone():
        env.cr.execute(
            "ALTER TABLE commission_settlement_line "
            "ADD COLUMN invoice_base_amount numeric"
        )
        env.invalidate_all()

    invoice_lines = migration._backfill_invoice_line(env)
    invoice_base = migration._backfill_invoice_base(env)
    relinked, ambiguous = migration._relink_orphan_settlement_lines(env)
    synced, failed = migration._resync_commission_sales(env)
    invoice_updated = migration._recompute_invoice_lines(env)
    crm_updated = migration._recompute_crm_lines(env)

    _logger.info("=" * 78)
    _logger.info("REPARO DO FECHAMENTO DE COMISSÕES (DRY_RUN=%s)", DRY_RUN)
    _logger.info("  invoice_line_id preenchido: %s", invoice_lines)
    _logger.info("  base da fatura congelada: %s", invoice_base)
    _logger.info("  linhas órfãs religadas: %s", relinked)
    _logger.info("  linhas órfãs ambíguas (revisar): %s", ambiguous)
    _logger.info("  vendas de comissão ressincronizadas: %s", synced)
    _logger.info("  falhas de ressincronização: %s", failed)
    _logger.info("  linhas de fatura recalculadas: %s", invoice_updated)
    _logger.info("  linhas de CRM zeradas recalculadas: %s", crm_updated)
    _logger.info("=" * 78)
    if DRY_RUN:
        cr.rollback()
        _logger.info("DRY_RUN: nenhuma alteração gravada (rollback).")
    else:
        cr.commit()
        _logger.info("Alterações gravadas.")


try:
    run(env.cr)  # noqa: F821 - provided by odoo shell
except Exception:
    _logger.exception("Falha no reparo do fechamento de comissões")
    env.cr.rollback()  # noqa: F821 - provided by odoo shell
    raise
