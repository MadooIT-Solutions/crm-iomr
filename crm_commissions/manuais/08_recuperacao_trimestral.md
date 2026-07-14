# Recuperação Trimestral

**Localização:** Comissionamento > Recuperação Trimestral
**Modelo:** commission.recovery

## Propósito

Gerenciar a recuperação de comissões perdidas em trimestres anteriores. Quando uma orientadora não atinge a meta em um mês (performance < 100%), a comissão daquele mês é reduzida. Se no trimestre a performance agregada atingir 100% ou mais, parte da comissão perdida pode ser recuperada.

## Campos do Formulário

| Campo | Descrição |
|-------|-----------|
| Name | Nome (Membro - Q/AAAA, calculado) |
| Member | Membro da equipe (orientadora) |
| Quarter | Trimestre (Q1, Q2, Q3, Q4) |
| Year | Ano |
| Quarter Target Amount | Soma das metas do trimestre |
| Quarter Sales Amount | Soma dos valores realizados no trimestre |
| Quarter Delivery (%) | Performance trimestral (calculado) |
| Expected Commission Amount | Comissão esperada para o trimestre |
| Calculated Commission Amount | Comissão calculada com base na performance real |
| Recovery Amount | Valor a recuperar (calculado) |
| State | Pending, Recovered, Lost |

## Como calcular

1. Vá para **Comissionamento > Recuperação Trimestral**
2. Clique em **Criar** ou abra um registro existente
3. Selecione o **membro**, **trimestre** e **ano**
4. Clique em **Calcular**
5. O sistema irá:
   a. Buscar as metas do trimestre (commission.target)
   b. Buscar os resultados do trimestre (commission.result)
   c. Calcular a performance trimestral
   d. Se performance >= 100%, calcular o valor a recuperar
   e. Atualizar o estado

## Regras

- A recuperação é automática ao recalcular os resultados mensais.
- Se a performance trimestral >= 100%, o valor da comissão perdida em meses ruins é recuperado.
- Orientadoras veem apenas seus próprios registros de recuperação.
