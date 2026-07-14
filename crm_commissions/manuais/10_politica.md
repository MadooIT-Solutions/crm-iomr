# Política de Comissionamento

**Localização:** Comissionamento > Política
**Modelo:** commission.policy
**Grupo:** Apenas Commission Manager

## Propósito

Definir as políticas de comissionamento que determinam as faixas de taxa aplicáveis com base na performance da orientadora. Cada política possui faixas de performance com taxas específicas, além de parâmetros de margem mínima, desconto máximo e IS-CRM.

## Campos do Formulário

### Cabeçalho
| Campo | Descrição |
|-------|-----------|
| Name | Nome da política (ex: "Política 2026") |
| Date Start | Data de início de vigência |
| Date End | Data de fim de vigência (opcional) |
| Active | Ativa |

### Parâmetros
| Campo | Descrição |
|-------|-----------|
| Min Margin (%) | Margem mínima obrigatória (padrão: 35%) |
| Min CRM Score (%) | IS-CRM mínimo para bônus (padrão: 95%) |
| Max Discount (%) | Desconto máximo permitido sem aprovação (padrão: 5%) |
| CRM Bonus Rate (%) | Bônus quando IS-CRM >= mínimo (padrão: 0,25%) |
| CRM Penalty Rate (%) | Penalidade quando IS-CRM < mínimo (padrão: 0,25%) |

### Faixas de Taxa (Aba Rate Bands)
| Campo | Descrição |
|-------|-----------|
| Sequence | Ordem |
| Delivery % From | Início da faixa |
| Delivery % To | Fim da faixa |
| Base Rate (%) | Taxa de comissão aplicada |

## Como criar

1. Vá para **Comissionamento > Política**
2. Clique em **Criar**
3. Dê um **nome** à política (ex: "Política 2026")
4. Defina a **data de início**
5. Configure os parâmetros de margem, IS-CRM e desconto
6. Na aba **Rate Bands**, adicione as faixas de performance:
   - Informe a sequência
   - Defina o intervalo de performance (From - To)
   - Informe a taxa base
7. Salve

## Exemplo de Faixas (Política 2026)

| Sequência | Performance | Taxa Base |
|-----------|-------------|-----------|
| 10 | 0% - 50% | 0,25% |
| 20 | 51% - 80% | 0,45% |
| 30 | 81% - 100% | 0,75% |
| 40 | 101% - 120% | 1,25% |
| 50 | > 120% | 1,75% |

## Funcionamento

1. Ao calcular um resultado (`commission.result`), a política ativa é identificada.
2. A performance da orientadora é comparada com as faixas.
3. A taxa base é definida pela faixa correspondente.
4. O bônus/penalidade IS-CRM é aplicado sobre a taxa base.
5. A taxa final = taxa base + bônus (ou - penalidade).
