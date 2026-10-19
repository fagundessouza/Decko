import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { theme } from "./lib/session";
import "./styles.css";

// Aplicado antes do primeiro render: fazer isso dentro de um componente provocaria um
// clarão branco no modo escuro a cada abertura.
theme.apply(theme.get());

const container = document.getElementById("root");
if (!container) throw new Error("elemento #root não encontrado em index.html");

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
