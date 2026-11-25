# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "IOMR Account Invoice Opportunity",
    "summary": "Show the sale order opportunity on invoice lists",
    "version": "18.0.1.0.0",
    "author": "IOMR, Odoo Community Association (OCA)",
    "category": "Accounting & Finance",
    "license": "AGPL-3",
    "depends": [
        "account",
        "sale_crm",
    ],
    "website": "https://github.com/OCA/account-invoicing",
    "maintainers": ["rodrigo-iomr"],
    "data": [
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
