import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { MeuPin } from "./MeuPin";

/* O PIN de entrada rápida.
 *
 * O que este arquivo guarda é a razão de a senha ser pedida: sem ela, um terminal
 * deixado aberto no balcão permitiria a qualquer um gravar um PIN próprio na conta alheia
 * e voltar nela quando quisesse — `docs/adr/0020-operador-supervisor-e-papeis.md`. */

vi.mock("../lib/api", () => ({ equipe: { definirPin: vi.fn() } }));

const { equipe } = await import("../lib/api");

async function preencher(senha: string, pin: string, repetido: string) {
  const usuario = userEvent.setup();
  render(<MeuPin open onClose={() => {}} />);

  if (senha) await usuario.type(screen.getByLabelText("Sua senha"), senha);
  if (pin) await usuario.type(screen.getByLabelText("PIN novo"), pin);
  if (repetido) await usuario.type(screen.getByLabelText("Repita o PIN"), repetido);
  return usuario;
}

function botao() {
  return screen.getByRole("button", { name: "Salvar PIN" });
}

describe("MeuPin", () => {
  it("guarda o PIN com a senha de quem está definindo", async () => {
    vi.mocked(equipe.definirPin).mockResolvedValue(undefined);
    const usuario = await preencher("senha-da-maria-123", "7219", "7219");

    await usuario.click(botao());

    await waitFor(() =>
      expect(equipe.definirPin).toHaveBeenCalledWith("senha-da-maria-123", "7219"),
    );
    expect(await screen.findByText(/PIN guardado/)).toBeTruthy();
  });

  it("não salva sem a senha", async () => {
    await preencher("", "7219", "7219");
    expect(botao()).toHaveProperty("disabled", true);
  });

  it("não salva PIN curto nem com letra", async () => {
    await preencher("senha-da-maria-123", "721", "721");
    expect(botao()).toHaveProperty("disabled", true);
  });

  it("não salva quando os dois não batem", async () => {
    await preencher("senha-da-maria-123", "7219", "7218");

    expect(screen.getByText("Os dois não estão iguais.")).toBeTruthy();
    expect(botao()).toHaveProperty("disabled", true);
  });

  it("mostra o motivo quando o servidor recusa", async () => {
    vi.mocked(equipe.definirPin).mockRejectedValue(new Error("A senha não confere."));
    const usuario = await preencher("chute", "7219", "7219");

    await usuario.click(botao());

    expect(await screen.findByText("A senha não confere.")).toBeTruthy();
  });
});
