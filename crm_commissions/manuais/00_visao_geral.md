# Manual do Sistema CRM Comissões IOMR

## Visão Geral

O módulo **CRM Comissões IOMR** gerencia o cálculo de comissões da equipe comercial da clínica IOMR, integrando metas mensais, performance por vendas, indicador IS-CRM, bônus trimestrais e portal do médico.

## Estrutura de Menus

O sistema está organizado em dois grupos de menus:

### CRM > Comissões
| Menu | Descrição |
|------|-----------|
| Dashboard | Painel web com resumo de metas, performance e comissões |
| Metas Mensais | Metas mensais por orientadora (modelo crm.commission.target) |
| Bônus Trimestrais | Bônus por cumprimento de meta trimestral |
| Config. Comissão LIOs | Regras de comissão progressiva e parâmetros IS-CRM |

### Comissionamento
| Menu | Descrição |
|------|-----------|
| Dashboard | Painel web de comissionamento |
| Vendas | Registro manual de cirurgias, LIOs e exames |
| Metas | Metas individuais/equipe por período |
| Resultados | Cálculo mensal de comissão por orientadora |
| Recuperação Trimestral | Recuperação de comissão perdida em trimestres anteriores |
| Equipe | Cadastro de membros da equipe (orientadoras, SDRs, coordenadoras) |
| Política | Faixas de taxa de comissionamento por performance |
| Configurações | Acesso às regras de comissão (commission) |

## Perfis de Usuário

| Perfil | Acesso |
|--------|--------|
| Orientadora | Vendas, Metas, Resultados (próprios), Equipe (leitura) |
| SDR | Acesso limitado a leads |
| Coordenadora | Visão geral da equipe |
| Commission Manager | Acesso total a todos os menus e configurações |
| Commission User | Acesso operacional |
| Doctor (Médico) | Acesso via portal (/my/opportunities) |
