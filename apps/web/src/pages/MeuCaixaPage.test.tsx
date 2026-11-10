import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Caixa } from "../lib/pdv";
import { MeuCaixaPage } from "./MeuCaixaPage";

/* A sessão de caixa do operador.
 *
 * O que estes testes guardam é a **conferência cega** da `docs/adr/0008-ponto-de-venda.md`:
 * enquanto o caixa está aberto, o quanto deveria haver na gaveta não aparece — nem na
 * tela, nem na resposta do servidor, que nem devolve o campo. Quem conta vendo o número
 * não confere, confirma. */

vi.mock("../lib/pdv", async (importar) => {
  const real = await importar<typeof import("../lib/pdv")>();
  return {
    ...real,
    pdv: {
      caixaAberto: vi.fn(),
      abrirCaixa: vi.fn(),
      movimentarCaixa: vi.fn(),
      fecharCaixa: vi.fn(),
    },
  };
});

const { pdv } = await import("../lib/pdv");

function umCaixa(sobre: Partial<Caixa> = {}): Caixa {
  return {
    id: "caixa-1",
    operador_id: "u-1",
    aberto_em: "2026-11-10T08:00:00-03:00",
    fechado_em: null,
    abertura: "100.00",
    contado: null,
    esperado: null,
    diferenca: null,
    observacao: null,
    movimentos: [],
    ...sobre,
  };
}

beforeEach(() => {
  vi.mocked(pdv.caixaAberto).mockResolvedValue(null);
});

describe("MeuCaixaPage, sem caixa aberto", () => {
  it("oferece abrir, com o fundo de troco", async () => {
    render(<MeuCaixaPage onBack={() => {}} />);

    expect(await screen.findByLabelText("Fundo de troco")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Abrir caixa" })).toBeTruthy();
  });

  it("manda o fundo com ponto, mesmo digitado com vírgula", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrirCaixa).mockResolvedValue(umCaixa());
    render(<MeuCaixaPage onBack={() => {}} />);

    const campo = await screen.findByLabelText("Fundo de troco");
    await usuario.clear(campo);
    await usuario.type(campo, "150,50");
    await usuario.click(screen.getByRole("button", { name: "Abrir caixa" }));

    await waitFor(() => expect(pdv.abrirCaixa).toHaveBeenCalledWith("150.50"));
  });
});

describe("MeuCaixaPage, com caixa aberto", () => {
  beforeEach(() => {
    vi.mocked(pdv.caixaAberto).mockResolvedValue(umCaixa());
  });

  it("não mostra em lugar nenhum o quanto deveria haver na gaveta", async () => {
    render(<MeuCaixaPage onBack={() => {}} />);
    expect(await screen.findByText("Fundo de troco")).toBeTruthy();

    // Nem a palavra, nem o número: ver o esperado antes de contar transforma a
    // conferência em confirmação.
    expect(screen.queryByText(/Esperado/)).toBeNull();
    expect(screen.queryByText(/Total das vendas|Recebido/)).toBeNull();
  });

  it("lança sangria com tipo, valor e motivo", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.movimentarCaixa).mockResolvedValue(umCaixa());
    render(<MeuCaixaPage onBack={() => {}} />);

    await usuario.click(await screen.findByRole("button", { name: "Lançar" }));
    await usuario.type(await screen.findByLabelText("Valor"), "30,00");
    await usuario.type(screen.getByLabelText("Motivo"), "Depósito no banco");
    await usuario.click(screen.getByRole("button", { name: "Lançar movimento" }));

    await waitFor(() =>
      expect(pdv.movimentarCaixa).toHaveBeenCalledWith("caixa-1", {
        tipo: "sangria",
        valor: "30.00",
        motivo: "Depósito no banco",
      }),
    );
  });

  it("mostra as retiradas já lançadas, com o motivo", async () => {
    vi.mocked(pdv.caixaAberto).mockResolvedValue(
      umCaixa({
        movimentos: [
          {
            id: "m-1",
            tipo: "sangria",
            valor: "30.00",
            motivo: "Depósito no banco",
            created_at: "2026-11-10T10:00:00-03:00",
          },
        ],
      }),
    );
    render(<MeuCaixaPage onBack={() => {}} />);

    expect(await screen.findByText("Sangria")).toBeTruthy();
    // O motivo fica visível na lista: é ele que explica a linha meses depois.
    expect(screen.getByText("Depósito no banco")).toBeTruthy();
  });

  it("só revela o esperado depois de a contagem ser enviada", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.fecharCaixa).mockResolvedValue(
      umCaixa({
        fechado_em: "2026-11-10T20:00:00-03:00",
        contado: "98.00",
        esperado: "100.00",
        diferenca: "-2.00",
      }),
    );
    render(<MeuCaixaPage onBack={() => {}} />);

    await usuario.click(await screen.findByRole("button", { name: "Fechar caixa" }));
    await usuario.type(await screen.findByLabelText("Quanto há na gaveta"), "98,00");
    await usuario.click(screen.getByRole("button", { name: "Confirmar fechamento" }));

    await waitFor(() =>
      expect(pdv.fecharCaixa).toHaveBeenCalledWith("caixa-1", { contado: "98.00" }),
    );
    // Só agora o número aparece — e junto da diferença, que é o produto da conferência.
    expect(await screen.findByText("Esperado pelo sistema")).toBeTruthy();
    expect(screen.getByText(/falta de/)).toBeTruthy();
  });

  it("diz que bateu quando não há diferença", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.fecharCaixa).mockResolvedValue(
      umCaixa({
        fechado_em: "2026-11-10T20:00:00-03:00",
        contado: "100.00",
        esperado: "100.00",
        diferenca: "0.00",
      }),
    );
    render(<MeuCaixaPage onBack={() => {}} />);

    await usuario.click(await screen.findByRole("button", { name: "Fechar caixa" }));
    await usuario.type(await screen.findByLabelText("Quanto há na gaveta"), "100,00");
    await usuario.click(screen.getByRole("button", { name: "Confirmar fechamento" }));

    expect(await screen.findByText("Bateu certo.")).toBeTruthy();
    expect(screen.queryByText(/falta de|sobra de/)).toBeNull();
  });
});
