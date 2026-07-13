from odoo import api, SUPERUSER_ID


def recompute_agents_for_doctor_orders(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})

    SaleOrderLine = env["sale.order.line"]

    lines = SaleOrderLine.search(
        [
            ("order_id.doctor_id", "!=", False),
            ("commission_free", "=", False),
        ]
    )

    total = len(lines)
    print(f"Encontradas {total} linhas de pedido com doctor_id para recalcular...")

    lines.recompute(["agent_ids"])
    lines.flush(["agent_ids"])

    print(f"Recálculo concluído! {total} linhas atualizadas.")
    return total


if __name__ == "__main__":
    recompute_agents_for_doctor_orders(env.cr)
    # Recompute also orders where doctor_id changed (lines without doctor_id before but now have it)
    # This is handled by the recompute above which processes all current doctor_id orders
