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

### Meta individual (Vendedor(a))

1. Vá para **CRM > Comissões > Metas Mensais**
2. Clique em **Criar**
3. Mantenha o seletor em **Vendedor(a)**
4. Selecione a **orientadora**
5. Defina o **mês** (Target Date)
6. Informe o **valor da meta** (Target Amount)
7. Ajuste o **IS-CRM Score** se necessário (padrão 100%)
8. Salve

### Meta para toda a equipe (Equipe de Vendas)

1. Clique em **Criar**
2. No seletor **Aplicar meta a**, escolha **Equipe de Vendas** (radio)
3. Selecione a **Equipe de Vendas**
4. Defina o mês e o valor da meta
5. Clique em **Aplicar à Equipe**: o sistema cria uma meta individual para
   **todos os vendedores (orientadoras)** da equipe com os mesmos mês, valor e
   IS-CRM. Vendedores que já possuem meta no mês não são duplicados.
6. O registro temporário de equipe é removido e a lista mostra as metas criadas.

## Comportamento

- O campo **Achieved Amount** é automaticamente calculado buscando todos os `sale.order` do mês onde a orientadora é agente.
- A **Performance** é recalculada automaticamente.
- O **Quarterly Target** é a soma das metas dos 3 meses do mesmo trimestre.
- O **IS-CRM Score** pode ser editado manualmente se necessário.
