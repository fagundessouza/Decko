# Como contribuir

## Branches

```
main       produção — sempre estável, só recebe merge de staging ou hotfix
staging    homologação — validação final antes de produção
develop    integração contínua — base do trabalho do dia a dia
```

Branches de trabalho, sempre criadas a partir de `develop`:

```
feature/<escopo>-<descricao>     feature/agro-weather-capture
bugfix/<escopo>-<descricao>      bugfix/core-token-refresh
```

Exceção: `hotfix/<descricao>` sai de `main`, e ao concluir volta para `main` **e** `develop`,
para a correção não se perder no próximo release.

Nunca commitar direto em `main` ou `staging`.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/), com escopo quando aplicável:

```
feat(agro): capture weather readings from coordinates
fix(core): refresh token not revoked on logout
docs: record module manifest decision
refactor(web): extract wizard step navigation
chore(infra): add qdrant to compose
```

Mensagem em inglês. O assunto diz o que a alteração faz, não o que o autor fez.

## Pull requests

Todo PR precisa responder:

1. O que muda e por quê.
2. Como foi verificado.
3. O que ficou de fora de propósito.

PR que altera schema inclui a migração Alembic. PR que altera decisão de arquitetura inclui ou
atualiza um ADR em `docs/adr/`.

## Organização das tarefas

Milestones do GitHub correspondem às fases do `docs/ROADMAP.md`. Cada issue pertence a uma fase e a
um módulo (`core`, `agro`, `distribuidora`, `infra`, `docs`).

Uma issue descreve o problema e o critério de aceite — não a solução. A solução é discutida no PR.

## Qualidade

- Sem dado mockado em código de aplicação. Dados de teste ficam em fixtures declaradas.
- Teste que depende de banco usa PostgreSQL real em container, não mock. Mock de banco esconde
  justamente a divergência que quebra em produção.
- Segredo nunca entra no repositório.
- Migração de banco só via Alembic.

## Ambiente

Pré-requisitos: Podman, Python 3.12+, Node 20+.

A infraestrutura local sobe por `infra/compose`. Instruções serão adicionadas junto com a Fase 1
do roadmap.
