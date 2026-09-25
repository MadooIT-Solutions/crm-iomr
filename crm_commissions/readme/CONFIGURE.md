1. Go to *CRM > Config. Comissão LIOs* to configure the progressive commission
   and its rate bands. These rates are also used to calculate quarterly
   recovery.
2. Configure the IS-CRM bonus and penalty percentages and the active 2026
   policy.
3. Create Orientadora, SDR, and Coordenadora profiles in *Contacts*.
4. Make sure each Orientadora has a *commission.member* record and the correct
   commission rule. Confirmed orders are synchronized to *commission.sale* and
   provide the eligible base used in quarterly recovery.
5. Create sales teams and add their Orientadoras under *CRM Comissões >
   Equipes*.
6. Register one monthly target per Orientadora under *CRM Comissões > Metas
   Mensais*. In team mode, use *Aplicar à Equipe* to create one individual target
   for every team member.
7. Review *CRM Comissões > Bônus Trimestrais*. The module creates the quarterly
   record automatically after the first monthly target, keeps one record per
   salesperson/quarter, and backfills existing targets when upgraded.
8. The scheduled action *CRM Comissões: sincronizar e fechar bônus trimestrais*
   runs daily. It refreshes sales totals and finalizes closed quarters; no
   manual creation is required.
9. The special prize has no monetary formula in the policy. After eligibility is
   confirmed, manually enter its amount, type, and description.
