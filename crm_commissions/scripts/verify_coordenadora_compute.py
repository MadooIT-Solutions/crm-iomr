"""
VALIDACAO (transacao com rollback, nada persistido) do compute
coordenadora_id = lider da equipe da orientadora + rotulos neutros.

  /home/iomr/venv/bin/python /home/iomr/odoo/odoo-bin shell \
      -c /home/iomr/odoo/odoo.conf -d odoo18_prod --log-level=warn --no-http \
      < crm_commissions/scripts/verify_coordenadora_compute.py
"""

import logging

_logger = logging.getLogger(__name__)

try:
    Partner = env["res.partner"]

    # ------------------------------------------------------------------
    # 1. Rotulos neutros no registry
    # ------------------------------------------------------------------
    _logger.info("=" * 78)
    _logger.info("1. ROTULOS NEUTROS")
    _logger.info("=" * 78)
    tp = dict(Partner._fields["type_partner"].get_description(env).get("selection") or [])
    # get_description pode nao vir com selection; cai para a definicao crua
    if not tp:
        tp = dict(Partner._fields["type_partner"].selection)
    for key in ("orientadora", "coordenadora", "sdr"):
        _logger.info("  type_partner[%s] = %s", key, tp.get(key))
    at = dict(Partner._fields["agent_type"].selection)
    _logger.info("  agent_type[doctor] = %s", at.get("doctor"))
    Users = env["res.users"]
    cr = dict(Users._fields["crm_role"].selection)
    for key in ("orientadora", "coordenadora", "salesman"):
        _logger.info("  crm_role[%s] = %s", key, cr.get(key))

    # ------------------------------------------------------------------
    # 2. Compute: orientadora ganha a lider da sua equipe
    # ------------------------------------------------------------------
    _logger.info("")
    _logger.info("=" * 78)
    _logger.info("2. COMPUTE coordenadora_id = crm_team.user_id.partner_id")
    _logger.info("=" * 78)

    equipe_orientacao = env.ref("crm_commissions.crm_team_orientacao_cirurgica", raise_if_not_found=False)
    if not equipe_orientacao:
        equipe_orientacao = env["crm.team"].browse(4)  # Orientacao Cirurgica -> Wanessa
    lider = equipe_orientacao.user_id.partner_id
    _logger.info("  Equipe de teste: %s (lider %s / id %s)",
                 equipe_orientacao.name, lider.name, lider.id)

    novo = Partner.create({
        "name": "ORIENTADORA TESTE COMPUTE (rollback)",
        "type_partner": "orientadora",
        "agent": True,
        "crm_team_id": equipe_orientacao.id,
    })
    ok1 = novo.coordenadora_id == lider
    _logger.info("  Criada orientadora na equipe -> coordenadora_id = %s (esperado %s): %s",
                 novo.coordenadora_id.name or "(vazio)", lider.name, "OK" if ok1 else "FALHOU")

    # Troca de equipe muda a coordenadora (recompute)
    outra = env["crm.team"].search([("user_id", "!=", equipe_orientacao.user_id.id), ("user_id", "!=", False)], limit=1)
    if outra:
        novo.crm_team_id = outra.id
        lider2 = outra.user_id.partner_id
        ok2 = novo.coordenadora_id == lider2
        _logger.info("  Trocou p/ equipe %s -> coordenadora_id = %s (esperado %s): %s",
                     outra.name, novo.coordenadora_id.name or "(vazio)",
                     lider2.name, "OK" if ok2 else "FALHOU")
    else:
        ok2 = True
        _logger.info("  (sem segunda equipe com lider para o teste de troca)")

    # Sem equipe -> vazia
    novo.crm_team_id = False
    ok3 = not novo.coordenadora_id
    _logger.info("  Sem equipe -> coordenadora_id = %s (esperado vazio): %s",
                 novo.coordenadora_id.name or "(vazio)", "OK" if ok3 else "FALHOU")

    # Nao-orientadora preserva valor manual
    outra_pessoa = Partner.create({
        "name": "TESTE NAO-ORIENTADORA (rollback)",
        "type_partner": "patient",
    })
    outra_pessoa.coordenadora_id = lider
    outra_pessoa.name = "TESTE NAO-ORIENTADORA 2 (rollback)"  # re-trigger
    ok4 = outra_pessoa.coordenadora_id == lider
    _logger.info("  Nao-orientadora com valor manual preservado: %s",
                 "OK" if ok4 else "FALHOU (valor apagado!)")

    # Orientadoras existentes: nao sairam do nada
    ori_existentes = Partner.search([("type_partner", "=", "orientadora")], limit=5)
    _logger.info("")
    _logger.info("  Orientadoras atuais ( nao modificadas ):")
    for p in ori_existentes:
        _logger.info("      %-20s equipe=%-25s coordenadora=%s",
                     p.name, p.crm_team_id.name or "(sem equipe)",
                     p.coordenadora_id.name or "(vazio)")

    # ------------------------------------------------------------------
    # 3. Patch da taxa de cartao continua carregado
    # ------------------------------------------------------------------
    metodo = env.registry["sale.order.line.agent"]._compute_amount
    deps = list(getattr(metodo, "_depends", None) or [])
    ok5 = any("credit_card_fee_amount" in d for d in deps)
    _logger.info("")
    _logger.info("=" * 78)
    _logger.info("3. PATCH TAXA DE CARTAO: %s", "carregado" if ok5 else "SUMIU!")

    env.cr.rollback()
    _logger.info("")
    _logger.info("RESULTADO: %s (rollback executado, nada persistido)",
                 "TODOS OS TESTES OK" if all((ok1, ok2, ok3, ok4, ok5)) else "HA FALHAS - VER ACIMA")

except Exception as e:
    _logger.error("Erro: %s", e)
    import traceback
    _logger.error(traceback.format_exc())
    env.cr.rollback()
