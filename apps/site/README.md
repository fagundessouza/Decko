# Página pública do Decko

A landing de prospecção: HTML, CSS e um JavaScript. Sem framework, sem build, sem
dependência para instalar — `apps/site/` é o site inteiro, do jeito que vai para o ar.

Isso não é economia de esforço, é escolha. Página de prospecção é julgada pelo tempo até o
primeiro conteúdo aparecer, e nada carrega mais rápido do que um HTML com um CSS do lado.
O buscador também rende melhor o que é simples: sem hidratação, sem script bloqueando o
desenho, sem conteúdo que só existe depois que um bundle roda.

## Ver na máquina

```
npx serve apps/site -l 4321
```

Ou, de dentro do Claude Code, o alvo `site` do `.claude/launch.json`.

## Onde cada coisa mora

| Arquivo | O que é |
|---|---|
| `index.html` | A página inicial. Inclui os dados estruturados (JSON-LD) e as meta de compartilhamento |
| `pulverizacao-agricola.html` | Página por segmento: operador de ARP, relatório do MAPA, voo do drone |
| `pdv-para-loja.html` | Página por segmento: loja de balcão, PDV sem internet, estoque |
| `sistema-para-distribuidora.html` | Página por segmento: distribuidora e atacado |
| `estilo.css` | Todo o visual, com as cores da identidade (`#16A34A`, `#0F172A`) |
| `app.js` | O envio do formulário, a abertura dos modais e o ano do rodapé |
| `indexar.mjs` | Fala com o Google Search Console: entrega o sitemap e pergunta se a URL foi indexada |
| `robots.txt` | O que os robôs podem percorrer, e onde está o sitemap |
| `sitemap.xml` | A lista de páginas, para o buscador não depender de achar link por link |
| `llms.txt` | O resumo do produto para assistentes de IA — ver abaixo |
| `vercel.json` | Cabeçalhos de segurança e cache |
| `marca.svg` | O símbolo da marca, usado no cabeçalho das três páginas |
| `favicon.svg` | O mesmo símbolo dentro do quadrado escuro, para a aba do navegador |

## Antes de publicar: três arquivos que faltam

Nenhum é bloqueio para subir, e todos melhoram o resultado.

1. **`og.png`** — 1200×630, a imagem que aparece quando o link é colado no WhatsApp ou no
   LinkedIn. O `index.html` já aponta para ela. Sem o arquivo, o link vai sem imagem.
2. **A marca oficial** — `marca.svg` e `favicon.svg` são aproximações desenhadas aqui, a
   partir da folha de identidade. Quando o arquivo oficial for exportado, **substitua os
   dois arquivos** e pronto: nenhuma página precisa mudar, porque as três apontam para
   `/marca.svg`.
3. **`apple-touch-icon.png`** — 180×180, para quem salva o site na tela inicial do iPhone.

## O domínio: uma decisão que precisa ser tomada antes

Hoje `decko.app.br` serve **o sistema** (o aplicativo React, na Vercel). Uma landing page
de prospecção quer a raiz do domínio — é ela que o Google indexa e que as pessoas digitam.
O arranjo normal é:

| Endereço | O que serve |
|---|---|
| `decko.app.br` | esta página |
| `app.decko.app.br` | o sistema (onde o cliente entra) |
| `api.decko.app.br` | a API (já é assim) |

Mudar isso exige três passos, e o segundo é o que quebra se for esquecido:

1. Apontar o projeto do sistema na Vercel para `app.decko.app.br` e criar um projeto novo
   para `apps/site` na raiz.
2. **Acrescentar `https://app.decko.app.br` ao `DECKO_CORS_ORIGINS` da API**, senão o
   sistema passa a receber erro de CORS em toda chamada.
3. Conferir se o `VITE_API_URL` do sistema continua apontando para
   `https://api.decko.app.br`.

A página de prospecção **também** precisa estar no CORS, porque o formulário chama a API
direto do navegador: `https://decko.app.br` já está na lista.

## Publicar na Vercel

