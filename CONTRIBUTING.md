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

Pré-requisitos: Python 3.13+, Node 20+, PostgreSQL 18, [uv](https://docs.astral.sh/uv/).

Em desenvolvimento os serviços rodam nativos, sem container — o motivo está em
`docs/adr/0002-ambiente-de-desenvolvimento-nativo.md`. Produção é Linux com containers.

```powershell
winget install Python.Python.3.13 astral-sh.uv OpenJS.NodeJS.LTS PostgreSQL.PostgreSQL.18
```

O banco usa dois papéis, e a separação é o que faz o isolamento entre empresas funcionar:

- `decko_owner` — dono do schema, usado apenas pelas migrações.
- `decko_app` — usado pela aplicação. Não é dono e não tem `BYPASSRLS`, então as políticas
  de Row Level Security se aplicam a ele.

Credenciais locais ficam em `.env`, na raiz do repositório, que não é versionado.

```powershell
uv sync                                          # instala o workspace
uv run alembic -c apps/api/alembic.ini upgrade heads
uv run pytest                                    # inclui a prova de isolamento
uv run uvicorn decko.main:app --reload           # http://127.0.0.1:8000/docs
```

`GET /health` informa com qual papel a aplicação está conectada e se esse papel ignora RLS.
Se `bypasses_rls` vier `true`, o isolamento entre empresas não está valendo.

### Primeira empresa

Sem empresa cadastrada não há como autenticar. A criação não existe na API de propósito,
para não deixar um cadastro aberto na internet:

```powershell
uv run decko-admin bootstrap --tenant-name "Minha Empresa" --tenant-slug minha-empresa `
  --admin-email voce@suaempresa.com.br --admin-name "Seu Nome"
```

A senha é pedida no terminal — nunca passada como argumento, porque argumentos ficam no
histórico do shell e na lista de processos. `uv run decko-admin status` lista o que existe.

O identificador é normalizado: `AgroDrone` e `Agro Drone` viram `agrodrone` e `agro-drone`,
e o comando informa o valor gravado. Em execução automatizada, sem terminal para responder
ao pedido de senha, defina `DECKO_ADMIN_PASSWORD` — sem isso o comando fica esperando.

A senha escolhida é conferida contra vazamentos conhecidos, e recusada se aparecer em um.
Só os cinco primeiros caracteres do SHA-1 saem da máquina, nunca a senha; o serviço fora do
ar deixa a senha passar, com aviso no log. Em instalação sem internet, desligue com
`DECKO_BREACH_CHECK_ENABLED=false` — ver `docs/adr/0011-senha-conhecidamente-vazada.md`.

### Frontend

```powershell
npm install --prefix apps/web
npm run dev --prefix apps/web      # http://localhost:5173
```

O servidor de desenvolvimento encaminha `/api` para a API na porta 8000, então os dois
precisam estar rodando. As cores e a tipografia vêm de `packages/tokens/tokens.css`
através do `@theme` do Tailwind: nenhum componente escreve cor diretamente.
