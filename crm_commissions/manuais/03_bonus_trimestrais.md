# Bônus Trimestrais

**Localização:** CRM > Comissões > Bônus Trimestrais  
**Modelo:** `crm.commission.quarterly.bonus`  
**Origem:** metas mensais em `crm.commission.target`  
**Grupo de gestão:** CRM Commission Manager

## Objetivo

Automatizar a avaliação trimestral da política de comissionamento. A meta do
trimestre é a soma das metas dos três meses da vendedora. O sistema não exige
cadastro manual do bônus: o primeiro registro de Meta Mensal já cria o
registro trimestral e os demais meses são vinculados ao mesmo documento.

## Criação automática

1. Ao cadastrar uma meta mensal individual, o sistema identifica a vendedora,
   o ano e o trimestre.
2. Procura um bônus da mesma vendedora no mesmo ano/trimestre.
3. Cria o registro somente se ele ainda não existir.
4. Recalcula a meta trimestral com a soma das metas mensais vinculadas.
5. Ao alterar ou excluir uma meta, o vínculo e os totais são sincronizados.
6. Uma constraint impede metas duplicadas para a mesma vendedora/mês e bônus
   duplicados para a mesma vendedora/trimestre.

A meta de equipe continua sendo usada apenas como atalho: ao clicar em
**Aplicar à Equipe**, são criadas metas individuais para todas as orientadoras
da equipe. A origem da equipe é preservada para calcular a elegibilidade
coletiva.

## Situação do trimestre

Enquanto o trimestre estiver em andamento, o registro fica como **Pending**.
Ele pode ser criado com apenas uma meta e passa a exibir a quantidade de meses
cadastrados e os meses que ainda faltam.

Após o encerramento do trimestre, a rotina executada diariamente pelo agendador
**CRM Comissões: sincronizar e fechar bônus trimestrais** faz a avaliação
final. O gerenciador também pode usar **Atualizar e finalizar trimestre** depois
que a data final for atingida.

| Estado | Regra |
|---|---|
| Pending | Trimestre ainda não encerrado |
| Incomplete goals | Trimestre encerrado sem as três metas mensais |
| Eligible | Meta trimestral atingida e sem pontos de comissão a recuperar |
| Recovered/Paid | Meta atingida e pontos de comissão recuperados |
| Lost | Meta trimestral não atingida |

## Cálculo da performance

```text
meta trimestral = soma das metas mensais
realizado trimestral = soma do realizado dos três meses
performance = realizado trimestral / meta trimestral × 100
```

A performance de 100% já é considerada meta atingida.

## Recuperação de comissão

A recuperação só ocorre quando:

- as três metas mensais estiverem cadastradas;
- o trimestre estiver encerrado;
- o realizado total for maior ou igual à meta total.

Para cada mês abaixo de 100%:

```text
taxa de referência = taxa-base da política em 100%
taxa do mês = taxa-base efetiva na performance mensal
pontos recuperados = máximo(taxa de referência - taxa do mês, 0)
recuperação = base elegível de comissão do mês × pontos recuperados / 100
```

A base elegível vem dos lançamentos `commission.sale` confirmados/faturados e
respeita as exclusões por tipo de linha. O ajuste de IS-CRM é separado: a
recuperação dos pontos de meta não cancela um bônus ou penalidade de CRM.

**Exemplo:** meta mensal de R$ 1.000,00 e realizado de R$ 700,00. A faixa de
70% usa 0,45%, enquanto 100% usa 0,75%. A diferença é 0,30%. Sobre uma base
elegível de R$ 700,00, a recuperação daquele mês é R$ 2,10.

## Elegibilidade da equipe e coordenadora

O formulário também mostra:

- meta e realizado agregados da equipe;
- performance coletiva do trimestre;
- **Elegível para equipe/coordenadora**.

A elegibilidade coletiva é verdadeira quando as metas dos três meses estão
presentes e o agregado da equipe atinge 100%. Esse indicador permite incluir a
coordenadora no prêmio especial sem misturá-lo à recuperação individual.

## Prêmio especial

A política não define valor ou percentual fixo para o prêmio. Por isso, os
campos **Valor do prêmio especial**, **Tipo de prêmio** e **Descrição do
prêmio** são mantidos manualmente. O tipo pode ser:

- Sorteio;
- Celebração coletiva;
- Outro.

A recuperação de comissão e o prêmio especial são valores distintos e devem
ser acompanhados separadamente.

## Atualização por vendas

A confirmação, alteração ou cancelamento de pedidos e a sincronização de
`commission.sale` atualizam o realizado das metas. O agendador diário também
revisa os realizados e mantém os totais trimestrais consistentes.

## Atualização do módulo

Ao instalar ou atualizar o módulo:

- metas mensais existentes são sincronizadas;
- bônus trimestrais pendentes são criados ou atualizados;
- trimestres já encerrados são reavaliados;
- valores manuais de prêmio, tipo e descrição são preservados.
