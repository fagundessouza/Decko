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

- [x] Definição de nome, posicionamento e modelo de negócio. ~~Open Core + SaaS~~ — trocado
      em 30/10/2026 por **produto fechado, vendido por assinatura**; ver `docs/NEGOCIO.md`
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
- [x] **Administração da equipe pelo dono da loja.** Até 10/11/2026 as permissões
      `core.user.*` e `core.role.*` existiam no manifesto e **não tinham rota nenhuma por
      trás**: só o `decko-admin bootstrap`, na linha de comando do servidor, criava gente.
      Agora o dono cria a pessoa, escolhe o papel e liga ou desliga o acesso, com tudo na
      trilha. Papel sugerido é declarado pelo manifesto do módulo (`[[roles]]`), criado na
      empresa que não o tem e **nunca mais tocado**. Quem é criado entra com senha inicial
      e é obrigado a trocá-la — sem isso o dono conhece a senha do operador e "quem fez"
      é contestável. Decisão: `docs/adr/0020-operador-supervisor-e-papeis.md`
- [ ] Criar e editar papel pela interface (`core.role.write`). Hoje o dono **escolhe**
      entre os papéis semeados, que é o que o Odoo tem nativamente — montar um do zero é
      o passo seguinte
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
- [x] Módulo `assinaturas`: plano, assinante e a cobrança de cada mês, com a regra de
      inadimplência inteira — aviso, cinco dias contados do **vencimento**, bloqueio, e o
      **prazo de confiança** concedido à mão, com motivo e rastro na trilha. O estado de
      acesso é derivado, nunca coluna; o valor da cobrança é cópia do preço, nunca
      referência. Sem gateway: a cobrança nasce aberta e recebe baixa à mão — ver
      `docs/adr/0013-assinatura-recorrente.md`. É este "sem gateway" que a
      `docs/adr/0017-meios-de-pagamento.md` decidiu como fechar; com quem, ainda não.
      **Bloquear marca o estado; não corta acesso de ninguém** — suspender empresa é ato
      do núcleo, e os clientes da Decko ainda não existem como empresas num sistema no ar
- [x] Tela de assinaturas: ordenada pela preocupação — bloqueada, em aviso, em dia — com
      dar baixa, dar prazo e gerar o mês. O cartão explica pela cobrança que **decide** o
      bloqueio, não pela mais antiga: as duas divergem quando há várias em aberto
- [x] Perfil `decko`: o próprio produto usa o próprio produto — clientes e assinaturas
- [x] **Nível de plataforma.** Em 13/11/2026 a primeira empresa cliente entrou de verdade
      — Agrodrone — e não aparecia em lugar nenhum: `tenant` é tabela da plataforma, e a
      carteira de clientes vive dentro da empresa `decko`. Eram dois lados da fronteira de
      isolamento sem nada ligando. Agora há uma marca de **pessoa**
      (`user_account.is_platform_admin`, ligada só pela linha de comando), a tela "Meus
      clientes" que lista as empresas, e o `tenant_assinante_id` no contato, que diz a quem
      aquela assinatura dá acesso. Nenhum papel concede a marca, e **nada nesta fatia lê de
      dentro de empresa alheia** — ver `docs/adr/0021-nivel-de-plataforma.md`
- [ ] Suspender o acesso de quem não paga: é ato do núcleo, na autenticação, e espera três
      respostas — o que acontece com quem está no meio de uma venda, o que o bloqueado vê,
      e como o pagamento devolve o acesso sem alguém passar na mão. Decisão 5 da ADR 0021
- [ ] Captura de pagamento, em módulo próprio atrás da porta decidida na
      `docs/adr/0017-meios-de-pagamento.md`. Não está agendado: começa quando houver
      cliente pedindo. Quatro coisas bloqueiam antes do código — qual agregador, se a
      captura é pela API ou pela maquininha do balcão, onde guardar a credencial do
      provedor por empresa, e quem faz a conciliação
- [ ] Entrada de nota por QR code: depende de certificado digital A1/A3 e de manifestação
      do destinatário. O QR do cupom não carrega os itens
- [ ] Entrada de nota por PDF do DANFE: depende do OCR da Fase 6
- [x] **Implantação em servidor próprio.** `infra/tvbox/` instala o Decko num ARM pequeno
      com um comando: PostgreSQL 18 da PGDG com os dados em disco externo, dois papéis sem
      BYPASSRLS, serviços no boot, túnel e cópia diária que se testa restaurando. Feito num
      TV box Amlogic S912 com 1,7 GB de RAM em 09/11/2026. **O backup ainda não sai da
      máquina** — enquanto não sair, o item de backup do `NEGOCIO.md` continua aberto
