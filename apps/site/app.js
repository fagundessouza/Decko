/* O formulário de contato da página pública.
 *
 * É o único JavaScript do site, e ele carrega com `defer`: a página inteira aparece e é
 * lida pelo buscador sem depender dele. Sem script, o formulário ainda mostra os campos —
 * o que ele perde é o envio, e aí o recado diz o que fazer.
 *
 * O destino é a API do próprio Decko: o lead cai no banco do dono do projeto, e não num
 * serviço de terceiro que ficaria com os dados de quem pediu contato.
 */

const API = "https://api.decko.app.br/api/v1/core/leads";

const formulario = document.getElementById("formulario");
const recado = document.getElementById("recado");
const ano = document.getElementById("ano");

if (ano) ano.textContent = String(new Date().getFullYear());

/** De onde a pessoa veio, quando a campanha diz.
 *
 * É o que separa anúncio pago de boca a boca no fim do mês. Sem isto, o dono do projeto
 * paga por tráfego sem saber qual parte dele vira conversa. */
function origem() {
  const url = new URL(window.location.href);
  const campanha = url.searchParams.get("utm_source") || url.searchParams.get("origem");
  if (campanha) return campanha.slice(0, 200);
  if (document.referrer && !document.referrer.includes(window.location.host)) {
    try {
      return new URL(document.referrer).hostname.slice(0, 200);
    } catch {
      return null;
    }
  }
  return "direto";
}

function dizer(texto, tom) {
  if (!recado) return;
  recado.textContent = texto;
  recado.className = `recado recado--${tom}`;
}

formulario?.addEventListener("submit", async (evento) => {
  evento.preventDefault();

  const campos = new FormData(formulario);
  const botao = formulario.querySelector("button[type=submit]");

  if (!campos.get("consentimento")) {
    dizer("Para a gente entrar em contato, marque a caixinha de aceite.", "erro");
    return;
  }

  const corpo = {
    nome: String(campos.get("nome") || "").trim(),
    email: String(campos.get("email") || "").trim(),
    empresa: String(campos.get("empresa") || "").trim() || null,
    telefone: String(campos.get("telefone") || "").trim() || null,
    segmento: String(campos.get("segmento") || "").trim() || null,
    mensagem: String(campos.get("mensagem") || "").trim() || null,
    // O campo-armadilha vai como veio: quem o preencheu foi um robô, e o servidor
    // responde "obrigado" sem gravar nada.
    site: String(campos.get("site") || ""),
    origem: origem(),
    consentimento: true,
  };

  if (botao) botao.disabled = true;
  dizer("Enviando…", "neutro");

  try {
    const resposta = await fetch(API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    });

    if (!resposta.ok) {
      // O servidor recusou por regra — e-mail inválido, enxurrada do mesmo lugar. A
      // mensagem dele é melhor do que qualquer texto genérico daqui.
      const detalhe = await resposta
        .json()
        .then((corpo) => corpo?.detail)
        .catch(() => null);
      dizer(
        typeof detalhe === "string"
          ? detalhe
          : "Não consegui enviar agora. Tente de novo em instantes.",
        "erro",
      );
      return;
    }

    formulario.reset();
    dizer(
      "Recebido. A gente entra em contato pelo WhatsApp ou e-mail que você deixou.",
      "certo",
    );
  } catch {
    // Sem rede, ou API fora. Não existe recado honesto além deste.
    dizer(
      "Não consegui falar com o servidor. Confira sua conexão e tente de novo.",
      "erro",
    );
  } finally {
    if (botao) botao.disabled = false;
  }
});

/* Os modais dos ramos e dos módulos.
 *
 * `<dialog>` nativo: sem biblioteca, com tecla Esc e devolução de foco funcionando de
 * graça. O detalhe abre na mesma página porque ninguém quer pular de tela em tela para
 * descobrir se o sistema serve para o ramo dele. */
for (const gatilho of document.querySelectorAll("[data-abre]")) {
  gatilho.addEventListener("click", () => {
    document.getElementById(gatilho.dataset.abre)?.showModal();
  });
}

for (const dialogo of document.querySelectorAll("dialog")) {
  // Clique fora da caixa fecha: é o gesto que todo mundo tenta primeiro.
  dialogo.addEventListener("click", (evento) => {
    if (evento.target === dialogo) dialogo.close();
  });
  for (const fecha of dialogo.querySelectorAll("[data-fecha]")) {
    fecha.addEventListener("click", () => dialogo.close());
  }
}
