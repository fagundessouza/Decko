# Roadmap

Este arquivo responde **o que construir e em que ordem**. O que falta para o produto ser
**vendido** — cadastro de empresa pela aplicação, implantação, backup, cobrança, emissão
fiscal e jurídico — está em `docs/NEGOCIO.md`, porque é operação e não produto, e some
quando fica misturado com fase.

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
- [x] Integração contínua: `pytest` contra PostgreSQL real, com os dois papéis do ambiente
      local e a conferência de que a aplicação não ignora RLS, mais lint, formatação,
      tipos e build do web — `.github/workflows/ci.yml`

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
- [x] Renovação de token em voo único: duas chamadas simultâneas levavam o mesmo refresh
      token rotativo, e a que perdia a corrida derrubava a sessão válida
- [x] Ativação de módulo por empresa: `tenant_module`, verificação aplicada pelo host na
      montagem do router, catálogo e contratação pela API, menu alimentado pelos módulos
      ativos — ver `docs/adr/0004-ativacao-de-modulo-por-empresa.md`
- [x] Recusar senha conhecidamente vazada: Pwned Passwords por k-anonimato, só o prefixo
      de cinco caracteres do SHA-1 sai daqui. Falha **aberta** — serviço fora do ar não
      pode impedir alguém de trabalhar — e desligável para instalação sem internet. Entra
      onde a senha é definida, que hoje é só o cadastro da empresa: troca de senha não
      existe para ser ligada, e inventar a rota agora seria fazer o item errado — ver
      `docs/adr/0011-senha-conhecidamente-vazada.md`
- [x] Escrita na trilha de auditoria na autenticação e na contratação: entrada, saída,
      tentativa recusada, token revogado reapresentado, e módulo contratado, desligado ou
      semeado. Duas decisões ficaram registradas em `modules/core/.../audit.py`: o e-mail
      digitado **nunca** entra (quando a conta existe, `user_id` diz o alvo com mais
      precisão; quando não existe, é palpite de quem sonda), e a falha é gravada em
      transação própria, porque a requisição recusada desfaz a dela. Tentativa contra
      empresa inexistente continua sem registro: `audit_log.tenant_id` é obrigatório e
      não há empresa a que prender a linha
- [x] Tela de consulta da trilha: `GET /core/audit` com filtro por grupo, página e total,
      e a tela que traduz a ação para o português. A permissão `core.audit.read` existia no
      manifesto desde o começo sem consumidor nenhum — escrever a trilha sem poder
      consultar atende a LGPD pela metade. A tradução mora na interface: ação que ela ainda
      não conhece aparece com o nome técnico, que é feio e honesto
- [x] Troca de empresa para quem opera em mais de uma: seletor na lateral, com as
      empresas que já entraram **neste aparelho**. Não há rota que liste "as minhas
      empresas", e isso é a decisão central: a consulta exigiria atravessar o RLS com
      privilégio e devolveria um oráculo de enumeração. Trocar pede a senha, porque as
      contas são independentes — ver `docs/adr/0012-troca-de-empresa.md`. A tela de
      escolha de ramo ganhou saída e troca junto: sem elas, entrar numa empresa sem módulo
      prendia a pessoa ali
- [x] Perfil de segmento: `profiles/*.toml`, tela de escolha do ramo e contratação em um
      clique — ver `docs/adr/0005-perfil-de-segmento.md`
- [x] Vitrine de aplicativos: catálogo agrupado por categoria, com instalar e desinstalar
      a qualquer momento. Rótulo, categoria, resumo e ícone saem do `module.toml`, então
      acrescentar um módulo ao produto não exige tocar na interface. Instalar traz junto
      o que o módulo depende; desinstalar é recusado enquanto outro módulo ativo o usa
- [x] Dado-semente por módulo com identidade estável: `seed_record` no núcleo, por empresa,
      e a semente escrita pelo módulo dono da tabela por porta invertida. Contratar o
      módulo passa a **configurar**, e não só ligar. Reativar não duplica, linha apagada
      pelo cliente não volta, e o `fingerprint` acusa ajuste em vez de adivinhar como o
      `noupdate` do Odoo — ver `docs/adr/0010-dado-semente-com-identidade-estavel.md`.
      A semente que embarcou é só `UN`, `KG` e `L`: fator de embalagem e categoria por
      segmento são suposição enquanto não houver discovery (regra 6)
- [x] "Trazer itens iniciais" na vitrine, para a empresa que instalou o módulo antes de a
      semente existir. A semente entra na contratação e só nela, de propósito — catálogo
      de quem já opera não recebe linha numa subida de aplicação que ninguém pediu —, e
      este é o pedido explícito de quem ficou de fora. Clicar duas vezes diz "nada a
      acrescentar" em vez de duplicar

