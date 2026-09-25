# Dashboard

**Localização:** CRM > Repasses > Dashboard

O Dashboard é uma página web que apresenta um resumo dos resultados de comissões do usuário. Sem um filtro informado, ele abre com o período do mês atual.

## Como acessar

1. Acesse **CRM > Repasses > Dashboard**.
2. Informe a **Data inicial** e a **Data final**.
3. Clique em **Aplicar período**.

As duas datas são incluídas no filtro e interpretadas no fuso horário do usuário. Se somente uma das datas for informada, o sistema completa a outra com o início ou o fim do mês correspondente. Se ambas forem deixadas em branco, datas inválidas forem informadas ou o intervalo for invertido, o sistema corrige o período para o mês atual e exibe um aviso na página.

## Quem pode acessar

Usuários dos grupos **CRM Commission User**, **Orientadora** e **SDR**, bem como usuários dos grupos padrão de Vendas, podem abrir o dashboard. As permissões do SDR são somente de leitura e as regras de acesso mantêm cada usuário restrito aos próprios registros.

## Indicadores do período

### 1. Meta e realizado

-   Soma das metas mensais dos meses tocados pelo período
-   Valor realizado
-   Percentual de performance
-   Diferência entre a meta e o realizado

Uma meta é mensal e fica armazenada no primeiro dia do mês. Assim, um intervalo de 15 de agosto a 15 de setembro inclui as metas de agosto e setembro.

### 2. Repasses do período

-   Repasses que se sobrepõem ao intervalo selecionado
-   Total a liquidar
-   Total com fatura gerada
-   Performance realizada em settlements de CRM, apresentada separadamente dos valores de comissão
-   Valor com exceção de faturamento
-   Até 10 repasses na tabela; as somas incluem todos os repasses encontrados

O rótulo **Fatura Gerada** significa que o settlement já possui uma fatura criada. A tela não afirma que a fatura esteja lançada ou paga.

### 3. Desempenho e bônus trimestrais

-   Bônus cujo trimestre se sobrepõe ao período
-   Meta, realizado e performance agregados
-   Valor recuperado e prêmio especial
-   Todos os bônus encontrados, inclusive os não atingidos

### 4. Pipeline de oportunidades

-   Oportunidades abertas no período e atribuídas ao usuário ou, no caso da Orientadora, aos seus SDRs vinculados
-   Exclusão de oportunidades com probabilidade zero ou 100
-   Receita esperada, probabilidade e receita ponderada
-   Para Orientadoras, inclui as oportunidades próprias e dos SDRs vinculados; para SDRs, apenas as próprias

### 5. Pedidos do período

Um pedido entra no dashboard quando está confirmado (`sale` ou `done`) e o usuário é agente em pelo menos uma de suas linhas. Não é necessário que o vendedor ou a oportunidade seja do usuário.

O valor **Meu Repasse** soma somente as linhas de comissão cujo agente é o usuário. Ele não inclui o repasse de outros agentes do mesmo pedido.

Os pedidos são agrupados da seguinte forma:

-   **Faturados:** `invoiced` e `upselling`
-   **Não Faturados:** `to invoice` e `no` (sem valor a faturar)

Os cartões usam o valor total do pedido, enquanto a coluna **Meu Repasse** apresenta somente a comissão individual.
