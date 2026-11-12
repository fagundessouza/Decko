import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../lib/api";
import { Button } from "./Button";
import { useAutorizacao } from "./Autorizacao";

/* A liberação do supervisor, no balcão.
 *
 * O que estes testes guardam é a `docs/adr/0020-operador-supervisor-e-papeis.md`,
 * decisão 4: **a tela não destrava nada**. Ela tenta a ação; se o servidor responder 428,
 * pede a credencial e repete a **mesma ação** com ela. Se alguém trocar isso por um botão
 * que se habilita depois de digitar uma senha, a trava inteira vira enfeite — quem abre
 * o inspetor passa por cima. */

vi.mock("../lib/pdv", async (importar) => {
  const real = await importar<typeof import("../lib/pdv")>();
  return { ...real, pdv: { autorizadores: vi.fn() } };
});

const { pdv } = await import("../lib/pdv");

/** Casca mínima: só exercita o gancho, como as telas o usam. */
function Balcao({ acao }: { acao: (credencial?: unknown) => Promise<unknown> }) {
  const autorizacao = useAutorizacao();
  return (
    <>
      <Button onClick={() => void autorizacao.executar(acao)}>Retirar item</Button>
      {autorizacao.dialogo}
    </>
  );
}

beforeEach(() => {
  vi.mocked(pdv.autorizadores).mockResolvedValue([
    { id: "sup-1", nome: "Joana Supervisora" },
  ]);
});

describe("useAutorizacao", () => {
  it("não pede nada quando a ação passa de primeira", async () => {
    const usuario = userEvent.setup();
    const acao = vi.fn().mockResolvedValue(undefined);
    render(<Balcao acao={acao} />);

    await usuario.click(screen.getByRole("button", { name: "Retirar item" }));

    // Sem argumento nenhum: a primeira tentativa não leva credencial.
    await waitFor(() => expect(acao).toHaveBeenCalledWith());
    expect(screen.queryByRole("dialog")).toBeNull();
    // Nem a lista é buscada: quem não precisa de supervisor não descobre quem são.
    expect(pdv.autorizadores).not.toHaveBeenCalled();
  });

  it("pede a credencial no 428 e repete a mesma ação com ela", async () => {
    const usuario = userEvent.setup();
    const acao = vi
      .fn()
      .mockRejectedValueOnce(new ApiError("Precisa de supervisor.", 428))
      .mockResolvedValueOnce(undefined);
    render(<Balcao acao={acao} />);

    await usuario.click(screen.getByRole("button", { name: "Retirar item" }));

    expect(await screen.findByRole("dialog")).toBeTruthy();
    await usuario.type(screen.getByLabelText("Senha de quem libera"), "senha-da-joana");
    await usuario.click(screen.getByRole("button", { name: "Liberar" }));

    // A credencial vai **junto com a ação**, na requisição que executa.
    await waitFor(() =>
      expect(acao).toHaveBeenLastCalledWith({
        autorizador_id: "sup-1",
        senha: "senha-da-joana",
      }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("senha errada mantém o diálogo aberto e diz o motivo", async () => {
    const usuario = userEvent.setup();
    const acao = vi
      .fn()
      .mockRejectedValueOnce(new ApiError("Precisa de supervisor.", 428))
      .mockRejectedValueOnce(new Error("A senha do supervisor não confere."));
    render(<Balcao acao={acao} />);

    await usuario.click(screen.getByRole("button", { name: "Retirar item" }));
    await usuario.type(
      await screen.findByLabelText("Senha de quem libera"),
      "chute",
    );
    await usuario.click(screen.getByRole("button", { name: "Liberar" }));

    // Senha errada no balcão é para digitar de novo, não para recomeçar a operação.
    expect(await screen.findByText("A senha do supervisor não confere.")).toBeTruthy();
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("erro que não é falta de liberação sobe para quem chamou", async () => {
    const usuario = userEvent.setup();
    const acao = vi.fn().mockRejectedValue(new ApiError("Venda já fechada.", 422));
    const aoFalhar = vi.fn();

    function Casca() {
      const autorizacao = useAutorizacao();
      return (
        <>
          <Button onClick={() => void autorizacao.executar(acao).catch(aoFalhar)}>
            Retirar item
          </Button>
          {autorizacao.dialogo}
        </>
      );
    }
    render(<Casca />);

    await usuario.click(screen.getByRole("button", { name: "Retirar item" }));

    // 422 é erro da ação, e quem chamou é que sabe mostrá-lo. Abrir o diálogo aqui faria
    // o operador procurar um supervisor para um problema que supervisor nenhum resolve.
    await waitFor(() => expect(aoFalhar).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