- [ ] **Pedido do caixa para a cozinha.** Restaurante do setor do dono do projeto: hoje
      entrega ficha de papel e o cliente caminha até o fundo, onde a fila se forma de novo.
      Quer que o pedido apareça lá sozinho. **Não precisa de emissão fiscal** — é dor de
      operação, como a do agro, e por isso é vendável antes do bloqueio mais caro. Oito
      perguntas em aberto em `docs/discovery/restaurante-pedido-na-cozinha.md`, e a que
      decide tudo é como o cliente fica sabendo que o pedido saiu. Exige mecanismo que o
      sistema não tem: hoje toda tela pergunta ao servidor, e uma cozinha precisa ser avisada
- [ ] **Offline-first.** Escrita nasce no aparelho, identidade vem da origem, fila
      sincroniza sozinha e a API aceita o mesmo pacote duas vezes sem duplicar — ver
      `docs/adr/0019-offline-first.md`. O servidor continua sendo o dono: o aparelho só
      adianta a escrita. Atravessa todos os módulos e **não começa** antes de **cinco**
      respostas: regra de conflito por entidade, prazo máximo offline, o que fica disponível
      sem rede, permissão revogada durante a ausência, e para quais telas isto paga o custo.
      A sexta — estoque negativo — foi respondida em 04/11/2026: a venda subtrai, o saldo
      pode ficar negativo, e a divergência **aparece** na sincronização, porque é ela que o
      dono da loja quer ver
- [ ] Modelo do documento fiscal, desenhado para atravessar a transição sem reescrita:
      documento é entidade própria e não coluna na venda, tributo é linha e não coluna, e o
      que foi autorizado é guardado como foi e nunca recalculado — ver
      `docs/adr/0018-modelo-fiscal-na-transicao.md`. Duas mudanças dali podem ser feitas
      antes da emissão: **CPF avulso no cupom** (hoje identificar é apontar para um cliente
      cadastrado) e **terminal de caixa**, que não existe como entidade
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
- [x] **Desconto na venda pela tela do PDV.** O servidor aceitava desde sempre e nenhuma
      tela chamava; agora o caixa dá e altera desconto, e o botão diz qual dos dois faz.
      A regra continua inteira no servidor — não negativo, não maior que a soma, só em
      venda aberta —, a tela só oferece o caminho
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
- [x] Recibo não fiscal em impressora térmica: cabeçalho da empresa com CNPJ e inscrição,
      itens, totais, formas de pagamento, troco e o cliente quando a venda é identificada.
      Sai pela impressora do sistema, que é como a térmica de balcão aparece no Windows.
      Largura escolhida por estação, 58 ou 80 mm — a mesma regra do tema no `BRAND.md`.
      **O papel diz "NÃO É DOCUMENTO FISCAL"**, porque onde a nota é exigida este recibo
      não a substitui
- [ ] Emissão fiscal (NFC-e/SAT) como módulo próprio. É o que falta para o PDV substituir
      o caixa de uma loja de verdade, e é o que não pode ser suposto: certificado digital,
      homologação na SEFAZ do estado, contingência e layout versionado
- [x] **Conta de recebimento no pagamento.** Módulo `financeiro` com o cadastro de
      destinos — banco, chave Pix, gaveta do caixa — e o pagamento do PDV apontando para
      um. Dois Pix na mesma venda podem cair em contas diferentes, que era o caso descrito.
      **Opcional de propósito**: o balcão não para para escolher conta. Não é plano de
      contas e não guarda saldo — ver `docs/adr/0014-conta-de-recebimento.md`
- [x] **Conferência de caixa.** O relatório que a cliente queria: quanto entrou, por forma
      de pagamento, por conta e por operador, com cancelamentos contados à parte. A
      contagem vem **antes** do esperado, como a ADR 0008 decidiu — quem conta vendo o
      número não confere, confirma. Conta-se só o dinheiro em espécie, porque é o que está
      na gaveta
- [x] **Abertura e fechamento de caixa.** Sessão por operador, sangria e suprimento com
      motivo obrigatório, e fechamento com contagem cega — o esperado não sai do servidor
      enquanto o caixa está aberto. Diferença nunca impede fechar. Decisão na atualização
      de 10/11/2026 da `docs/adr/0008-ponto-de-venda.md`; as sete perguntas que a
      destravaram estão em `docs/discovery/pdv-fechamento-de-caixa.md`
- [x] **Autorização do supervisor.** Seis ações podem exigir a credencial de quem pode
      liberar: cancelar item, cancelar venda, sangria, devolução, desconto acima do limite
      e fechamento com diferença acima do limite. A credencial vai **junto com a ação** e é
      conferida no servidor — destravar a tela seria teatro. A trilha guarda as duas
      pessoas. Cada loja liga o que quiser; as que dependem de um número nascem desligadas,
      porque o limite é dela. Decisão: `docs/adr/0020-operador-supervisor-e-papeis.md`
- [x] **As operações de caixa vivem dentro do PDV**, como diálogos sobrepostos, e não como
      telas irmãs no menu. As teclas F1–F4 passaram a ser do PDV o tempo inteiro: antes só
      valiam com venda e item na tela, e no resto do expediente F1 abria a ajuda do
      navegador por cima do caixa
