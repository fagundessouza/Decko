import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProdutosPage } from "./ProdutosPage";

/* O catálogo da loja.
 *
 * O que este arquivo guarda é a fusão de 10/11/2026: cadastrar à mão e receber do
 * fornecedor eram duas telas que faziam a mesma coisa — criar produto e pôr estoque. A
 * segunda virou operação daqui, sobreposta, e sumiu do menu lateral. */

vi.mock("../lib/comercial", () => ({
  comercial: { listProdutos: vi.fn(), listUnidades: vi.fn() },
}));

vi.mock("../lib/compras", () => ({
  compras: { listNotas: vi.fn(), importarXml: vi.fn() },
}));

const { comercial } = await import("../lib/comercial");
const { compras } = await import("../lib/compras");

beforeEach(() => {
  vi.mocked(comercial.listProdutos).mockResolvedValue([]);
  vi.mocked(comercial.listUnidades).mockResolvedValue([]);
  vi.mocked(compras.listNotas).mockResolvedValue([]);
});

function abrir({ comNota = false } = {}) {
  const usuario = userEvent.setup();
  const abrirNota = vi.fn();
  render(
    <ProdutosPage
      onBack={() => {}}
      onOpen={() => {}}
      onNew={() => {}}
      onUnidades={() => {}}
      onConferencia={() => {}}
      onAbrirNota={comNota ? abrirNota : undefined}
    />,
  );
  return { usuario, abrirNota };
}

describe("ProdutosPage", () => {
  it("não oferece entrada por nota a quem não tem o módulo", async () => {
    abrir();
    expect(await screen.findByRole("button", { name: "Novo produto" })).toBeTruthy();

    expect(screen.queryByRole("button", { name: "Entrada por nota" })).toBeNull();
  });

  it("abre a entrada por nota sobreposta, sem sair do catálogo", async () => {
    const { usuario } = abrir({ comNota: true });

    await usuario.click(await screen.findByRole("button", { name: "Entrada por nota" }));

    // Diálogo de verdade: trava o catálogo atrás enquanto a nota entra.
    expect(await screen.findByRole("dialog")).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Importar XML" })).toBeTruthy();
  });
});
