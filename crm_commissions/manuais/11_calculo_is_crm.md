# Cálculo do IS-CRM (Índice de Saúde CRM)

## O que é o IS-CRM?

O **IS-CRM** (Índice de Saúde CRM / CRM Health Index) é um indicador de 0% a 100% que mede a qualidade do gerenciamento das oportunidades e vendas no CRM. Ele reflete o quão bem a orientadora está conduzindo seus processos comerciais.

Um IS-CRM **>= 95%** gera um **bônus** na comissão.
Um IS-CRM **< 95%** gera uma **penalidade** na comissão.

## Onde o IS-CRM é definido?

O IS-CRM pode ser definido em vários níveis:

### 1. Na Venda (commission.sale)
- Campo: **IS-CRM (%)** (crm_pct)
- Padrão: 100%
- Editável manualmente pela orientadora ao registrar a venda
- Permite ajustar o score para cada venda individualmente

### 2. Na Meta Mensal (crm.commission.target)
- Campo: **IS-CRM Score** (is_crm_score)
- Padrão: 100%
- Pode ser ajustado manualmente
- O campo **IS-CRM OK** indica se o score >= 95%

### 3. No Resultado (commission.result)
- Campo: **IS-CRM Score** (is_crm_score)
- **Calculado automaticamente** como a média dos IS-CRM scores de todas as vendas do período
- Fórmula: `is_crm_score = soma dos crm_pct das vendas / quantidade de vendas`
- Se não houver vendas no período, o score é 100%

### 4. Na Oportunidade (crm.lead)
- Campo: **IS-CRM Score** (is_crm_score)
- Padrão: 100%
- Editável manualmente

### 5. No Pedido de Venda (sale.order)
- Campo: **IS-CRM Score** (is_crm_score)
- Padrão: 100%
- Editável manualmente

## Como o IS-CRM afeta a comissão?

### Fluxo completo:

```
Vendas do Período (commission.sale)
  → Média do IS-CRM de todas as vendas
  → IS-CRM Score do Resultado (commission.result)
  → Comparação com o mínimo da política (crm_min_pct = 95%)
  → Se >= 95%: Bônus (+) aplicado à taxa base
  → Se < 95%: Penalidade (-) aplicada à taxa base
  → Taxa Final = Taxa Base + Bônus (ou - Penalidade)
  → Comissão = Base de Cálculo × Taxa Final
```

### Cálculo da Taxa Final:

```python
taxa_final = taxa_base + taxa_bonus_crm

# Onde:
# taxa_bonus_crm = política.crm_bonus_rate (ex: 0,25%) se IS-CRM OK
# taxa_bonus_crm = -política.crm_penalty_rate (ex: -0,25%) se IS-CRM não OK
```

### Exemplo 1: IS-CRM OK (score 98%)

| Parâmetro | Valor |
|-----------|-------|
| Performance | 90% |
| Faixa | 81% a 100% |
| Taxa Base | 0,75% |
| IS-CRM Score | 98% (>= 95%) |
| Bônus | +0,25% |
| Taxa Final | 1,00% |
| Base de Cálculo | R$ 100.000 |
| Comissão | R$ 1.000 |

### Exemplo 2: IS-CRM não OK (score 72%)

| Parâmetro | Valor |
|-----------|-------|
| Performance | 90% |
| Faixa | 81% a 100% |
| Taxa Base | 0,75% |
| IS-CRM Score | 72% (< 95%) |
| Penalidade | -0,25% |
| Taxa Final | 0,50% |
| Base de Cálculo | R$ 100.000 |
| Comissão | R$ 500 |

## Parâmetros configuráveis

Os parâmetros do IS-CRM são configuráveis em dois lugares:

### 1. Na Comissão (Config. Comissão LIOs)
| Campo | Padrão |
|-------|--------|
| IS-CRM Bonus (%) | 0,25% |
| IS-CRM Penalty (%) | 0,25% |

### 2. Na Política de Comissionamento
| Campo | Padrão |
|-------|--------|
| Min CRM Score (%) | 95% |
| CRM Bonus Rate (%) | 0,25% |
| CRM Penalty Rate (%) | 0,25% |

## Comissão Progressiva com IS-CRM

Quando o tipo de comissão é **Progressiva**, o cálculo inclui o IS-CRM:

```python
comissao = base * (taxa_progressiva / 100)
if is_crm_ok:
    comissao += base * (is_crm_bonus / 100)     # bônus
else:
    comissao -= base * (is_crm_penalty / 100)    # penalidade

comissao = max(comissao, 0)  # nunca negativa
```

## Dicas

- Mantenha o IS-CRM das vendas sempre atualizado para refletir a real qualidade do processo.
- Um IS-CRM baixo impacta diretamente o valor da comissão.
- O score de 100% é o padrão e deve ser ajustado quando houver não conformidades.
- A meta mínima de 95% e as taxas de bônus/penalidade podem ser alteradas na política.