**Demonstrável:** login, troca de empresa, e a prova de que um tenant não enxerga dados do outro.

**Fase concluída em 29/10/2026.** As duas pendências abaixo seguem valendo — elas são
limitações conhecidas, não itens de escopo, e por isso nunca foram caixas a marcar.

Estado atual: o ciclo completo funciona e foi verificado no navegador — login, permissões
vindas dos manifestos dos módulos, alternância de tema, sessão sobrevivendo ao recarregar
e logout. 11 testes contra PostgreSQL real cobrem o isolamento entre empresas e o ciclo
de tokens.

Pendências conhecidas, registradas para não virarem dívida esquecida:

- O refresh token fica em `localStorage`, exposto a XSS. A troca por cookie `httpOnly`
  exige tratar CSRF e mudar o backend — ver `apps/web/src/lib/session.ts`.
- ~~A fonte Inter não é hospedada pelo projeto.~~ Resolvido: `@fontsource-variable/inter`
  entra pelo pacote e é importada em `apps/web/src/styles.css`, sem CDN.

## Fase 2 — MVP Agro

Escopo e critério de aceite em `docs/discovery/agro-planejamento-operacional.md`.

- [x] Módulo `agro` instalável, com manifesto, permissões próprias e ramificação de
      migrações separada — primeira validação real da arquitetura modular
- [x] Modelo completo derivado do formulário: contratante, propriedade, aeronave, produto,
      receituário, planejamento, produtos aplicados, manutenção, leituras meteorológicas
      e as quatro assinaturas
- [x] Row Level Security nas dez tabelas do módulo, verificado por teste
- [x] Cadastros pela API: contratante, propriedade, aeronave, produto e receituário
- [x] Integração meteorológica por coordenada e horário (Open-Meteo), com escolha entre
      conjunto histórico e recente — ver `docs/adr/0003-provedor-de-clima.md`
- [x] Registro probatório da leitura: origem, provedor, payload bruto, coordenada, horário
- [x] Alerta de violação de parâmetro, devolvendo **qual** limite foi rompido
- [x] Captura de GPS pelo aparelho e conversão decimal → grau/minuto/segundo no documento
- [x] Tabela de produtos e vínculo do receituário pela tela, com a cópia de formulação e
      classe toxicológica feita no lançamento
- [ ] Cache das consultas meteorológicas (só necessário com volume; ver ADR 0003)
- [x] Wizard mobile de preenchimento
- [x] Geração do PDF fiel ao talão atual
- [x] Assinaturas pela tela, desenhadas com o dedo ou a caneta e presas ao documento por
      hash — ver a Fase 5 e `docs/discovery/assinaturas-dois-modulos.md`. A Q5 deixou de
      bloquear: as duas formas convivem, e a gov.br entra quando houver credenciamento
- [x] Cadastro de contratante e propriedade pela tela, dentro do wizard, com captura da
      coordenada da propriedade pelo aparelho
- [x] Conferência de CPF/CNPJ pelo dígito verificador, incluindo o CNPJ alfanumérico, na
      tela e no servidor (`decko.documents`)
- [x] Identificação da empresa aplicadora (registro no MAPA, CREA, CDA, inscrições e
      rodapé) em tela, preenchendo o cabeçalho do documento — antes saía em branco
- [x] Consolidação mensal: fechamento do período com área, produtos e violações, e
      exportador CSV para a planilha. **Não** é o arquivo do portal do MAPA — formato e
      sistema de envio continuam sendo a questão Q1

**Demonstrável:** Nathan emite um Planejamento Operacional completo pelo celular, em campo, e o PDF
substitui o talão de papel.

Estado atual: o caminho inteiro foi percorrido no navegador, em viewport de celular —
planejamento criado, produto cadastrado e lançado na tabela, receituário cadastrado e
vinculado, e o PDF saiu com tudo isso impresso. O caminho começa numa empresa vazia: o
contratante e a propriedade são cadastrados dentro do próprio wizard, onde antes ele
parava em "Nenhum contratante cadastrado ainda".

O CPF/CNPJ é conferido pelo dígito verificador na entrada, nos dois formatos, com a regra
do CNPJ alfanumérico lida na fonte oficial da Receita — ver "Formato do CPF/CNPJ" no
discovery.

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

## Fase 5 — Base comercial e verticais

A auditoria do Odoo 20 mostrou que a vertical é fina: `pos_restaurant` tem uma dependência
só e é quase todo dado-semente. O peso está na base compartilhada, que vem primeiro.

- [x] Módulo `comercial`: unidade em árvore (unidade → caixa → fardo), categoria, produto
      com código de barras, lote e validade, preço de custo e venda, e estoque como razão
      somente-inserção — ver `docs/adr/0006-base-comercial.md`
