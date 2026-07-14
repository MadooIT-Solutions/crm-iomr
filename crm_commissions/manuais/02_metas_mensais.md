# Metas Mensais

**Localização:** CRM > Comissões > Metas Mensais
**Modelo:** crm.commission.target

## Propósito

Registrar as metas mensais de faturamento para cada orientadora. As metas servem como base para:
- Cálculo de performance mensal (realizado / meta * 100)
- Cálculo de comissão progressiva
- Avaliação do IS-CRM
- Geração de bônus trimestrais

## Campos do Formulário

| Campo | Descrição |
|-------|-----------|
| Agent | Orientadora vinculada (domínio: type_partner = orientadora) |
| Target Date | Mês de referência da meta |
| Target Amount | Valor da meta mensal em moeda |
| Quarterly Target | Meta trimestral (calculada automaticamente pela soma das metas do trimestre) |
| Achieved Amount | Valor realizado (calculado automaticamente a partir dos pedidos do mês) |
| Performance (%) | Percentual de cumprimento: (realizado / meta) × 100 |
| IS-CRM Score | Pontuação IS-CRM para o período (0-100%, padrão 100%) |
| IS-CRM OK | True se IS-CRM Score >= 95% |
| State | Draft, In Progress, Achieved, Lost |

## Como criar uma meta

1. Vá para **CRM > Comissões > Metas Mensais**
2. Clique em **Criar**
3. Selecione a **orientadora**
4. Defina o **mês** (Target Date)
5. Informe o **valor da meta** (Target Amount)
6. Ajuste o **IS-CRM Score** se necessário (padrão 100%)
7. Salve

## Comportamento

- O campo **Achieved Amount** é automaticamente calculado buscando todos os `sale.order` do mês onde a orientadora é agente.
- A **Performance** é recalculada automaticamente.
- O **Quarterly Target** é a soma das metas dos 3 meses do mesmo trimestre.
- O **IS-CRM Score** pode ser editado manualmente se necessário.
