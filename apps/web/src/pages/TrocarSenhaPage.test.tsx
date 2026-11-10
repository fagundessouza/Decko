import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TrocarSenhaPage } from "./TrocarSenhaPage";

/* A troca obrigatória da senha inicial.
 *
 * Não é conveniência: é o que torna a credencial **da pessoa**. Enquanto o dono souber a
 * senha do operador, "quem fez" é sempre contestável e a trilha do caixa vira enfeite —
 * `docs/adr/0020-operador-supervisor-e-papeis.md`, decisão 6. */

vi.mock("../lib/api", () => ({ equipe: { trocarSenha: vi.fn() } }));

const { equipe } = await import("../lib/api");

async function preencher(atual: string, nova: string, repetida: string) {
  const usuario = userEvent.setup();
  const trocada = vi.fn();
  render(<TrocarSenhaPage onTrocada={trocada} />);

  if (atual) await usuario.type(screen.getByLabelText("Senha atual"), atual);
  if (nova) await usuario.type(screen.getByLabelText("Senha nova"), nova);
  if (repetida) await usuario.type(screen.getByLabelText("Repita a senha nova"), repetida);
  return { usuario, trocada };
}

describe("TrocarSenhaPage", () => {
  it("troca a senha e avisa quem chamou", async () => {
    vi.mocked(equipe.trocarSenha).mockResolvedValue(undefined);
    const { usuario, trocada } = await preencher(
      "senha-da-loja-123",
      "minha-senha-456",
      "minha-senha-456",
    );

    await usuario.click(screen.getByRole("button", { name: "Trocar a senha" }));

    await waitFor(() =>
      expect(equipe.trocarSenha).toHaveBeenCalledWith("senha-da-loja-123", "minha-senha-456"),
    );
    expect(trocada).toHaveBeenCalled();
  });

  it("não deixa trocar quando as duas não estão iguais", async () => {
    await preencher("senha-da-loja-123", "minha-senha-456", "minha-senha-789");

    expect(screen.getByText("As duas não estão iguais.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Trocar a senha" })).toHaveProperty(
      "disabled",
      true,
    );
  });

  it("não deixa trocar por uma senha curta demais", async () => {
    await preencher("senha-da-loja-123", "curta", "curta");

    expect(screen.getByRole("button", { name: "Trocar a senha" })).toHaveProperty(
      "disabled",
      true,
    );
  });

  it("exige a senha atual, para terminal aberto não virar tomada de conta", async () => {
    await preencher("", "minha-senha-456", "minha-senha-456");

    expect(screen.getByRole("button", { name: "Trocar a senha" })).toHaveProperty(
      "disabled",
      true,
    );
  });

  it("mostra o motivo quando o servidor recusa", async () => {
    vi.mocked(equipe.trocarSenha).mockRejectedValue(new Error("A senha atual não confere."));
    const { usuario } = await preencher("chute", "minha-senha-456", "minha-senha-456");

    await usuario.click(screen.getByRole("button", { name: "Trocar a senha" }));

    expect(await screen.findByText("A senha atual não confere.")).toBeTruthy();
  });
});
