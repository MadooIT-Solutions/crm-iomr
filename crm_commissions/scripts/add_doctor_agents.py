from odoo import api, SUPERUSER_ID


def add_doctors_as_agents(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})

    SaleOrderLine = env["sale.order.line"]
    SaleOrderLineAgent = env["sale.order.line.agent"]

    lines = SaleOrderLine.search(
        [
            ("order_id.doctor_id", "!=", False),
            ("commission_free", "=", False),
        ]
    )

    added = 0
    skipped = 0

    for line in lines:
        doctor = line.order_id.doctor_id
        if not doctor.agent or not doctor.commission_id:
            skipped += 1
            continue

        existing = SaleOrderLineAgent.search_count(
            [
                ("object_id", "=", line.id),
                ("agent_id", "=", doctor.id),
            ]
        )
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
    return added


def run(cr):
    result = add_doctors_as_agents(cr)
    cr.commit()
    return result