- [x] **Entrada rápida por PIN e crachá.** Troca de operador no balcão sem digitar
      empresa, e-mail e senha — só a partir de uma estação já autenticada, que é o que
      sustenta quatro dígitos. O crachá é lido pelo leitor de código de barras, que já
      funciona como teclado, e identifica; quem autentica é o PIN. Cinco erros bloqueiam
      por cinco minutos, com contagem única entre a troca de operador e a liberação do
      supervisor. Decisão: `docs/adr/0020-operador-supervisor-e-papeis.md`
- [x] **Papéis por módulo, não só no caixa.** O `agro` passou a sugerir Piloto e
      Responsável técnico pelo manifesto, sem código novo — e quem assina é o responsável,
      que é o papel que o formulário do MAPA nomeia
- [x] **As operações do caixa estão todas dentro do PDV**, inclusive trocar de operador,
      definir o próprio PIN e os ajustes do que exige supervisor. Nada disso é item de
      menu lateral: passar o turno é operação de balcão
- [x] **Entrada por nota entrou em "Produtos e estoque".** Cadastrar à mão e receber do
      fornecedor eram duas telas que faziam a mesma coisa — criar produto e pôr estoque.
      A conferência continua tela inteira, porque casar item por item é trabalho longo
- [x] **O ponto de venda abre no nome de quem vai operar.** A pergunta vem antes de haver
      venda, e a saída está escrita no próprio diálogo. É configuração, ligada por padrão
      e desligável nos ajustes
- [ ] Biometria (Digital Persona, facial) para o mesmo fim. **Depende da ADR de
      periféricos**: o navegador não alcança o leitor, e isso exige agente local
- [ ] Periféricos por serial, Bluetooth e TEF. **Precisa de ADR**: o navegador não alcança
      porta serial no iOS, e TEF pede agente local no Windows — o que cria um segundo
      executável para instalar e atualizar na casa do cliente. O leitor de código de barras
      **já funciona** sem nada disso, porque se apresenta como teclado
- [x] **Devolução de venda.** Documento novo que aponta para a venda, que continua
      `finalizada` e congelada. Parcial por linha, com **destino por linha**: o que volta
      para vender entra na razão como entrada, o que tem defeito não entra e vira avaria.
      Devolução em espécie sai da gaveta e o fechamento já conta com ela; cartão e Pix só
      ficam registrados, porque o estorno é da adquirente. O valor é rateado pelo servidor,
      com o desconto da venda embutido. Decisão na atualização de 10/11/2026 da
      `docs/adr/0008-ponto-de-venda.md`; o requisito, em
      `docs/discovery/pdv-devolucao-de-venda.md`
- [ ] PDV offline-first
- [ ] Verticais sobre a base. **Cada uma exige documento real da operação**, como o agro
      exigiu o talão do MAPA. Sem isso vira suposição, que é o defeito que o projeto
      existe para não repetir:
  - [ ] Distribuidora de bebidas — cliente real alcançável, discovery da Fase 4
  - [ ] Supermercado, ferragista, lanchonete, restaurante, loja de veículos

## Fase 6 — Camada de inteligência

- [ ] **Preencher o relatório de voo a partir do arquivo do equipamento.** O Nathan pediu
      em 13/11/2026: *"seria top se desse para conectar com esse app"*. **Não existe API
      pública do SmartFarm**, e o registro de voo que fica no controle é criptografado — o
      caminho viável é importar a planilha que ele já exporta, como o `compras` faz com o
      XML. Apuração e perguntas em aberto na seção 7 do
      `docs/discovery/agro-planejamento-operacional.md`
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

- [ ] **Teste automatizado no frontend — o executor existe desde 03/11/2026, e cobre
      três pontos.** Vitest com jsdom e Testing Library, na esteira junto do lint e dos
      tipos, com o fuso fixado em `America/Sao_Paulo` (sem isso o teste de data local
      passaria por engano na esteira, que roda em UTC). São 50 testes: o foco do `Modal`,
      as funções de `format.ts`, e o PDV — leitor de código de barras, recebimento,
      fechamento, atalhos F1 a F4, identificação do cliente, conta de recebimento e as
      três operações que desfazem (retirar item, retirar pagamento, cancelar). O backend
      tem 643 contra banco real.

      Cada um nasceu de defeito que aconteceu: o teclado do celular fechava a cada letra
      digitada em qualquer diálogo, o quadro de assinatura travava no meio do traço, e a
      leitura meteorológica mostrava "0° (N)" quando a direção do vento era ausente.
      Nenhum é erro de tipo, então nem `oxlint` nem `tsc -b` tinham como ver.

      Os testes do PDV foram conferidos por mutação — quebrando a tela de um jeito por
      vez e exigindo que reprovassem. Valeu a pena: o teste de foco passava com o defeito
      posto de volta, porque digitar no campo de código já deixa o foco nele. O caminho
      em que o foco se perde é o do mouse, e é esse que o teste faz agora.

      O que ainda pede rede: identificação de produto na entrada por nota, troca de
      empresa, e a identificação do cliente na venda
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
