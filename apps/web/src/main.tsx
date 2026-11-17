import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { registerSW } from "virtual:pwa-register";

import App from "./App";
import { anunciarAtualizacao } from "./lib/pwa";
import { recibo, theme } from "./lib/session";
import "./styles.css";

/* Guarda o pacote no aparelho, para o Decko abrir sem rede.
 *
 * `onNeedRefresh` avisa que existe versão nova esperando; quem decide a hora de trocar é
 * quem está operando, porque recarregar no meio de uma venda perde a tela. */
const trocarVersao = registerSW({
  onNeedRefresh() {
    anunciarAtualizacao(trocarVersao);
  },
});

// Aplicado antes do primeiro render: fazer isso dentro de um componente provocaria um
// clarão branco no modo escuro a cada abertura.
theme.apply(theme.get());
// A largura do papel entra na mesma hora: ela é lida pelo CSS de impressão, e não por
// componente, então precisa estar na raiz antes de existir recibo para imprimir.
recibo.aplicar();

const container = document.getElementById("root");
if (!container) throw new Error("elemento #root não encontrado em index.html");

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
