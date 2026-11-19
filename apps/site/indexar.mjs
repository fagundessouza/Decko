/* Faz o Google saber que o site existe, e conferir o que ele achou dele.
 *
 * Três comandos, nesta ordem de utilidade real:
 *
 *   node indexar.mjs sitemap            → entrega o sitemap.xml ao Search Console
 *   node indexar.mjs estado [url...]    → pergunta ao Search Console se a URL está indexada
 *   node indexar.mjs indexing [url...]  → chama a Indexing API (leia o aviso abaixo)
 *
 * AVISO SOBRE A INDEXING API — o Google aceita a chamada para qualquer URL, responde 200 e
 * ignora páginas que não sejam JobPosting ou BroadcastEvent. Ela não serve para apressar a
 * indexação de uma landing page: a documentação oficial é explícita quanto a isso. Está aqui
 * porque é pedida com frequência, e porque no dia em que o site publicar vaga de emprego
 * (JobPosting) ela passa a valer. Para página comum, o que funciona é sitemap + "Solicitar
 * indexação" na inspeção de URL do Search Console, que não tem API de escrita.
 *
 * Credencial: conta de serviço do Google Cloud, nunca em código.
 *
 *   GOOGLE_APPLICATION_CREDENTIALS=/caminho/para/conta-de-servico.json
 *   ou DECKO_GOOGLE_SERVICE_ACCOUNT='{"client_email":...,"private_key":...}'
 *
 * O e-mail da conta de serviço precisa estar como proprietário da propriedade no Search
 * Console (Configurações → Usuários e permissões), e a propriedade precisa existir antes.
 * O passo a passo está no README desta pasta.
 */

import { createSign } from "node:crypto";
import { readFileSync } from "node:fs";
import { argv, env, exit } from "node:process";

/* A origem é o endereço do site; a propriedade é como o Search Console chama ele. Os dois
 * existem separados porque propriedade de domínio (a verificada por DNS, que cobre
 * subdomínio e http junto) se escreve `sc-domain:decko.app.br`, e isso não é uma URL. */
const ORIGEM = env.DECKO_SITE_URL ?? "https://decko.app.br/";
const PROPRIEDADE = env.DECKO_SEARCH_CONSOLE_PROPERTY ?? ORIGEM;
const SITEMAP = new URL("sitemap.xml", ORIGEM).href;

const ESCOPOS = {
  sitemap: "https://www.googleapis.com/auth/webmasters",
  estado: "https://www.googleapis.com/auth/webmasters.readonly",
  indexing: "https://www.googleapis.com/auth/indexing",
};

/** A credencial, do arquivo ou da variável com o JSON inteiro. Falha cedo e explicada: um
 *  erro de autenticação no meio da chamada é muito mais difícil de ler do que este. */
function credencial() {
  const inline = env.DECKO_GOOGLE_SERVICE_ACCOUNT;
  const caminho = env.GOOGLE_APPLICATION_CREDENTIALS;

  if (!inline && !caminho) {
    throw new Error(
      "Falta a credencial. Defina GOOGLE_APPLICATION_CREDENTIALS com o caminho do JSON " +
        "da conta de serviço, ou DECKO_GOOGLE_SERVICE_ACCOUNT com o JSON inteiro.",
    );
  }

  const bruto = inline ?? readFileSync(caminho, "utf8");
  const conta = JSON.parse(bruto);

  if (!conta.client_email || !conta.private_key) {
    throw new Error("A credencial não tem client_email e private_key — não é conta de serviço.");
  }
  return conta;
}

function base64url(dado) {
  return Buffer.from(dado).toString("base64url");
}

/** Troca a conta de serviço por um token de acesso. É o fluxo JWT Bearer do OAuth 2: a
 *  gente assina uma afirmação com a chave privada e o Google devolve o token. Feito à mão
 *  porque o site não tem dependência nenhuma, e não vale ganhar uma por causa disto. */
async function token(escopo) {
  const conta = credencial();
  const agora = Math.floor(Date.now() / 1000);

  const cabecalho = base64url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const corpo = base64url(
    JSON.stringify({
      iss: conta.client_email,
      scope: escopo,
      aud: conta.token_uri ?? "https://oauth2.googleapis.com/token",
      iat: agora,
      exp: agora + 3600,
    }),
  );

  const assinatura = createSign("RSA-SHA256")
    .update(`${cabecalho}.${corpo}`)
    .sign(conta.private_key)
    .toString("base64url");

  const resposta = await fetch(conta.token_uri ?? "https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
      assertion: `${cabecalho}.${corpo}.${assinatura}`,
    }),
  });

  const dado = await resposta.json();
  if (!resposta.ok) {
    throw new Error(`Autenticação recusada (${resposta.status}): ${JSON.stringify(dado)}`);
  }
  return dado.access_token;
}

