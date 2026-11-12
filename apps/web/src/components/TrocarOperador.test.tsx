import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TrocarOperador } from "./TrocarOperador";

/* A troca de operador no balcão.
 *
 * O que estes testes guardam é a `docs/adr/0020-operador-supervisor-e-papeis.md`,
 * decisão 1: **o crachá identifica, o PIN autentica**. Cartão perdido não pode ser a
 * conta de ninguém, e o nome que ficou escolhido de uma troca anterior não pode vencer
 * o cartão que acabou de ser passado. */

vi.mock("../lib/api", () => ({
  operadores: vi.fn(),
  entrarPorPin: vi.fn(),
}));

const { operadores, entrarPorPin } = await import("../lib/api");

const SESSAO = { user: { full_name: "Maria Operadora" } } as never;

beforeEach(() => {
  vi.mocked(operadores).mockResolvedValue([
    { id: "u-maria", nome: "Maria Operadora" },
    { id: "u-joao", nome: "João Caixa" },
  ]);
});

function abrir() {
  const usuario = userEvent.setup();
  const trocado = vi.fn();
  render(<TrocarOperador open onClose={() => {}} onTrocado={trocado} />);
  return { usuario, trocado };
}

describe("TrocarOperador", () => {
  it("entra pelo nome escolhido e o PIN", async () => {
    vi.mocked(entrarPorPin).mockResolvedValue(SESSAO);
    const { usuario, trocado } = abrir();

    await usuario.selectOptions(await screen.findByLabelText("Nome"), "u-joao");
    await usuario.type(screen.getByLabelText("PIN"), "7219");
    await usuario.click(screen.getByRole("button", { name: "Entrar" }));

    await waitFor(() =>
      expect(entrarPorPin).toHaveBeenCalledWith({ user_id: "u-joao", pin: "7219" }),
    );
    expect(trocado).toHaveBeenCalledWith(SESSAO);
  });

  it("o crachá lido vence o nome que ficou escolhido", async () => {
    // O nome sobra da troca anterior; quem está ali é quem passou o cartão agora.
    vi.mocked(entrarPorPin).mockResolvedValue(SESSAO);
    const { usuario } = abrir();

    await usuario.selectOptions(await screen.findByLabelText("Nome"), "u-joao");
    await usuario.type(screen.getByLabelText("Crachá"), "CRACHA-0042");
    await usuario.type(screen.getByLabelText("PIN"), "7219");
    await usuario.click(screen.getByRole("button", { name: "Entrar" }));

    await waitFor(() =>
      expect(entrarPorPin).toHaveBeenCalledWith({ cracha: "CRACHA-0042", pin: "7219" }),
    );
  });

  it("não entra sem PIN, nem com crachá", async () => {
    const { usuario } = abrir();
    await usuario.type(await screen.findByLabelText("Crachá"), "CRACHA-0042");

    // O crachá identifica; sozinho não entra.
    expect(screen.getByRole("button", { name: "Entrar" })).toHaveProperty("disabled", true);
  });

  it("Enter no crachá leva o foco ao PIN", async () => {
    // O leitor digita o código e dá Enter. É a sequência que a mão faz no balcão.
    const { usuario } = abrir();
    const cracha = await screen.findByLabelText("Crachá");

    await usuario.type(cracha, "CRACHA-0042{Enter}");

    expect(document.activeElement).toBe(screen.getByLabelText("PIN"));
    expect(entrarPorPin).not.toHaveBeenCalled();
  });

  it("PIN errado diz o motivo e limpa o campo", async () => {
    vi.mocked(entrarPorPin).mockRejectedValue(new Error("PIN incorreto."));
    const { usuario } = abrir();

    await usuario.type(await screen.findByLabelText("PIN"), "0000");
    await usuario.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByText("PIN incorreto.")).toBeTruthy();
    // Limpo, para a próxima tentativa começar do zero em vez de corrigir no escuro.
    expect(screen.getByLabelText<HTMLInputElement>("PIN").value).toBe("");
  });
});
