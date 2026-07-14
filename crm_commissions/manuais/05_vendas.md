# Vendas (Comissionamento)

**Localização:** Comissionamento > Vendas
**Modelo:** commission.sale

## Propósito

Registrar manualmente cirurgias, vendas de LIOs e exames realizados por cada orientadora. Este cadastro serve como base de cálculo para as comissões mensais.

## Campos do Formulário

### Cabeçalho
| Campo | Descrição |
|-------|-----------|
| Name | Número do registro (gerado automaticamente: COM-ANO-SEQ) |
| Date | Data da venda |
| Orientadora | Membro da equipe responsável (tipo orientadora) |
| Patient Name | Nome do paciente |
| Surgery Type | Tipo de cirurgia: Catarata, Refrativa, Glaucoma, Vitrectomia, Outros |
| Sale Category | Categoria: Particular, Convênio, Saúde Toddos, Outras |
| Status | Rascunho, Confirmado, Faturado, Cancelado |

### Valores Financeiros
| Campo | Descrição |
|-------|-----------|
| LIO Package Amount | Valor do pacote de LIO |
| LIO Upgrade Amount | Valor do upgrade de LIO |
| Hospital Gross Amount | Valor bruto hospitalar |
| Hospital Tax (%) | Percentual de imposto hospitalar |
| Hospital Cost (%) | Percentual de custo hospitalar |
| Hospital Net Amount | Valor líquido hospitalar (calculado automaticamente) |
| Medical Fee Amount | Valor do honorário médico |

### Indicadores
| Campo | Descrição |
|-------|-----------|
| IS-CRM (%) | Score IS-CRM para esta venda (padrão: 100%, editável) |
| Margin (%) | Margem calculada automaticamente |
| Discount (%) | Percentual de desconto concedido |
| Discount Approved | Indica se o desconto foi aprovado |

### Aba de Linhas (Line Items)
| Campo | Descrição |
|-------|-----------|
| Line Type | Tipo: Hospital, Medical Fee, LIO Package, LIO Upgrade |
| Amount | Valor da linha |
| Eligible for Commission | Calculado automaticamente (Medical Fee e LIO Package nunca comissionam) |
| Exclusion Reason | Motivo de exclusão da comissão (se aplicável) |

### Venda de Lentes de Contato
| Campo | Descrição |
|-------|-----------|
| Is Lens Sale | Marcar se é venda de lente de contato |
| Lens Type | Gelatinous ou Rigid |
| Lens Commission Type | Com exame (1,5%) ou Sem exame (5%) |

## Como criar uma venda

1. Vá para **Comissionamento > Vendas**
2. Clique em **Criar**
3. Preencha a **orientadora**, **paciente**, **data** e **categoria**
4. Informe os valores financeiros (hospital, LIO, honorários)
5. Ajuste o **IS-CRM** se necessário
6. Na aba de linhas, adicione os itens da venda
7. Clique em **Confirmar** para ativar a venda
8. Quando faturado, mude o status para **Faturado**

## Regras de Comissionamento

- **Medical Fee** e **LIO Package** nunca geram comissão.
- A base de comissionamento é calculada a partir dos valores elegíveis.
- O IS-CRM da venda alimenta a média do período para cálculo de bônus/penalidade.
