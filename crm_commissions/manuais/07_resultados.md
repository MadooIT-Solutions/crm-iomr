# Resultados (Comissionamento)

**Localização:** Comissionamento > Resultados
**Modelo:** commission.result

## Propósito

Calcular mensalmente a comissão devida a cada orientadora com base nas vendas registradas, metas, política de comissionamento e IS-CRM.

## Campos do Formulário

### Cabeçalho
| Campo | Descrição |
|-------|-----------|
| Name | Nome (calculado: Membro - Mês/Ano) |
| Member | Membro da equipe (orientadora) |
| Period Code | Mês de referência (YYYY-MM) |
| Policy | Política de comissionamento aplicada |
| Target | Meta do período |
| Target Amount | Valor da meta |
| State | Draft, Calculated, Approved, Paid |

### Valores de Vendas
| Campo | Descrição |
|-------|-----------|
| LIO Sales Amount | Total de vendas de LIO no período |
| Hospital Sales Amount | Total de vendas hospitalares no período |
| Delivery (%) | Percentual de entrega (realizado / meta × 100) - calculado |

### Taxas
| Campo | Descrição |
|-------|-----------|
| Range Label | Faixa de performance atingida (ex: "81% a 100%") |
| Base Rate | Taxa base da faixa |
| CRM Bonus Rate | Taxa de bônus/penalidade IS-CRM (positiva ou negativa) |
| Final Rate | Taxa final = Base Rate + CRM Bonus Rate |
| Commission Base Amount | Base de cálculo da comissão |
| Commission Amount | Valor da comissão calculado |

### IS-CRM
| Campo | Descrição |
|-------|-----------|
| IS-CRM Score (%) | Média dos IS-CRM scores de todas as vendas do período |
| IS-CRM OK | True se IS-CRM Score >= política.crm_min_pct (95%) |

## Como calcular a comissão

1. Certifique-se de que as **Vendas** do período estão registradas e confirmadas.
2. Verifique se a **Meta** do período está cadastrada.
3. Confirme se a **Política** de comissionamento está ativa.
4. No formulário do resultado, clique em **Calcular**.
5. O sistema irá:
   a. Buscar todas as `commission.sale` do período para a orientadora
   b. Calcular o `delivery_pct` com base na meta
   c. Identificar a faixa de taxa na política
   d. Calcular o IS-CRM médio do período
   e. Aplicar bônus/penalidade
   f. Calcular o valor final da comissão
6. Revise os valores e clique em **Aprovar**.
7. Após o pagamento, clique em **Pago**.

## Ações disponíveis

| Botão | Ação |
|-------|------|
| Calcular | Executa o cálculo da comissão com base nos dados do período |
| Aprovar | Marca o resultado como aprovado |
| Pago | Marca o resultado como pago |
| Resetar Volta ao Rascunho | Retorna para estado Draft para recalcular |
