# Metas (Comissionamento)

**Localização:** Comissionamento > Metas
**Modelo:** commission.target

## Propósito

Registrar as metas individuais e de equipe para cada membro (orientadora) por período mensal.

## Campos do Formulário

| Campo | Descrição |
|-------|-----------|
| Name | Nome (calculado automaticamente) |
| Member | Membro da equipe (orientadora) |
| Year | Ano da meta |
| Month | Mês (1 a 12) |
| Period Code | Código do período (YYYY-MM, calculado) |
| Team Target Amount | Meta da equipe para o período |
| Individual Target Amount | Meta individual da orientadora |
| Origin Type | Origem: Auto (calculado pelo sistema) ou Manual |
| State | Draft, In Progress, Achieved, Lost |

## Como criar

1. Vá para **Comissionamento > Metas**
2. Clique em **Criar**
3. Selecione o **membro** (orientadora)
4. Defina **ano** e **mês**
5. Informe o valor da **meta individual**
6. Se houver meta de equipe, preencha **Team Target Amount**
7. Salve

## Regras

- O **state** é calculado automaticamente com base no campo `achieved_amount` (vindo do `commission.result`).
- As metas alimentam o cálculo de performance no `commission.result`.
- Orientadoras veem apenas suas próprias metas (regra de registro).
