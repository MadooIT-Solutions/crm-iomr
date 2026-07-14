# Equipe (Comissionamento)

**Localização:** Comissionamento > Equipe
**Modelo:** commission.member

## Propósito

Cadastrar e gerenciar os membros da equipe de comissionamento: orientadoras, SDRs e coordenadoras.

## Campos do Formulário

| Campo | Descrição |
|-------|-----------|
| Name | Nome do membro |
| Member Type | Tipo: Orientadora, SDR, Coordenadora |
| Partner | Contato vinculado (res.partner) |
| User | Usuário do sistema (calculado a partir do partner) |
| Active | Ativo |
| Team | Equipe CRM |

### Relacionamentos
| Campo | Descrição |
|-------|-----------|
| SDRs | SDRs vinculadas a esta orientadora |
| Orientadora | Orientadora responsável (para SDRs) |
| Targets | Metas do membro (link para commission.target) |
| Results | Resultados do membro (link para commission.result) |

## Como criar

1. Vá para **Comissionamento > Equipe**
2. Clique em **Criar**
3. Informe o **nome**
4. Selecione o **tipo** (Orientadora, SDR ou Coordenadora)
5. Vincule o **partner** (contato no Odoo)
6. Se SDR, selecione a **orientadora** responsável
7. Se orientadora, vincula as **SDRs** que reportam a ela
8. Salve

## Regras

- Uma orientadora pode ter múltiplas SDRs vinculadas.
- Uma SDR pode ter apenas uma orientadora.
- Coordenadoras não têm subordinados diretos.
- Apenas orientadoras podem ter metas e resultados de comissão.
