# Configuração de Comissão LIOs

**Localização:** CRM > Comissões > Config. Comissão LIOs
**Modelo:** commission (herdado de commission_oca)
**Grupo:** Apenas CRM Commission Manager

## Propósito

Definir as regras de comissionamento para LIOs (Lentes Intraoculares) e outros produtos, incluindo:
- Tipo de comissão (fixa, seccionada ou progressiva)
- Taxas progressivas por faixa de performance
- Parâmetros do IS-CRM (bônus e penalidade)
- Margem mínima e desconto máximo

## Campos

| Campo | Descrição |
|-------|-----------|
| Name | Nome da regra de comissão |
| Commission Type | Fixa, Seccionada, **Progressiva por performance** |
| Progressive Lines | Faixas de taxa progressiva |
| IS-CRM Bonus (%) | Percentual de bônus quando IS-CRM >= 95% (padrão: 0,25%) |
| IS-CRM Penalty (%) | Percentual de penalidade quando IS-CRM < 95% (padrão: 0,25%) |
| Min Margin (%) | Margem mínima para validação da comissão (padrão: 35%) |
| Max Discount (%) | Desconto máximo sem aprovação gerencial (padrão: 5%) |

### Faixas de Taxa Progressiva (Progressive Lines)

Para cada faixa, defina:

| Campo | Descrição |
|-------|-----------|
| Sequence | Ordem de avaliação |
| Performance From | Início da faixa de performance (%) |
| Performance To | Fim da faixa de performance (%) |
| Commission Rate | Taxa de comissão aplicada na faixa (%) |

## Dados Padrão (2026)

| Faixa de Performance | Taxa |
|---------------------|------|
| 0% a 50% | 0,25% |
| 51% a 80% | 0,45% |
| 81% a 100% | 0,75% |
| 101% a 120% | 1,25% |
| Acima de 120% | 1,75% |

IS-CRM: Bônus 0,25% | Penalidade 0,25% | Mínimo 95%
