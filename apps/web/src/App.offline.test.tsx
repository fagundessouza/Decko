import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

/* Abrir sem rede não pode cair na tela de entrada.
 *
 * O service worker fez o Decko abrir sem internet — e abrir no formulário de senha é pior
 * do que a tela de erro do navegador: a pessoa digita a senha certa, nada acontece, e a
 * conclusão razoável é que o sistema quebrou. Pior ainda no campo, onde não há como
 * conseguir rede para responder ao formulário. */

vi.mock("./lib/api", async (original) => ({
  ...(await original<typeof import("./lib/api")>()),
  restoreSession: vi.fn(),
  renewSession: vi.fn(),
  logout: vi.fn(),
}));

const { restoreSession, SemRedeError } = await import("./lib/api");
const { default: App } = await import("./App");

beforeEach(() => {
  vi.clearAllMocks();
});

it("sem rede, mostra 'Sem conexão' em vez do formulário de entrada", async () => {
  vi.mocked(restoreSession).mockRejectedValue(new SemRedeError());

  render(<App />);

  expect(await screen.findByText("Sem conexão")).toBeTruthy();
  expect(screen.queryByLabelText(/Código da empresa/)).toBeNull();
});

it("'Tentar de novo' pergunta ao servidor outra vez", async () => {
  vi.mocked(restoreSession).mockRejectedValue(new SemRedeError());
  render(<App />);
  await screen.findByText("Sem conexão");
  expect(restoreSession).toHaveBeenCalledTimes(1);

  // A rede voltou, e agora a sessão restaura.
  vi.mocked(restoreSession).mockResolvedValue(null);
  await userEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));

  expect(restoreSession).toHaveBeenCalledTimes(2);
  // Sem sessão e com rede, aí sim é a tela de entrada.
  expect(await screen.findByLabelText(/Código da empresa/)).toBeTruthy();
});

it("sessão que o servidor recusou leva para a entrada, e não para 'Sem conexão'", async () => {
  vi.mocked(restoreSession).mockResolvedValue(null);

  render(<App />);

  expect(await screen.findByLabelText(/Código da empresa/)).toBeTruthy();
  expect(screen.queryByText("Sem conexão")).toBeNull();
});

it("erro que não é de rede não vira 'Sem conexão'", async () => {
  /* Dizer "sem conexão" para um defeito manda a pessoa conferir o roteador por causa de
   * um problema que está no sistema. A mensagem errada custa a tarde de alguém. */
  vi.mocked(restoreSession).mockRejectedValue(new Error("qualquer outra coisa"));

  render(<App />);

  expect(await screen.findByLabelText(/Código da empresa/)).toBeTruthy();
  expect(screen.queryByText("Sem conexão")).toBeNull();
});
