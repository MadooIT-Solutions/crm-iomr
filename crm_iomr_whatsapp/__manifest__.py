{
    "name": "CRM IOMR WhatsApp",
    "version": "18.0.1.0.0",
    "category": "Sales/CRM",
    "summary": "Adds new salesperson to WhatsApp channel on user change",
    "author": "Rodrigo A. Madureira",
    "company": "Madooit IT Solutions",
    "maintainer": "Madooit IT Solutions",
    "website": "https://www.madooit.com",
    "depends": [
        "crm",
        "mail_gateway_whatsapp_chatter",
        "crm_iomr_auto",
        "crm_commissions",
    ],
    "data": [
        "security/crm_iomr_whatsapp_security.xml",
    ],
    "license": "AGPL-3",
    "installable": True,
    "application": False,
    "auto_install": False,
}
