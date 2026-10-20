# Roadmap

Regra: cada fase precisa terminar em algo demonstrável. Fase que só produz código de infraestrutura
sem nada visível é sinal de escopo mal cortado.

Ao concluir uma etapa, marque aqui na mesma alteração que entrega o código.

---

## Fase 0 — Organizar a casa ✅

- [x] Definição de nome, posicionamento e modelo de negócio (Open Core + SaaS gerenciado)
- [x] Paleta e regras de interface fundamentadas (`docs/BRAND.md`)
- [x] Arquitetura definida: monólito modular com módulos instaláveis (`docs/ARCHITECTURE.md`)
- [x] Discovery do módulo Agro a partir do formulário real (`docs/discovery/`)
- [x] Estrutura do monorepo e regras para a IA (`CLAUDE.md`)
- [ ] Repositório no GitHub com Git Flow, Projects e Issues por milestone

## Fase 1 — Fundação

Objetivo: uma pessoa consegue entrar no sistema, e a empresa dela está isolada de todas as outras.

- [x] PostgreSQL 18 nativo, com papéis separados: dono do schema e papel da aplicação
      (sem `BYPASSRLS`) — ver `docs/adr/0002-ambiente-de-desenvolvimento-nativo.md`
- [x] `apps/api`: FastAPI com configuração, health check e Alembic
- [x] Carregador de módulos lendo `module.toml`, com resolução de dependências
- [x] `modules/core`: empresa, usuário, papéis, permissões e auditoria
- [x] Autenticação: Argon2id, JWT de acesso e refresh token rotativo e revogável
- [x] Isolamento multi-tenant com Row Level Security, provado por teste contra banco real
- [x] Comando `decko-admin bootstrap`: cria a empresa e o administrador, com o papel de
      administrador montado a partir das permissões declaradas nos manifestos
- [x] `apps/web`: React 19 + Vite + Tailwind v4 consumindo os tokens, com tela de login,
      modo claro/escuro por estação e sessão restaurada ao recarregar
- [ ] Escrita na trilha de auditoria nos fluxos de autenticação (o bootstrap já registra)
- [ ] Troca de empresa para quem opera em mais de uma

**Demonstrável:** login, troca de empresa, e a prova de que um tenant não enxerga dados do outro.

Estado atual: o ciclo completo funciona e foi verificado no navegador — login, permissões
vindas dos manifestos dos módulos, alternância de tema, sessão sobrevivendo ao recarregar
e logout. 11 testes contra PostgreSQL real cobrem o isolamento entre empresas e o ciclo
de tokens.

Pendências conhecidas, registradas para não virarem dívida esquecida:

- O refresh token fica em `localStorage`, exposto a XSS. A troca por cookie `httpOnly`
  exige tratar CSRF e mudar o backend — ver `apps/web/src/lib/session.ts`.
- A fonte Inter ainda não é hospedada pelo projeto; hoje recai na fonte do sistema. Para
  o modo offline, ela precisa vir junto com a aplicação, não de um CDN.

## Fase 2 — MVP Agro

Escopo e critério de aceite em `docs/discovery/agro-planejamento-operacional.md`.

- [ ] Cadastros: cliente, propriedade, aeronave, produto
- [ ] Modelo do Planejamento Operacional e das leituras meteorológicas
- [ ] Captura de GPS com conversão decimal → grau/minuto/segundo
- [ ] Integração com API meteorológica, com cache em Redis
- [ ] Registro probatório da leitura: origem, provedor, payload bruto, coordenada, horário
- [ ] Alerta de violação de parâmetro (vento, temperatura, umidade)
- [ ] Wizard mobile de preenchimento
- [ ] Geração do PDF fiel ao talão atual
- [ ] Consolidação mensal

**Demonstrável:** Nathan emite um Planejamento Operacional completo pelo celular, em campo, e o PDF
substitui o talão de papel.

## Fase 3 — Validação em campo

- [ ] Nathan usa em operação real
- [ ] Responder as questões Q1–Q8 do discovery
- [ ] Ajustar com base no uso real, não em suposição

Esta fase não produz funcionalidade nova de propósito. Validar antes de ampliar é o que evita
construir o módulo errado.

## Fase 4 — Discovery da distribuidora de bebidas

Mesmo método do Agro: documento real em mãos antes de modelar.

- [ ] Entrevista e levantamento das dores
- [ ] Coletar os documentos reais em uso (pedido, romaneio, acerto de rota, controle de prazo)
- [ ] `docs/discovery/distribuidora-*.md`

## Fase 5 — Módulo distribuidora + PDV

- [ ] Estoque com unidade, caixa e atacado
- [ ] PDV offline-first
- [ ] O que o discovery da Fase 4 apontar

## Fase 6 — Camada de inteligência

- [ ] OCR de receituário e nota fiscal (Tesseract + MinIO)
- [ ] Extração estruturada via LLM local (Ollama), sempre com confirmação humana
- [ ] Busca semântica no catálogo (Qdrant + rerank)
- [ ] Entrada por voz no campo

## Fase 7 — Distribuição multiplataforma

- [ ] PWA offline completo
- [ ] Empacotamento Android (Capacitor)
- [ ] Empacotamento desktop (Tauri)
- [ ] Observabilidade: Prometheus, Grafana, Jaeger

---

## Fora de escopo por ora

Registrado para não ser reintroduzido por engano:

- Microsserviços — ver `docs/ARCHITECTURE.md`, seção 1
- Fine-tuning de modelo — RAG resolve o caso de uso atual com custo muito menor
- Integração automatizada com o portal do MAPA — depende da resposta de Q1
- Módulos de supermercado, ferragista, restaurante e veículos — só após duas verticais validadas
