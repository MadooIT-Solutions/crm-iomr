import sys
import os

# Add Odoo to path
sys.path.insert(0, "/home/iomr/odoo")
sys.path.insert(0, "/home/iomr/extra")
sys.path.insert(0, "/home/iomr/extra/crm-iomr")
sys.path.insert(0, "/home/iomr/extra/commission")

import odoo
from odoo import api, SUPERUSER_ID
from odoo.tools import config

if __name__ == "__main__":
    config.parse_config(["--db_host=10.84.10.51", "--db_port=5432",
                         "--db_user=odoo18", "--db_password=Odoo18@2026",
                         "--database=odoo18_prov", "--http-port=0",
                         "--addons-path=/home/iomr/odoo/odoo/addons,/home/iomr/odoo/addons,/home/iomr/extra,/home/iomr/extra/web,/home/iomr/extra/l10n-brazil,/home/iomr/extra/product-attribute,/home/iomr/extra/CybroAddons,/home/iomr/extra/social,/home/iomr/extra/crm-iomr,/home/iomr/extra/server-tools,/home/iomr/extra/knowledge,/home/iomr/extra/dms,/home/iomr/extra/product-configurator,/home/iomr/extra/commission,/home/iomr/extra/sale-workflow,/home/iomr/extra/account-invoicing"])

    odoo.service.server.start(preload=[], stop=True)

    from odoo.modules.registry import Registry

    db_name = "odoo18_prod"
    registry = Registry(db_name)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        
        SaleOrderLine = env["sale.order.line"]
        SaleOrderLineAgent = env["sale.order.line.agent"]

        lines = SaleOrderLine.search([
            ("order_id.doctor_id", "!=", False),
            ("commission_free", "=", False),
        ])

        added = 0
        skipped = 0

        for line in lines:
            doctor = line.order_id.doctor_id
            if not doctor.agent or not doctor.commission_id:
                skipped += 1
                continue

            existing = SaleOrderLineAgent.search_count([
                ("object_id", "=", line.id),
                ("agent_id", "=", doctor.id),
            ])
            if existing:
                skipped += 1
                continue

            line.write({
                "agent_ids": [(0, 0, line._prepare_agent_vals(doctor))]
            })
            added += 1

        print(f"Linhas processadas: {len(lines)}")
        print(f"Médicos adicionados como agentes: {added}")
        print(f"Pulados (já existente ou sem comissão): {skipped}")

        cr.commit()
        print("Alterações salvas no banco!")
