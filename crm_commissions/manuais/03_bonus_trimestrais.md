# Bônus Trimestrais

**Localização:** CRM > Comissões > Bônus Trimestrais
**Modelo:** crm.commission.quarterly.bonus
**Grupo:** Apenas CRM Commission Manager

## Propósito

Gerenciar o bônus trimestral das orientadoras. Quando a performance acumulada do trimestre atinge 100% ou mais, a orientadora tem direito a recuperar comissões perdidas em meses anteriores onde a meta não foi atingida.

## Campos do Formulário

| Campo | Descrição |
|-------|-----------|
| Agent | Orientadora |
| Quarter | Trimestre de referência (Q1, Q2, Q3, Q4) |
| Year | Ano |
| Monthly Targets | Metas mensais que compõem o trimestre |
| Total Target | Soma das metas do trimestre |
| Total Achieved | Soma dos valores realizados no trimestre |
| Quarterly Performance (%) | Total Achieved / Total Target × 100 |
| Lost Commission Recovered | Valor de comissão perdida que foi recuperada |
| Bonus Amount | Valor do bônus calculado |
| State | Pending, Recovered/Paid, Lost |

## Como funciona

1. As metas mensais de cada orientadora são agrupadas por trimestre.
2. O sistema calcula a **performance trimestral** (total realizado / total meta).
3. Se a performance >= 100%, a orientadora recupera comissões de meses com performance < 100%.
4. O valor recuperado é registrado no campo **Lost Commission Recovered**.
5. O estado muda para **Recovered/Paid** se houver recuperação, ou **Lost** se a performance trimestral ficou abaixo de 100%.

## Fluxo

1. As metas mensais são cadastradas em **CRM > Comissões > Metas Mensais**.
2. Os resultados mensais são calculados em **Comissionamento > Resultados**.
3. O bônus trimestral é processado automaticamente ou manualmente ao recalcular resultados.
