# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


def migrate(cr, version):
    """Default every existing opportunity to the IOMR sale type.

    ``tipo_venda`` is required and defaults to ``iomr``, but the default only
    applies to new records. Without this the opportunities created before the
    field existed would keep an empty value and block every later edition.
    """
    if not version:
        return
    cr.execute(
        "UPDATE crm_lead SET tipo_venda = 'iomr' WHERE tipo_venda IS NULL"
    )
