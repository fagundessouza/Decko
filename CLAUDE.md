# Decko — instruções para a IA

Leia este arquivo inteiro antes de qualquer alteração. Ele existe para manter o alinhamento do
projeto entre sessões diferentes, quando o contexto anterior já não está disponível.

## O que é o Decko

Plataforma ERP/PDV modular, **Open Core**, no modelo do Odoo: o cliente escolhe o perfil da empresa
e o sistema instala e configura os módulos daquele segmento. O núcleo é aberto; a monetização vem
de hospedagem gerenciada (SaaS) e de módulos avançados.

Dono do projeto: Lucas Fagundes Souza (engenheiro de software). O projeto também serve de
portfólio para vagas no mercado internacional.

## Onde está a verdade do projeto

| Pergunta | Arquivo |
|---|---|
| Como o sistema é construído e por quê | `docs/ARCHITECTURE.md` |
| O que fazer agora e em que ordem | `docs/ROADMAP.md` |
| Cores, tipografia, regras de UX | `docs/BRAND.md` |
| Requisitos do módulo Agro | `docs/discovery/agro-planejamento-operacional.md` |
| Decisões arquiteturais e seus motivos | `docs/adr/` |
| Como o Odoo resolve o mesmo problema, e onde divergimos | `docs/benchmark/odoo-20-comparativo.md` |

Antes de propor arquitetura, leia `docs/ARCHITECTURE.md` e confira em
`docs/benchmark/odoo-20-comparativo.md` se a dimensão já está decidida — lá estão as divergências
deliberadas em relação ao Odoo (que não são dívida) e as lacunas que ainda esperam ADR.
Antes de criar tela, leia `docs/BRAND.md`.
Antes de modelar o módulo Agro, leia o discovery — ele vem de um formulário real em uso, não de
suposição.

## Regras não negociáveis

1. **Sem dados mockados.** Nenhum dado falso, de exemplo ou "placeholder" em código de aplicação.
   Dados de teste existem apenas em fixtures declaradas, isoladas e nunca carregadas em produção.
2. **Dados sensíveis em primeiro lugar.** O sistema guarda CPF/CNPJ, dados fiscais, registros
   profissionais e informação de clientes. LGPD não é etapa final: criptografia, RBAC e trilha de
   auditoria entram junto com a funcionalidade, não depois.
3. **Nada de segredo em código.** Credenciais só por variável de ambiente. `.env` nunca é commitado.
4. **Migração sempre versionada.** Mudança de schema só via Alembic. Nunca alterar banco à mão.
5. **Leveza é requisito funcional.** O alvo inclui PC antigo de caixa e celular fraco. Peso de
   bundle e consulta lenta são defeitos, não detalhes.
6. **Não inventar regra de negócio.** O domínio é regulado (MAPA, fiscal). Se o requisito não
   estiver documentado, pergunte — não presuma. Questões em aberto ficam listadas no discovery.

## Idioma

- **Código, nomes de variáveis, commits e comentários:** inglês.
- **Documentação em `docs/` e interface do usuário:** português do Brasil.
- **README.md:** inglês (é a vitrine pública do repositório).

Termos do domínio permanecem em português mesmo no código, porque não têm tradução fiel e a
tradução atrapalharia a conferência com a lei: `receituario`, `croqui`, `planejamento_operacional`,
`classe_toxicologica`, `crea`, `canac`.

## Convenções

- Monorepo. `apps/` são executáveis, `modules/` são módulos de negócio instaláveis,
  `packages/` é código compartilhado, `infra/` é infraestrutura.
- Um módulo só importa de outro que ele declare em `depends`, no `module.toml`, e nunca
  escreve na tabela de outro módulo — chama o serviço dele. O teste de fronteira
  (`apps/api/tests/test_module_boundaries.py`) recusa import não declarado. Decisão e
  motivo: `docs/adr/0007-dependencia-entre-modulos.md`.
- Backend: Python, FastAPI, SQLAlchemy, Alembic, Pydantic.
- Frontend: React, Vite, TypeScript, Tailwind.
- Containers: Podman (rootless).
- Teste que depende de banco usa banco real em container, não mock.

## Git

Git Flow: `main` (produção) ← `staging` (homologação) ← `develop` (integração) ←
`feature/*` | `bugfix/*` | `hotfix/*`.

Commits em Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`).
Nunca commitar direto em `main` ou `staging`.

## Como trabalhar neste repositório

- Mudou uma decisão de arquitetura? Registre um ADR em `docs/adr/` **antes** de implementar.
- Terminou uma etapa do roadmap? Atualize `docs/ROADMAP.md` na mesma alteração.
- Descobriu um requisito novo com o cliente? Atualize o discovery do módulo, não só o código.
- Não crie abstração para caso hipotético. O projeto é grande; a complexidade precisa ser ganha.