- [x] Telas do comercial: cadastro de produto, entrada por embalagem e consulta de saldo
- [x] Identificação fiscal do produto: NCM e CEST, com busca por NCM. Veio da experiência
      do dono do projeto como vendedor na Fujioka, onde o comprador de licitação pedia o
      NCM antes do preço — ver `docs/discovery/comercial-produto-fiscal.md`
- [x] Módulo `compras`: importa o XML da NF-e, reconhece o produto por código de barras
      e por código do fornecedor, sugere por semelhança sem decidir sozinho, e dá entrada
      no estoque só depois de conferido — ver
      `docs/adr/0009-identidade-de-produto-e-entrada-por-nota.md`
- [x] Conferência de estoque: estoque mínimo por produto, lista do que está acabando e
      dos lotes vencendo com saldo, e aviso na tela inicial. A validade já existia, por
      lote; o que faltava era a visão do estoque inteiro de uma vez
- [x] Módulo `clientes`: pessoa ou empresa, CPF/CNPJ conferido pelo dígito, contato e
      endereço, busca por nome e por documento. Cadastro não é apagado, só desativado —
      venda e nota continuam apontando para alguém. A trilha registra o que mudou sem
      copiar o dado pessoal para dentro dela
- [x] Cadastro de pilotos no agro, pedido pelo Nathan em 27/10/2026: o planejamento aponta
      para quem voou, em vez de repetir o nome dentro da assinatura. As respostas dele às
      questões abertas estão na seção 6 do discovery do agro
- [x] Permissão de módulo que evolui: versão nova que declara permissão nova agora alcança
      as empresas que já usavam o módulo, na subida da aplicação — ver a atualização no
      `docs/adr/0004-ativacao-de-modulo-por-empresa.md`
- [x] Fechamento mensal no formato que a Portaria MAPA 298/2021 exige: agregado por
      município/UF, com horas de execução e prazo no dia 15 do mês seguinte. O CSV
      aproximado de antes continua, renomeado como conferência, e os dois estão rotulados
      na tela — ver `docs/discovery/agro-normas-mapa.md`
- [x] Direção do vento na leitura meteorológica, exigida pelo art. 10 da Portaria 298/2021.
      O provedor já devolvia; faltava guardar e mostrar
- [x] Croqui a partir do arquivo do voo: lê KML e KMZ, guarda a geometria e desenha o
      croqui no PDF, com contorno da área, faixas de aplicação, norte e seta do vento. A
      área calculada é sugestão — quem declara é quem assina
- [x] Assinatura desenhada na tela, no Planejamento Operacional: traço em vetor, preso ao
      documento por hash, com quem, quando e de onde. Editar o planejamento depois de
      assinado passa a ser acusado. Ficou **dentro do agro**, e não em módulo próprio,
      porque há um consumidor só — ver `docs/discovery/assinaturas-dois-modulos.md`
- [ ] Assinatura gov.br: depende de credenciamento da aplicação na plataforma, que é
      providência do dono do projeto, não código
- [ ] Módulo de plano recorrente: depende de `clientes`, que já existe, e de uma decisão
      sobre meio de pagamento. Sem gateway, dá para gerar a cobrança e marcar como paga
- [ ] Entrada de nota por QR code: depende de certificado digital A1/A3 e de manifestação
      do destinatário. O QR do cupom não carrega os itens
- [ ] Entrada de nota por PDF do DANFE: depende do OCR da Fase 6
- [ ] Responder as dez perguntas de `docs/discovery/comercial-emissao-fiscal.md`. Duas
      correções que a pesquisa trouxe e mudam o escopo: a NFC-e é autorizada pela **SEFAZ
      do estado**, não pela Receita, então não é "uma API"; e a Avalara que se quer imitar é
      **motor de cálculo**, não emissor — é ele que responde à dor do lojista, e é o que a
      reforma tributária está reescrevendo agora
- [ ] Responder as perguntas em aberto do discovery fiscal (origem da mercadoria, CATMAT,
      marca e modelo, unidade tributável, tabela oficial de NCM). Nenhuma foi suposta
- [x] Módulo `pdv`: venda de balcão com busca por código de barras, pagamento em dinheiro,
      débito, crédito e pix, troco, e baixa de estoque na mesma transação da venda — ver
      `docs/adr/0008-ponto-de-venda.md`. É também o primeiro módulo a depender de outro
      módulo de negócio, o que exigiu `docs/adr/0007-dependencia-entre-modulos.md`
