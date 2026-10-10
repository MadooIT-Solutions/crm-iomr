"""VALIDACAO (rollback, nada persistido) da sincronizacao crm_role -> type_partner.

  /home/iomr/venv/bin/python /home/iomr/odoo/odoo-bin shell \
      -c /home/iomr/odoo/odoo.conf -d odoo18_prod --log-level=info --no-http \
      < crm_commissions/scripts/verify_crm_role_type_partner.py
"""
import logging

_logger = logging.getLogger(__name__)

try:
    Users = env["res.users"]
    Partner = env["res.partner"]

    def probe(role, current_type):
        """Cria usuario+partner com type atual, atribui crm_role e le o tipo."""
        p = Partner.create({
            "name": f"TST SYNC {role or 'vazio'} ({current_type})",
            "type_partner": current_type,
        })
        u = Users.create({
            "login": f"tst_sync_{role or 'vazio'}_{current_type}",
            "name": p.name,
            "partner_id": p.id,
            "type_partner": current_type,
        })
        u.crm_role = role  # dispara o inverse
        got = u.partner_id.type_partner
        return got

    # (role esperado, tipo_inicial, tipo_esperado)
    casos = [
        ("sdr", "others", "sdr"),
        ("orientadora", "others", "orientadora"),
        ("coordenadora", "others", "coordenadora"),
        ("doctor", "doctorint", "doctorint"),   # preserva interno
        ("doctor", "doctorext", "doctorext"),   # preserva externo
        ("doctor", "others", "doctorext"),      # assume externo
        ("salesman", "others", "employee"),
        ("sale_manager", "others", "employee"),
        ("commission_user", "others", "employee"),
        ("manager", "others", "employee"),
        ("readonly", "others", "employee"),
        (False, "patient", "patient"),          # funcao vazia nao mexe
    ]

    _logger.info("=" * 70)
    _logger.info("SINCRONIZACAO crm_role -> type_partner")
    _logger.info("=" * 70)
    todos_ok = True
    for role, inicial, esperado in casos:
        got = probe(role, inicial)
        ok = got == esperado
        todos_ok = todos_ok and ok
        _logger.info("  %-16s inicial=%-9s -> %-9s (esp %-9s) %s",
                     role or "(vazio)", inicial, got, esperado,
                     "OK" if ok else "FALHOU")

    env.cr.rollback()
    _logger.info("")
    _logger.info("RESULTADO: %s (rollback)",
                 "TODOS OK" if todos_ok else "HA FALHAS")
except Exception as e:
    import traceback
    _logger.error("Erro: %s", e)
    _logger.error(traceback.format_exc())
    env.cr.rollback()