Projeto novo, apontando para esta pasta:

- **Root Directory:** `apps/site`
- **Framework Preset:** Other
- **Build Command:** (vazio)
- **Output Directory:** (vazio — a Vercel serve a pasta como está)

O `vercel.json` cuida dos cabeçalhos de segurança e do cache.

## Indexação: a ordem que funciona

### 1. Verificar o domínio no Search Console

<https://search.google.com/search-console> → **Adicionar propriedade** → **Domínio**
(`decko.app.br`). A propriedade de domínio é a certa aqui: ela cobre `www`, `app`, `api`,
`http` e `https` de uma vez, enquanto a de prefixo de URL cobre só o endereço exato.

A verificação é um registro **TXT** no DNS — no Registro.br ou na Cloudflare, onde o
domínio estiver apontado. O Google mostra o valor; ele entra como:

| Tipo | Nome | Valor |
|---|---|---|
| TXT | `@` (ou `decko.app.br`) | `google-site-verification=…` |

A propagação costuma levar minutos. **Não apague o registro depois** — o Google reconfere
de vez em quando, e sem ele a propriedade cai e as chamadas de API param.

> A alternativa, a meta `google-site-verification` no `<head>`, serve para propriedade de
> prefixo de URL e só vale para aquele endereço. Não é usada aqui: ela não autoriza a API
> no domínio todo, e teria de ser copiada em cada página nova.

### 2. Mandar o sitemap

Pela tela, em *Sitemaps* → `https://decko.app.br/sitemap.xml`. Ou pela API, que é o que o
`indexar.mjs` faz:

```
node apps/site/indexar.mjs sitemap
```

Só precisa ser refeito quando entra ou sai página. Depois disso o Google volta sozinho.

### 3. Pedir a indexação da primeira vez

*Inspeção de URL* → cole a URL → **Solicitar indexação**. Isto **não tem API de escrita**,
e é de propósito: é a única porta que o Google deixou para apressar uma página comum. Sem
esse empurrão, a primeira passada pode levar dias.

### 4. Conferir se o Google viu

```
node apps/site/indexar.mjs estado                       # todas as URLs do sitemap
node apps/site/indexar.mjs estado https://decko.app.br/ # uma só
```

Responde o que a tela de inspeção responde: cobertura, última passada do robô, **qual
canônica o Google escolheu** (pode não ser a que a página declara, e isso é um defeito
silencioso de SEO), veredito do robots e por qual sitemap a URL foi descoberta.

### 5. Bing Webmaster Tools

<https://www.bing.com/webmasters> — importa a verificação do Google em dois cliques, e é o
índice que o Copilot e parte do ChatGPT consultam.

## A conta de serviço que o `indexar.mjs` usa

As duas chamadas automatizáveis (entregar sitemap e inspecionar URL) exigem OAuth de conta
de serviço. Uma vez, no Google Cloud:

1. Projeto novo (ou um existente) → **APIs e serviços** → ative **Google Search Console
   API**. Se um dia o site publicar vaga de emprego, ative também a **Indexing API**.
2. **IAM** → **Contas de serviço** → criar. Sem papel nenhum no projeto: a autorização que
   importa não é do Cloud, é do Search Console.
3. Na conta criada → **Chaves** → **Adicionar chave** → JSON. O arquivo baixa uma vez só.
4. No Search Console, na propriedade → **Configurações** → **Usuários e permissões** →
   adicionar o `client_email` da conta de serviço como **Proprietário**. É este passo que
   as pessoas esquecem, e o erro que ele dá (403) não explica o motivo.

O JSON é credencial: **não entra no repositório.** Guarde fora da pasta do projeto e
aponte por variável de ambiente:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\Users\Lucas\.chaves\decko-search-console.json"
$env:DECKO_SEARCH_CONSOLE_PROPERTY = "sc-domain:decko.app.br"
node apps/site/indexar.mjs estado
```

`DECKO_SEARCH_CONSOLE_PROPERTY` é como o Search Console chama a propriedade:
`sc-domain:decko.app.br` para a de domínio (a do passo 1), ou `https://decko.app.br/` para
a de prefixo de URL. Errar isso dá 403, não 404.

