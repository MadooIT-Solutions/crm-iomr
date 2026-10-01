# Análise — Meta e Bônus Trimestral

**Fontes analisadas**

- `Politica de Comissionamento 2026, Sua Performance, Nosso Sucesso.pdf` (páginas 7, 9, 10 e 11)
- `models/crm_commission_models.py` — classes `CommissionTarget` e `CommissionQuarterlyBonus`
- `data/crm_quarterly_bonus_cron.xml`
- Banco `crmcomm_fix` (clone de teste de `crmcomm_e2e`)

---

## Resposta direta

**Não.** Não existe, nem na política nem no sistema, uma regra de somatória da equipe com distribuição igual para a meta trimestral.

A distribuição igual existe na política, mas para **comissão sobre venda compartilhada** — não para meta.

> **Decisão registrada:** a construção da meta trimestral permanece baseada nas
> **metas individuais**. Ver seção 5.1. O comportamento vigente já atende a isso e
> **nenhuma alteração de código foi necessária**.

---

## 1. O que a política estabelece

### Meta trimestral = soma dos meses, individual por pessoa

Página 10, "METAS TRIMESTRAIS":

| Trimestre | Mês 1 | Mês 2 | Mês 3 | META TOTAL |
|---|---|---|---|---|
| **Q1** | Jan 414.667,00 | Fev 351.814,00 | Mar 495.243,00 | **1.261.724,00** |
| **Q2** | Abr 504.735,00 | Mai 330.197,00 | Jun 369.204,00 | **1.204.136,00** |
| **Q3** | Jul 589.939,00 | Ago 517.472,00 | Set 456.091,00 | **1.563.502,00** |
| **Q4** | Out 446.035,00 | Nov 608.469,00 | Dez 46.642,00 | **1.101.146,00** |

Meta anual total: **R$ 5.130.508,00**

Valores conferidos: os quatro `META TOTAL` batem exatamente com a soma dos três meses, e o anual fecha com a soma dos quatro trimestres.

Página 3 explicita que a meta é individual:

> "Meta mensal comunicada individualmente pela gestão no início de cada ciclo."

### Onde a política fala em "igual"

Página 7, "OPORTUNIDADES COMPARTILHADAS" — único uso de rateio igual:

> "Vendas que envolvem múltiplas Orientadoras têm comissão rateada igualmente entre os participantes registrados."
> "Valor dividido igualmente entre todos os colaboradores que atuaram na jornada do cliente."

Exemplo do PDF: comissão de 1% sobre venda com Orientadora A, B, C e SDR → 0,25% para cada.

> Isso é rateio de **comissão sobre uma venda específica**. Não tem relação com meta mensal ou trimestral.

### O gatilho do bônus, segundo a política

Página 9, "BÔNUS DE QUARTER":

> "Ao bater a meta do quarter, os Orientadores recebem um bônus especial."
> "A Coordenadora também participa do bônus se a equipe atingir a meta coletiva do trimestre."

E a recuperação de comissão:

> "Se o vendedor não bater 100% em algum mês, mas ao final do quarter cobrir a meta total trimestral, os percentuais perdidos nos meses anteriores são devolvidos integralmente."
>
> Exemplo Q1: Jan 0,70% (−0,30%) → Fev 0,70% (−0,30%) → Mar meta coberta → **+0,60% devolvidos**

Página 11 repete: "Se a equipe bater a meta total do Q1, a Coordenadora participa do prêmio extra junto com os Orientadores."

**Leitura:** "meta total trimestral" = o número único da tabela da página 10 (R$ 1.261.724 no Q1).

---

## 2. O que o sistema faz

### A meta trimestral não é digitada

`crm.commission.quarterly.bonus` não tem campo de valor editável. `total_target`, `total_achieved`, `quarterly_pct`, `bonus_amount` e `lost_commission_recovered` são todos `compute` + `store`, derivados de `monthly_targets`.

O único dado informado é o par `agent_id` + `year` + `quarter`.

### Registro: um por pessoa por trimestre

```
_sql_constraints = [("unique_agent_quarter", "UNIQUE (agent_id, year, quarter)", ...)]
```

Criado por `_sync_for_keys()` (linha 1131), acionado por três caminhos:

1. `crm.commission.target.create()`
2. `crm.commission.target.write()`
3. cron `cron_crm_quarterly_bonus_daily` (diário, 00:05) + `post_init_hook`

Gatilho — `_get_quarterly_bonus_keys()` (linha 345) coleta apenas registros com `target_scope == 'salesperson'`:

```python
targets = search([
    ("target_scope", "=", "salesperson"),
    ("agent_id", "=", agent_id),
    ("target_date", ">=", date_from),
    ("target_date", "<=", date_to),
])
bonus.create({**values, "agent_id": agent_id, "year": year,
              "quarter": quarter, "auto_generated": True})
```

`monthly_targets` é gravado como `(6, 0, targets.ids)` — **sobrescreve** a lista a cada sync.

