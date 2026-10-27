# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


def migrate(cr, version):
    """Carry the values from ``tipo_venda`` into the renamed field.

    The field was renamed to ``tipo_paciente``. Odoo creates the new column
    with the default (``iomr``), so any opportunity manually set to ``externo``
    would be lost without copying the old column first. The old column is left
    in place (unused) to keep the migration non destructive.
    """
    if not version:
        return
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'crm_lead'
           AND column_name = 'tipo_venda'
        """
    )
    if not cr.fetchone():
        return
    cr.execute(
        "UPDATE crm_lead SET tipo_paciente = tipo_venda "
        "WHERE tipo_venda IS NOT NULL"
    )