Em CI, onde não há caminho de arquivo, use `DECKO_GOOGLE_SERVICE_ACCOUNT` com o JSON
inteiro vindo do segredo do runner.

## A Indexing API não serve para esta página

Ela existe, o `indexar.mjs` tem o comando `indexing`, e ela **não vai indexar a landing
page**. O Google aceita a chamada para qualquer URL, responde 200 e ignora o que não for
`JobPosting` ou `BroadcastEvent` — a documentação oficial é explícita. Quem a usa para
página comum vê o 200, conclui que funcionou, e espera por nada.

O comando ficou no script por dois motivos: porque a dúvida volta, e porque no dia em que o
site publicar vaga de emprego com dado estruturado `JobPosting` ela passa a valer de fato.
Até lá, o caminho é o dos passos 2 e 3: sitemap pela API, primeiro empurrão pela tela.

O que de fato empurra uma página comum, em ordem de efeito: ser a melhor resposta para uma
busca específica, estar no sitemap, receber link de fora, e carregar rápido.

### O que **não** acelera

Pagar não "amplifica a indexação orgânica": anúncio e busca orgânica são dois sistemas
separados no Google, e o dinheiro do primeiro não move a posição do segundo. O que o
anúncio faz é trazer visita enquanto o orgânico amadurece — e visita que chega e fica
melhora o orgânico com o tempo, de forma indireta.

O que move posição é, nesta ordem: ser a melhor resposta para uma busca específica, ter o
conteúdo legível pelo robô, e ser citado por outros sites. O primeiro item é conteúdo, não
configuração.

## Uma página por busca

As duas primeiras entraram em 18/11/2026, e a razão de serem **páginas** e não seções é
essa: o buscador classifica página por página. Quem digita "sistema para pulverização
agrícola" e quem digita "PDV que funciona sem internet" procuram coisas diferentes, e uma
página só disputaria as duas buscas sem ganhar nenhuma.

Cada página tem título, descrição, `canonical`, `BreadcrumbList` e **FAQ próprios** — as
perguntas não se repetem entre elas de propósito: FAQ repetido faz as páginas do mesmo
site competirem entre si.

**A página de distribuidora é de outro tipo, e isso é de propósito.** A vertical não
existe: o roadmap tem a Fase 4 em branco, sem entrevista e sem documento real em mãos.
Então ela vende o que já está pronto — embalagem em árvore, entrada por nota, lote e
validade, balcão — e diz, numa seção inteira, o que **não** existe: romaneio, acerto de
rota, pedido de vendedor externo. O convite no fim é de levantamento: "traga o seu
romaneio".

É a página fazendo o trabalho que a Fase 4 precisa. Vender a vertical antes de ver o
documento seria repetir exatamente o erro que o método do projeto existe para evitar — e o
cliente descobriria na implantação, que é o pior lugar possível.

**Restaurante não tem página**, pelo mesmo critério: o que o dono de restaurante quer é o
pedido chegando na cozinha, e isso não existe (oito perguntas em aberto em
`docs/discovery/restaurante-pedido-na-cozinha.md`). Uma página que não pudesse prometer
isso não teria o que dizer.

Para acrescentar a próxima:

1. Copie `pdv-para-loja.html` e troque título, descrição, `canonical`, o `BreadcrumbList`,
   o conteúdo e as perguntas.
2. Deixe o `<option>` do ramo já marcado como `selected` no formulário — quem chegou por
   aquela busca já disse o que faz.
3. Acrescente a URL ao `sitemap.xml` e ao `llms.txt`.
4. Ligue a página na home: link no cartão do módulo e no rodapé. Link interno é o que
   distribui força entre as páginas, e é de graça.

O cabeçalho e o rodapé são copiados em cada arquivo — é o preço de não ter build, e ele é
barato até umas seis páginas. Passando disso, vale um gerador simples; antes disso, um
build seria complexidade comprada sem necessidade.

