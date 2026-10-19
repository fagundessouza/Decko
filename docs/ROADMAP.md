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
- [ ] Escrita efetiva na trilha de auditoria nos fluxos de autenticação
- [ ] Cadastro inicial de empresa e primeiro usuário administrador
- [ ] `apps/web`: shell React/Vite com os tokens aplicados, login e layout

**Demonstrável:** login, troca de empresa, e a prova de que um tenant não enxerga dados do outro.

Estado atual: o backend responde em `/health` e expõe `/api/v1/core/auth/*`; cinco testes
cobrem o isolamento. Falta a interface e o cadastro inicial.

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
