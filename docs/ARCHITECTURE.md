# Arquitetura do Decko

## 1. Princípio central: monólito modular, não microsserviços

O Decko é um **monólito modular** — um único processo de API que carrega módulos instaláveis em
tempo de execução, no modelo do Odoo.

Microsserviços foram descartados nesta fase. O projeto tem um desenvolvedor; distribuir o sistema
cedo cria custo de operação, rastreamento e consistência de dados sem resolver nenhum problema que
exista hoje. A modularidade é obtida pela fronteira entre módulos, não pela fronteira de rede.

Os módulos são desacoplados o suficiente para que, se um deles justificar extração futura, a
extração seja mecânica.

## 2. Por que "módulo" é a unidade central

O requisito de produto é: *o cliente escolhe o perfil da empresa e o sistema fica pronto para aquele
segmento*. Isso só funciona se o segmento for um artefato instalável, não um `if` espalhado pelo
código.

Um módulo é autocontido:

```
modules/<nome>/
  module.toml        # manifesto: identificação, dependências, permissões, menus
  backend/           # modelos, serviços, rotas, migrações do módulo
  frontend/          # telas do módulo, carregadas sob demanda
  tests/
```

O manifesto declara o que o módulo precisa e o que oferece:

```toml
[module]
name = "agro"
version = "0.1.0"
depends = ["core"]

[permissions]
provides = ["agro.plan.create", "agro.plan.sign", "agro.plan.export"]

[menu]
label = "Agro"
```

**Consequências:**

- Instalar um perfil de empresa = ativar um conjunto de módulos para aquele tenant.
- Um módulo só importa de outro módulo que ele declare em `depends`. Import não declarado quebra
  a suíte — `apps/api/tests/test_module_boundaries.py`. O grafo de dependência fica no manifesto,
  e não escondido no código, que é o que impede o sistema de virar um emaranhado conforme os
  segmentos crescem. Ver `docs/adr/0007-dependencia-entre-modulos.md`.
- Módulo irmão não escreve na tabela de outro módulo: chama o serviço dele.
- O frontend carrega o bundle do módulo sob demanda (code splitting), então um supermercado não
  baixa o código do agro. Isso atende o requisito de leveza.

## 3. Estrutura do repositório

```
decko/
├── apps/
│   ├── api/          # host FastAPI: carrega módulos, expõe a API
│   ├── web/          # shell React/Vite: layout, auth, carrega módulos sob demanda
│   └── worker/       # tarefas assíncronas (OCR, PDF, IA, importações)
├── modules/
│   ├── core/         # tenants, autenticação, RBAC, auditoria, eventos, arquivos
│   ├── agro/         # vertical 1 — relatórios de pulverização (AgroDrone)
│   └── distribuidora/# vertical 2 — distribuidora de bebidas
├── packages/
│   ├── tokens/       # design tokens (fonte única das cores e tipografia)
│   └── ui/           # componentes compartilhados
├── infra/
│   ├── compose/      # podman-compose dos serviços
│   └── observability/
└── docs/
```

## 4. Multi-tenancy

Isolamento por `tenant_id` com **Row Level Security do PostgreSQL**, não apenas filtro na aplicação.

O filtro em aplicação depende de todo desenvolvedor lembrar de aplicá-lo em toda consulta — uma
falha silenciosa vaza dados de uma empresa para outra. Com RLS, o banco recusa por padrão: o
vazamento vira impossível, não improvável.

Clientes grandes que exijam isolamento físico podem receber schema ou banco dedicado depois; o
modelo lógico não muda.

## 5. Camadas do backend

```
api/          rotas, validação de entrada/saída (Pydantic). Sem regra de negócio.
services/     regra de negócio. Não conhece HTTP.
domain/       entidades e invariantes.
repositories/ acesso a dados.
```

A separação existe para que a regra de negócio — a parte regulada, que precisa ser auditável e
testável — não fique presa a detalhes de framework.

## 6. Estratégia de dados

| Tecnologia | Papel | Por quê |
|---|---|---|
| PostgreSQL | Fonte da verdade. Dados transacionais, fiscais e de auditoria | Transações e RLS |
| Alembic | Versionamento de schema | Mudança de banco rastreável e reversível |
| Redis | Cache (ex.: clima por coordenada) e fila de tarefas | Evita estourar cota de API externa |
| MinIO | Arquivos: receituários, croquis, PDFs, notas fiscais | S3-compatível, roda local |
| Qdrant | Busca semântica e RAG | Busca em linguagem natural no catálogo |

Dados de IA (embeddings) nunca são fonte da verdade. O Postgres é.

## 7. IA — onde entra e onde não entra

A IA é usada para **transformar entrada não estruturada em dado estruturado**, sempre com revisão
humana antes de virar registro oficial:

- OCR (Tesseract) + LLM local (Ollama) para ler receituário agronômico e nota fiscal.
- Extração de parâmetros a partir de texto ou áudio ditado pelo operador em campo.
- RAG (Qdrant + rerank) para consultar legislação e bulas.

**Limite rígido:** a IA nunca decide sozinha o conteúdo de um documento legal. Ela pré-preenche; a
pessoa confirma. Documento regulado assinado por LLM sem conferência é risco jurídico, não recurso.

## 8. Multiplataforma

Uma base de código, três destinos:

- **Web / mobile:** PWA (React + Vite), com funcionamento offline — requisito real, porque o campo
  não tem sinal e o caixa não pode parar se a internet cair.
- **Android:** o mesmo PWA empacotado via Capacitor.
- **Desktop:** Tauri, pelo consumo de memória muito menor que o Electron em máquina antiga de caixa.

Offline-first implica escrita local com sincronização posterior e resolução de conflito explícita.
Isso é decisão estrutural: precisa estar no modelo desde o início, não ser adaptado depois.

## 9. Observabilidade

Prometheus (métricas), Grafana (painéis), Jaeger (rastreamento distribuído).

Não é enfeite: com IA local e integrações externas no caminho da requisição, a latência tem várias
origens possíveis. Sem rastreamento, diagnosticar lentidão em produção vira adivinhação.

## 10. Segurança

- Autenticação por JWT curto + refresh token revogável em Redis.
- RBAC granular por permissão declarada em manifesto de módulo.
- Criptografia em repouso para campos sensíveis.
- Trilha de auditoria imutável para tudo que tenha efeito legal ou financeiro.
- RLS como última linha de defesa do isolamento entre empresas.