## `llms.txt`: o que ele é, e o que ele não é

É um resumo do site em texto, pensado para assistentes de IA entenderem o produto sem
precisar interpretar HTML. Fica em `https://decko.app.br/llms.txt`.

**Não é um padrão adotado como o `robots.txt`.** Não há garantia de que ChatGPT, Gemini ou
Claude vão lê-lo. Ele custa um arquivo de texto e pode ajudar; não substitui o que de fato
pesa, que é o **JSON-LD** no `index.html` — esse sim é lido por buscador e por quem resume
páginas, e é ele que diz, em dado estruturado, quem é a empresa, o que é o produto e quais
são as perguntas frequentes.

Quando mudar o que o Decko faz, mude os dois: o `llms.txt` e o bloco `FAQPage` do
`index.html`. Descrição velha em dado estruturado é pior do que nenhuma — ela faz o
buscador afirmar com confiança algo que não é mais verdade.

## O tom do texto, e o que sustenta cada frase

A home foi reescrita três vezes em 19/11/2026, e cada volta tirou uma coisa. Vale registrar
o que saiu, porque a tendência é querer colocar de novo:

- **Nada de detalhe de infraestrutura.** "1,7 GB de memória do servidor" impressiona quem
  trabalha com TI e não diz nada a quem tem loja. O dono de ferragista quer saber se a fila
  anda, não onde o sistema roda.
- **Nada de número de artigo de norma.** "Portaria 298/2021, art. 10 e 11" na home era
  autoridade dirigida a ninguém. Na página de agro, onde o leitor convive com a norma, a
  tabela de conformidade ficou — sem o número do artigo na barra de prova.
- **Nada de "quem atende é quem escreve o sistema".** Quem entra em contato é um consultor,
  e é isso que a página promete.
- **O offline deixou de ser o assunto.** Era um dos quatro diferenciais e tinha virado o
  único. Hoje ele é uma linha da tabela de comparação e um cartão entre quatro.
- **Nenhuma menção a não emitir nota fiscal.** O módulo fiscal não existe ainda; a página
  não afirma nada sobre ele, em nenhum sentido.
- **XML virou "cadastro de produto automatizado".** O formato do arquivo é assunto de quem
  integra. Quem recebe mercadoria só quer não digitar.

O esqueleto da home segue a ordem em que a objeção aparece na cabeça de quem lê:

1. **Dor, no herói** — o estoque que não bate, em uma frase.
2. **Ganho em quatro palavras** (barra logo abaixo) — para quem passa o olho e não lê.
3. **As quatro dores**, cada uma com um modal "Como funciona".
4. **Comparação com o mercado** — "na hora de" × "o que costuma acontecer" × "no Decko".
5. **Para quem é** — seis ramos, cada um abrindo o detalhe em modal.
6. **Garantia / risco zero** — tira o medo de ficar preso.
7. **Perguntas**, as cinco que travam a decisão.
8. **Um consultor entra em contato** — o formulário.

**A regra dos três cliques, e por isso os modais.** Nada que decida a compra fica a mais de
três cliques da chegada: o ramo abre em modal, o "como funciona" abre em modal, e o
formulário está na mesma página. Ninguém precisa trocar de endereço para descobrir se o
sistema serve — e cada troca de página é gente que desiste no caminho. Os modais são
`<dialog>` nativo: foco preso, `Esc` que fecha e fundo inerte sem uma linha de script para
isso.

Os gatilhos usados, e por que cada um é honesto aqui:

| Gatilho | Como aparece | Por que não é mentira |
|---|---|---|
| Dor concreta | "descobrir no fim do mês que o estoque não bate" | É a reclamação que aparece em toda conversa de balcão |
| Custo da inação | compra repetida do que já tinha, falta do que vendia | Consequência direta de saldo que ninguém confere |
| Contraste de categoria | a tabela "o que costuma acontecer" × "no Decko" | Fala do padrão do mercado, nunca de uma empresa pelo nome |
| Simplicidade | "No mesmo dia", "só o que usa" | É assim que a contratação por ramo funciona |
| Garantia | dados em planilha, sem implantação, mensal | As três são verdade hoje |
| Baixo atrito | formulário de seis campos, sem cadastro e sem cartão | É o que o formulário faz |
| Novidade | "liga e desliga módulo quando quiser" | O módulo é instalável de verdade, não uma tela escondida |

