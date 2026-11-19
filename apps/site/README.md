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
| `index.html` | A página. Inclui os dados estruturados (JSON-LD) e as meta de compartilhamento |
| `estilo.css` | Todo o visual, com as cores da identidade (`#16A34A`, `#0F172A`) |
| `app.js` | Só o envio do formulário e o ano do rodapé |
| `robots.txt` | O que os robôs podem percorrer, e onde está o sitemap |
| `sitemap.xml` | A lista de páginas, para o buscador não depender de achar link por link |
| `llms.txt` | O resumo do produto para assistentes de IA — ver abaixo |
| `vercel.json` | Cabeçalhos de segurança e cache |
| `favicon.svg` | Marca provisória, desenhada em SVG |

## Antes de publicar: três arquivos que faltam

Nenhum é bloqueio para subir, e todos melhoram o resultado.

1. **`og.png`** — 1200×630, a imagem que aparece quando o link é colado no WhatsApp ou no
   LinkedIn. O `index.html` já aponta para ela. Sem o arquivo, o link vai sem imagem.
2. **`logo.svg`** — a marca exportada do material de identidade. Hoje o cabeçalho desenha
   um símbolo provisório em CSS (`.marca__simbolo`), e o favicon é um SVG aproximado.
   Quando o arquivo oficial existir, troque os dois.
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

1. **Google Search Console** — <https://search.google.com/search-console>. Adicione a
   propriedade **de domínio** (`decko.app.br`), que cobre todos os subdomínios; a
   verificação é um registro TXT no Registro.br ou na Cloudflare, onde o DNS estiver.
2. **Mande o sitemap** em *Sitemaps* → `https://decko.app.br/sitemap.xml`.
3. **Peça a indexação da página** em *Inspeção de URL* → "Solicitar indexação". Sem isso o
   Google pode levar dias para passar na primeira vez.
4. **Bing Webmaster Tools** — <https://www.bing.com/webmasters>. Importa a verificação do
   Google em dois cliques, e é o índice que o Copilot e parte do ChatGPT consultam.
5. Depois, confira em *Experiência na página* se algo ficou lento ou quebrado no celular.

### O que **não** acelera

Pagar não "amplifica a indexação orgânica": anúncio e busca orgânica são dois sistemas
separados no Google, e o dinheiro do primeiro não move a posição do segundo. O que o
anúncio faz é trazer visita enquanto o orgânico amadurece — e visita que chega e fica
melhora o orgânico com o tempo, de forma indireta.

O que move posição é, nesta ordem: ser a melhor resposta para uma busca específica, ter o
conteúdo legível pelo robô, e ser citado por outros sites. O primeiro item é conteúdo, não
configuração — por isso a próxima coisa a fazer nesta página é uma seção por segmento
("sistema para pulverização agrícola", "PDV para loja de balcão"), cada uma respondendo a
busca que o cliente daquele ramo realmente digita.

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