- [x] **Venda identificada.** A venda aponta para quem comprou, e o PDV passou a declarar
      `clientes` em `depends` — instalar o ponto de venda traz o cadastro junto, com o
      custo assumido na atualização de 29/10/2026 da `docs/adr/0008-ponto-de-venda.md`.
      Venda anônima continua sendo o caso normal. Cliente desativado não entra em venda
      nova, venda fechada não troca de dono, e o nome é lido na hora em vez de copiado:
      corrigir um nome digitado errado vale para as vendas da pessoa também.
      **Fiado e crediário continuam fora** — cobrança a prazo exige limite, vencimento e
      regra de inadimplência, e nada disso tem requisito escrito
- [ ] **Fornecedor não existe como entidade.** A nota guarda o CNPJ do emitente como texto,
      e o vínculo "código do fornecedor → produto" pendura num CNPJ solto. Prazo de entrega,
      contato e histórico de compra por fornecedor não têm onde morar
- [ ] **Contagem de estoque.** O lançamento de ajuste existe, por produto, na tela do
      produto. O que falta é a sessão de contagem: contar o estoque inteiro e gerar os
      ajustes de uma vez, com o que foi contado e por quem. Em loja de verdade divergência
      é regra, não exceção
- [ ] **Contratante do agro e cliente da base são duas tabelas.** `agro_client` nasceu antes
      do módulo `clientes` e guarda a mesma coisa com menos campos; uma empresa com os dois
      módulos cadastra a mesma fazenda duas vezes. Unificar é decisão de arquitetura e
      **precisa de ADR** — há planejamento assinado apontando para a tabela atual, e hash
      de documento que não pode mudar de significado.
      (`agro_product` **não** entra aqui: defensivo com formulação, classe toxicológica e
      registro no MAPA é coisa diferente de produto de prateleira)
- [ ] Recibo não fiscal em impressora térmica. Hoje o PDV não imprime nada. É a parte
      barata e sem dependência externa — e **não substitui** documento fiscal onde ele é
      exigido, o que precisa estar claro no produto e não só no código
- [ ] Emissão fiscal (NFC-e/SAT) como módulo próprio. É o que falta para o PDV substituir
      o caixa de uma loja de verdade, e é o que não pode ser suposto: certificado digital,
      homologação na SEFAZ do estado, contingência e layout versionado
- [ ] Abertura e fechamento de caixa (sangria, suprimento, conferência). Falta requisito
- [ ] Devolução de venda. Hoje venda finalizada não é cancelada, e a recusa diz por quê
- [ ] PDV offline-first
- [ ] Verticais sobre a base. **Cada uma exige documento real da operação**, como o agro
      exigiu o talão do MAPA. Sem isso vira suposição, que é o defeito que o projeto
      existe para não repetir:
  - [ ] Distribuidora de bebidas — cliente real alcançável, discovery da Fase 4
  - [ ] Supermercado, ferragista, lanchonete, restaurante, loja de veículos

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

## Transversal — qualidade da base

Não pertence a fase nenhuma: atravessa todas, e por isso some das listas por fase. Nenhum
destes itens é funcionalidade; todos são a diferença entre mexer no código com confiança e
mexer torcendo.

- [ ] **Teste automatizado no frontend — hoje são zero, e não há runner instalado.** O
      backend tem 558 testes contra banco real; a interface tem `oxlint` e `tsc -b`, que
      acusam erro de tipo e não acusam comportamento errado. Já custou caro: o quadro de
      assinatura travava no meio do traço, e a leitura meteorológica mostrava "0° (N)"
      quando a direção do vento era ausente — os dois só apareceram ao usar à mão. O que
      mais pede rede de proteção: identificação de produto na entrada por nota, troca de
      empresa, e o PDV
- [ ] **Navegação sem URL.** `App.tsx` é uma máquina de estado escrita à mão: não há link
      direto para um planejamento ou um produto, o botão voltar do navegador sai do
      sistema, e recarregar cai na tela inicial. Num ERP que se usa o dia inteiro isso é
      defeito diário, não detalhe. Mexer nisso toca toda tela, então quanto antes, mais
      barato
- [ ] **Refresh token em `localStorage`.** Exposto a XSS. A troca por cookie `httpOnly`
      exige tratar CSRF e mudar o backend — está em `apps/web/src/lib/session.ts`, e
      repetido aqui porque a pendência da Fase 1 saiu de vista quando a fase fechou

---

## Fora de escopo por ora

Registrado para não ser reintroduzido por engano:

- Microsserviços — ver `docs/ARCHITECTURE.md`, seção 1
- Fine-tuning de modelo — RAG resolve o caso de uso atual com custo muito menor
- Integração automatizada com o portal do MAPA — depende da resposta de Q1
- Módulos de supermercado, ferragista, restaurante e veículos — só após duas verticais validadas