**Consequência:** metas de equipe (`target_scope == 'team'`) nunca geram bônus diretamente. Elas viram individuais em `action_apply_team()` e aí sim entram.

### Teste real executado

3 meses de meta de equipe com `split_team_target=True`, 2 pessoas, R$ 30.000/mês:

```
id  partner   year  qtr  from        to          auto  state  n  all3  total_target  achieved
75  Q Ori 1   2026  Q1   2026-01-01  2026-03-31  True  lost   3  True   45.000,00    0,00
76  Q Ori 2   2026  Q1   2026-01-01  2026-03-31  True  lost   3  True   45.000,00    0,00

metas vinculadas ao bonus 75:
  Q Ori 1 | 2026-01-01 | 15.000,00
  Q Ori 1 | 2026-02-01 | 15.000,00
  Q Ori 1 | 2026-03-01 | 15.000,00
```

Confirma: 30.000 dividido por 2 = 15.000 por pessoa por mês → 45.000 no trimestre.

`state = lost` porque `achieved_amount` é 0 (não havia vendas). O fechamento ocorreu por `_finalize_if_closed()`, que roda no fim do próprio `_sync_for_keys()`.

---

## 3. Divergências entre sistema e política

### 3.1 `is_team_eligible` compara contra a meta errada — **impacto alto**

`_compute_team_totals()` (linha 1049) calculou `is_team_eligible` com:

```python
agent_ids = self.env["crm.commission.target"]._get_team_member_partners(team).ids
targets = search([("agent_id", "in", agent_ids),
                  ("target_date", ">=", rec.date_from),
                  ("target_date", "<=", rec.date_to)])
rec.team_total_target = sum(targets.mapped("target_amount"))
...
rec.is_team_eligible = bool(rec.is_finalized and len(target_months) == 3
                           and rec.team_total_target
                           and rec.team_total_achieved >= rec.team_total_target)
```

**Problema:** `team_total_target` soma a meta de **todo mundo** da equipe.

Com 4 orientadoras onde cada uma tem R$ 1.261.724 no Q1:

| | Valor |
|---|---|
| Meta da equipe no sistema | 4 × 1.261.724 = **R$ 5.046.896** |
| Meta da equipe na política (pág. 10) | **R$ 1.261.724** |
| Excesso exigido | **4×** |

A coleção necessária para o bônus disparar é 4 vezes o alvo real. **Na prática o bônus da coordenadora quase nunca é elegível.**

**Correção necessária:** existe um campo de meta de equipe do trimestre? Não. Precisa ser criado e preenchido com o valor da tabela da página 10, para então comparar `team_total_achieved` contra ele.

### 3.2 A divisão de meta recém-implementada diverge da política — **decisão de negócio**

O campo `split_team_target` ("Dividir meta para equipe") pega um total e reparte igualmente.

A política diz que a meta mensal é **individual**, comunicada pela gestão. Dividir um total de equipe gera meta por pessoa diferente da tabela da página 10.

Para casar com o PDF: cadastrar a meta de cada pessoa direto, sem dividir.

**Isto não é bug.** É uma funcionalidade nova, útil para outro fluxo de trabalho. Mas as duas abordagens não podem ser misturadas sem saber a intenção.

### 3.3 Consequência prática do item 3.1 + 3.2 juntos

Com `split_team_target` ligado, a soma da equipe cresce pelo número de pessoas, o que agrava a desproporção de 3.1: o `team_total_target` passa a ser N × (total ÷ N) = total, o que *parece* correto por coincidência matemática — **mas apenas se todos os membros estiverem incluídos**. Se alguém for pulado, o valor volta a ser inflado.

---

## 4. Pontos de atenção no código

### 4.1 Fechamento é por data, irreversível

`_finalize_if_closed()` (linha 1288) fecha assim que `date_to < hoje`:

- 3 meses presentes + `achieved >= target` → `eligible` ou `recovered`
- menos de 3 meses → `incomplete`
- abaixo do target → `lost`

`is_finalized` passa a `True` e **não há como reabrir**.

### 4.2 Registro manual é órfão por construção

Em `_sync_for_keys`, duplicados e bônus sem metas são apagados **apenas se `auto_generated` e não `is_finalized`**.

`_sync_all_quarterly_bonuses()` (linha 444) aceita chaves de registros com `monthly_targets` vazio, permitindo registro manual. Mas esse registro fica sem metas → `total_target = 0` → `is_eligible` nunca verdadeiro.

### 4.3 Dependência não resolvida no ambiente

```
ERROR odoo.modules.loading: Some modules are not loaded, some dependencies
or manifest may be missing: ['l10n_br_sale_credit_card_fee']
ERROR odoo.modules.registry: Model crm.sale.order.monthly has no table.
```

Não afeta a análise, mas aparece em toda execução de teste.

---

## 5. Decisões do negócio

### 5.1 Meta trimestral permanece sobre as metas individuais — **CONFIRMADO**

> **Decisão:** manter a construção da meta trimestral baseada nas metas
> individuais.

Esta é a decisão que governa todo o restante do documento. Ela settles as
dúvidas das seções 3.2 e 3.3 e **não requer alteração de código**.