/** As URLs do sitemap, quando o comando não recebe nenhuma. Ler o próprio sitemap evita a
 *  lista duplicada que envelhece em silêncio. */
function urlsDoSitemap() {
  const xml = readFileSync(new URL("sitemap.xml", import.meta.url), "utf8");
  const achadas = [...xml.matchAll(/<loc>\s*([^<\s]+)\s*<\/loc>/g)].map((m) => m[1]);
  if (achadas.length === 0) throw new Error("Nenhuma <loc> no sitemap.xml.");
  return achadas;
}

// ------------------------------------------------------------------ comandos

/* O sitemap só precisa ser entregue de novo quando entra ou sai página — depois disso o
 * Google volta sozinho. Entregar todo dia não acelera nada. */
async function enviarSitemap() {
  const acesso = await token(ESCOPOS.sitemap);
  const alvo =
    `https://www.googleapis.com/webmasters/v3/sites/${encodeURIComponent(PROPRIEDADE)}` +
    `/sitemaps/${encodeURIComponent(SITEMAP)}`;

  const resposta = await fetch(alvo, {
    method: "PUT",
    headers: { Authorization: `Bearer ${acesso}` },
  });

  if (!resposta.ok) {
    throw new Error(
      `Search Console recusou o sitemap (${resposta.status}): ${await resposta.text()}\n` +
        `Confira se a propriedade ${PROPRIEDADE} existe e se a conta de serviço é proprietária dela.`,
    );
  }
  console.log(`sitemap entregue: ${SITEMAP}`);
}

/* A inspeção de URL responde o que o Search Console mostra na tela: se está indexada, por
 * qual sitemap foi descoberta, qual é a canônica escolhida pelo Google — que pode não ser a
 * que a página declara — e o veredito do robots. É a parte da API que mais serve no dia a
 * dia, porque responde "ele viu?" sem abrir o navegador. */
async function estado(urls) {
  const acesso = await token(ESCOPOS.estado);

  for (const url of urls) {
    const resposta = await fetch(
      "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${acesso}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ inspectionUrl: url, siteUrl: PROPRIEDADE, languageCode: "pt-BR" }),
      },
    );

    const dado = await resposta.json();
    if (!resposta.ok) {
      console.error(`${url} → erro ${resposta.status}: ${JSON.stringify(dado)}`);
      continue;
    }

    const i = dado.inspectionResult?.indexStatusResult ?? {};
    console.log(
      [
        url,
        `  cobertura: ${i.coverageState ?? "?"}`,
        `  indexada em: ${i.lastCrawlTime ?? "ainda não rastreada"}`,
        `  canônica do Google: ${i.googleCanonical ?? "?"}`,
        `  robots: ${i.robotsTxtState ?? "?"} · indexação: ${i.indexingState ?? "?"}`,
        `  descoberta por: ${(i.sitemap ?? ["nenhum sitemap"]).join(", ")}`,
      ].join("\n"),
    );
  }
}

/* Ver o aviso no topo do arquivo antes de confiar nesta chamada. */
async function indexing(urls) {
  const acesso = await token(ESCOPOS.indexing);
  console.warn(
    "aviso: a Indexing API só tem efeito em JobPosting e BroadcastEvent. Para página " +
      "comum, use `sitemap` e a solicitação manual de indexação no Search Console.",
  );

  for (const url of urls) {
    const resposta = await fetch("https://indexing.googleapis.com/v3/urlNotifications:publish", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${acesso}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ url, type: "URL_UPDATED" }),
    });

    const dado = await resposta.json();
    console.log(
      resposta.ok
        ? `${url} → aceita em ${dado.urlNotificationMetadata?.latestUpdate?.notifyTime ?? "?"}`
        : `${url} → erro ${resposta.status}: ${JSON.stringify(dado)}`,
    );
  }
}

// ------------------------------------------------------------------ entrada

const [comando, ...resto] = argv.slice(2);
const urls = resto.length > 0 ? resto : urlsDoSitemap();

try {
  if (comando === "sitemap") await enviarSitemap();
  else if (comando === "estado") await estado(urls);
  else if (comando === "indexing") await indexing(urls);
  else {
    console.error("uso: node indexar.mjs sitemap | estado [url...] | indexing [url...]");
    exit(2);
  }
} catch (erro) {
  console.error(erro.message);
  exit(1);
}
