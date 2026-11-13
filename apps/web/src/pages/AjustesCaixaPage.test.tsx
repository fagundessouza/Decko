import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ConfiguracaoPdv } from "../lib/pdv";
import { AjustesCaixaPage } from "./AjustesCaixaPage";

/* Os ajustes do caixa.
 *
 * O que estes testes guardam é a `docs/adr/0020-operador-supervisor-e-papeis.md`,
 * decisão 4: **cada loja liga o que quiser**, e as duas exigências que dependem de um
 * número não vêm com número inventado — o limite é da loja. Também guardam que quem não
 * administra vê o que está valendo e não mexe: esconder a regra de quem opera não a
 * protege, mas deixá-la editável sim a quebraria. */

vi.mock("../lib/pdv", async (importar) => {
  const real = await importar<typeof import("../lib/pdv")>();
  return { ...real, pdv: { configuracao: vi.fn(), salvarConfiguracao: vi.fn() } };
});

const { pdv } = await import("../lib/pdv");

function umaConfig(sobre: Partial<ConfiguracaoPdv> = {}): ConfiguracaoPdv {
  return {
    exige_cancelar_item: true,
    exige_cancelar_venda: true,
    exige_sangria: true,
    exige_devolucao: true,
    exige_desconto: false,
    desconto_livre: "0.00",
    exige_diferenca: false,
    diferenca_livre: "0.00",
    exige_pin_no_pdv: true,
    ...sobre,
  };
}

beforeEach(() => {
  vi.mocked(pdv.configuracao).mockResolvedValue(umaConfig());
});

describe("AjustesCaixaPage", () => {
  it("mostra o que a loja exige hoje", async () => {
    render(<AjustesCaixaPage podeEditar />);

    const sangria = await screen.findByLabelText<HTMLInputElement>("Sangria");
    expect(sangria.checked).toBe(true);
    // As que dependem de um número nascem desligadas: o limite é da loja, não meu.
    expect(
      screen.getByLabelText<HTMLInputElement>("Desconto acima de um limite").checked,
    ).toBe(false);
  });

  it("o limite só aparece quando a exigência está ligada", async () => {
    const usuario = userEvent.setup();
    render(<AjustesCaixaPage podeEditar />);

    // Esperar a tela carregar antes de afirmar ausência: afirmar logo depois do render
    // encontraria "Carregando…" e daria por ausente o que ainda não tinha chegado.
    await screen.findByLabelText("Sangria");
    expect(screen.queryByLabelText("Desconto livre até")).toBeNull();

    await usuario.click(screen.getByLabelText("Desconto acima de um limite"));

    expect(await screen.findByLabelText("Desconto livre até")).toBeTruthy();
  });

  it("salva o que foi mexido, com vírgula virando ponto", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.salvarConfiguracao).mockResolvedValue(
      umaConfig({ exige_diferenca: true, diferenca_livre: "5.00" }),
    );
    render(<AjustesCaixaPage podeEditar />);

    await usuario.click(await screen.findByLabelText("Sangria"));
    await usuario.click(screen.getByLabelText("Fechamento com diferença acima de um limite"));
    await usuario.type(await screen.findByLabelText("Diferença livre até"), "5,00");
    await usuario.click(screen.getByRole("button", { name: "Salvar ajustes" }));

    await waitFor(() =>
      expect(pdv.salvarConfiguracao).toHaveBeenCalledWith({
        exige_cancelar_item: true,
        exige_cancelar_venda: true,
        // Desmarcada agora: esta loja deixa o operador sangrar sozinho.
        exige_sangria: false,
        exige_devolucao: true,
        exige_desconto: false,
        // Campo vazio vira "0": nada a digitar quando a exigência está desligada.
        desconto_livre: "0",
        exige_diferenca: true,
        // O campo nasce vazio quando o limite é zero, então o que vai é o que foi
        // digitado — com a vírgula virando ponto, não grudada no valor do servidor.
        diferenca_livre: "5.00",
        exige_pin_no_pdv: true,
      }),
    );
    expect(await screen.findByText("Ajustes salvos.")).toBeTruthy();
  });

  it("quem não administra vê e não mexe", async () => {
    render(<AjustesCaixaPage podeEditar={false} />);

    const sangria = await screen.findByLabelText<HTMLInputElement>("Sangria");
    expect(sangria.checked).toBe(true);
    expect(sangria.disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Salvar ajustes" })).toBeNull();
  });

  it("o limite começa vazio quando é zero, e mostra vírgula quando tem valor", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.configuracao).mockResolvedValue(
      umaConfig({ exige_desconto: true, desconto_livre: "5.00" }),
    );
    render(<AjustesCaixaPage podeEditar />);

    // Vem do servidor como "5.00" e chega ao campo como "5,00": é assim que se escreve
    // dinheiro aqui, e é o que o resto do sistema faz.
    expect(
      (await screen.findByLabelText<HTMLInputElement>("Desconto livre até")).value,
    ).toBe("5,00");

    vi.mocked(pdv.salvarConfiguracao).mockResolvedValue(umaConfig());
    await usuario.click(screen.getByRole("button", { name: "Salvar ajustes" }));

    await waitFor(() =>
      expect(pdv.salvarConfiguracao).toHaveBeenCalledWith(
        expect.objectContaining({ desconto_livre: "5.00" }),
      ),
    );
  });

  it("vazio vira zero, que é 'qualquer valor pede supervisor'", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.salvarConfiguracao).mockResolvedValue(umaConfig());
    render(<AjustesCaixaPage podeEditar />);

    await usuario.click(await screen.findByLabelText("Desconto acima de um limite"));
    await usuario.click(screen.getByRole("button", { name: "Salvar ajustes" }));

    await waitFor(() =>
      expect(pdv.salvarConfiguracao).toHaveBeenCalledWith(
        expect.objectContaining({ exige_desconto: true, desconto_livre: "0" }),
      ),
    );
  });

  it("diz o motivo quando o servidor recusa", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.salvarConfiguracao).mockRejectedValue(new Error("Sem permissão."));
    render(<AjustesCaixaPage podeEditar />);

    await usuario.click(await screen.findByLabelText("Sangria"));
    await usuario.click(screen.getByRole("button", { name: "Salvar ajustes" }));

    expect(await screen.findByText("Sem permissão.")).toBeTruthy();
  });
});
