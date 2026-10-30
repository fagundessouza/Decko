import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { recibo, theme } from "./lib/session";
import "./styles.css";

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