**Prova social sem cliente para mostrar.** É o gatilho mais difícil aqui, porque o produto é
novo e não há depoimento nem logo autorizado. A saída foi não fingir, e também não ficar
explicando: a barra de prova fala de resultado ("Vende sempre", "Estoque certo", "No mesmo
dia", "Só o que usa") em vez de ocupar o lugar do mural de logos com uma confissão. A seção
que explicava **por que não há logo de cliente** saiu da home junto com o resto do texto
sobre o próprio projeto: ela tirava o leitor da decisão para falar de nós.

O que **não** entra: depoimento inventado, número de clientes, logo de quem não é cliente,
comparação nominal com concorrente, e promessa de funcionalidade que não existe. A seção
"o que ainda não existe" da página da distribuidora é parte do argumento de venda, e não
uma concessão.

### O benchmark que embasa o contraste

`docs/benchmark/odoo-20-comparativo.md` tem a comparação técnica feita com o ERP aberto
mais usado do mundo: 1,7 GB em disco, cada processo carregando 696 módulos, offline como
caso especial do PDV e não propriedade do sistema, e nenhum conceito de "contratar por
ramo". É daí que saem os três diferenciais da home — mas o nome da empresa **não** aparece
no site, pela regra abaixo.

## Marca de terceiro não entra no texto

Decisão do dono do projeto, em 18/11/2026: o site não cita o nome de aplicativo,
fabricante ou concorrente. O texto fala do **equipamento** e do **aplicativo que
acompanha o equipamento**, nunca do nome deles.

São dois motivos, e os dois valem. O primeiro é jurídico: marca registrada de terceiro em
página comercial é terreno de quem tem advogado, e o ganho é nenhum. O segundo é de
produto: citar um fabricante faz o cliente de outro achar que o Decko não serve para ele —
e o leitor de planilha de voo não liga para a marca do drone.

A documentação interna (`docs/`) continua citando formatos e nomes reais: lá a precisão é
que vale, e ninguém de fora lê.

## A esteira de marcas do rodapé

Hoje ela mostra os **segmentos atendidos**, e não logos de clientes. O motivo está na regra
1 do `CLAUDE.md`: nada de dado inventado. Logo de empresa que não é cliente é prova social
falsa, e com marca registrada no meio.

Quando houver a primeira marca de verdade — e **autorização por escrito de quem é dona
dela** —, troque cada `<span class="esteira__item">` por uma imagem:

```html
<img class="esteira__item" src="/marcas/agrodrone.svg" alt="Agrodrone" height="28" />
```

A animação continua funcionando: o trilho repete a lista duas vezes e desliza metade da
própria largura. Mantenha as duas cópias, e a segunda com `aria-hidden="true"` para o
leitor de tela não ler tudo em dobro.

## Para onde vai o lead

O formulário chama `POST https://api.decko.app.br/api/v1/core/leads` — a API do próprio
Decko. O pedido de contato cai no banco do dono do projeto, e não num serviço de terceiro
que ficaria com os dados de quem pediu contato.

Para ver e exportar:

- `GET /api/v1/core/plataforma/leads` — a lista, com `?pendentes=true` para quem ainda não
  foi atendido.
- `GET /api/v1/core/plataforma/leads.csv` — a planilha, que abre direto no Excel e no
  Sheets.
- `PUT /api/v1/core/plataforma/leads/{id}` — marcar que alguém já falou com a pessoa.

As três exigem a marca de plataforma na conta (`is_platform_admin`).

**O que ainda não existe:** aviso por e-mail quando um lead chega. Falta a caixa de e-mail
do domínio e as credenciais de SMTP; enquanto isso, a lista e a planilha são o controle.