O que isso significa na prática:

| | Comportamento |
|---|---|
| Unidade de construção | Meta mensal **individual** (`target_scope = 'salesperson'`) |
| Meta trimestral | Soma das 3 metas mensais da mesma pessoa |
| Meta da equipe | Não é uma entidade independente; é a agregação das metas individuais |
| Bônus individual | Calculado sobre `total_target` da pessoa |
| `_get_quarterly_bonus_keys()` | Mantido: agrupa por `agent_id` + ano + trimestre |

A entrada do usuário permanece sendo a **meta mensal de cada pessoa**. O
trimestre é sempre derivado — nunca digitado.

O `split_team_target` ("Dividir meta para equipe") **permanece disponível** como
forma de cadastro em lote. Ele continua sendo apenas um atalho de digitação:
produz metas individuais a partir de um total, e o trimestre é montado a partir
dessas individuais. Não muda a regra de construção.

### 5.2 Efeito sobre as divergências

Com essa decisão, os itens 3.1 a 3.3 ficam assim:

- **3.1** (`is_team_eligible`) — permanece como está. A agregação da equipe é a
  soma das metas individuais por definição, o que é auto-consistente com o item
  5.1. A diferença em escala em relação à tabela da página 10 fica
  **documentada como decisão**, não como bug. Ver ressalva em 5.3.
- **3.2** (divisão de meta) — o `split_team_target` continua existindo como
  ferramenta de cadastro em lote. Ele gera metas individuais a partir de um
  total, e o trimestre segue sendo a soma dessas individuais. Não conflita com o
  item 5.1: a divisão acontece na **entrada**, não na construção do trimestre.
- **3.3** — sem efeito. A observação sobre a coincidência matemática
  N × (total ÷ N) = total segue válida e serve apenas como alerta de
  consistência dos dados.

### 5.3 Ressalva que fica em aberto

Escolher metas individuais como base **não resolve** a diferença de escala com a
página 10 do PDF. As duas coisas são independentes:

- **Como o trimestre é construído** → somatório das mensais individuais (decidido)
- **Qual número a equipe precisa coletar** → R$ 1.261.724 no Q1 (política)

Se a tabela da página 10 representa o alvo **coletivo** da equipe, então o
`is_team_eligible` atual exige uma coleção 4× maior com 4 orientadoras. Isso só
se resolve com um campo de meta coletiva por trimestre — uma decisão separada
da que foi tomada agora, que fica registrada aqui caso venha a ser discutida.

### 5.4 Recomendações restantes

| # | Ação | Prioridade |
|---|---|---|
| 1 | Atualizar `readme/`, que ainda descreve o comportamento antigo das metas de equipe | Baixa |
| 2 | Documentar a meta por pessoa no cadastro manual, para evitar divergência da tabela da página 10 | Média |
| 3 | Avaliar se vale permitir reabrir um trimestre já fechado | Média |
| 4 | Remover ou documentar o caminho de registro manual de bônus | Média |

**Nada no código muda.** As implementações de
`_get_quarterly_bonus_keys()`, `_sync_for_keys()` e `_compute_totals()` já
operam sobre metas individuais e permanecem como estão.

---

## 6. Registro de decisão

| Data | Decisão | Origem |
|---|---|---|
| 2026-09-30 | Manter a construção da meta trimestral baseada nas metas individuais | Usuário |

**Impacto em código: nenhum.** O comportamento vigente já atende à decisão —
nenhuma das funções que constroem o trimestre foi alterada.

---

## 7. Referência de código

| Assunto | Local |
|---|---|
| Registro do bônus | `models/crm_commission_models.py:1131` `_sync_for_keys()` |
| Chaves por pessoa/trimestre | `models/crm_commission_models.py:345` `_get_quarterly_bonus_keys()` |
| Cron diário | `data/crm_quarterly_bonus_cron.xml` |
| Totais individuais | `models/crm_commission_models.py:995` `_compute_totals()` |
| Totais da equipe | `models/crm_commission_models.py:1049` `_compute_team_totals()` |
| Fechamento do trimestre | `models/crm_commission_models.py:1288` `_finalize_if_closed()` |
| Recuperação de comissão | `models/crm_commission_models.py:1273` `_calculate_lost_commission()` |
| Divisão de meta | `models/crm_commission_models.py:656` `_split_team_target_amount()` |
| Membros da equipe | `models/crm_commission_models.py:598` `_get_team_member_partners()` |

### Testes

| Arquivo | Cobertura |
|---|---|
| `tests/test_quarterly_bonus.py` | Elegibilidade, meses faltantes, recuperação, duplicados |
| `tests/test_target_team.py` | 24 casos: aplicação em equipe, divisão, confirmação de conflito |

Suíte completa do módulo: **114/115**. A falha restante
(`TestQuarterlyBonus.test_closed_quarter_recovers_lost_rate_points`,
`3360.0 != 3000.0`) foi confirmada como pré-existente, sem relação com as
alterações de meta de equipe.