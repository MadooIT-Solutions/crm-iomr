Faz com que a Operação Fiscal do pedido seja propagada automaticamente para
as linhas do pedido de venda.

No `l10n_br_sale` original, o campo `fiscal_operation_id` da linha é um
Many2one simples (sem compute): a operação escolhida no cabeçalho só chega às
linhas quando elas são criadas pelo formulário, via contexto. Linhas criadas
antes de marcar a operação no pedido (ou por importação/colagem) permanecem
sem operação e, por consequência, o campo "Linha de operação" fica em branco e
sua lista de opções vazia.

Este módulo torna o campo compute (stored, precompute), preenchendo
automaticamente as linhas vazias com a operação do cabeçalho. Valores
digitados manualmente na linha não são sobrescritos.
