import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Devolucao, DevolucoesDaVenda, VendaResumo } from "../lib/pdv";
import { DevolucaoPage } from "./DevolucaoPage";

/* A devolução de venda.
 *
 * Dois pontos aqui são regra, não interface, e é o que estes testes guardam:
 *
 * 1. **O valor vem do servidor antes de a gaveta abrir.** O operador pede a prévia, vê o
 *    número e só então confirma. Se alguém trocar isso por uma soma feita na tela, a
 *    ADR 0008, decisão 3, foi perdida — e quem paga a diferença é o caixa.
 * 2. **Defeito é dito por linha.** O que tem defeito não volta ao estoque vendável, e
 *    quem escolhe isso é quem está olhando o produto. */

vi.mock("../lib/pdv", async (importar) => {
  const real = await importar<typeof import("../lib/pdv")>();
  return {
    ...real,
    pdv: {
      porNumero: vi.fn(),
      devolucoesDaVenda: vi.fn(),
      preverDevolucao: vi.fn(),
      devolver: vi.fn(),
    },
  };
});

const { pdv } = await import("../lib/pdv");

/** Comparador que normaliza o espaço fino do `R$` — ele não é um espaço comum. */
function dinheiro(valor: string) {
  return (conteudo: string) => conteudo.replace(/\s/g, " ").trim() === valor;
}

function umResumo(sobre: Partial<VendaResumo> = {}): VendaResumo {
  return {
    id: "venda-1",
    numero: 7,
    status: "finalizada",
    aberta_em: "2026-11-10T09:00:00-03:00",
    fechada_em: "2026-11-10T09:05:00-03:00",
    total: "30.00",
    ...sobre,
  };
}

function umaVenda(sobre: Partial<DevolucoesDaVenda> = {}): DevolucoesDaVenda {
  return {
    venda_id: "venda-1",
    numero: 7,
    fechada_em: "2026-11-10T09:05:00-03:00",
    total: "30.00",
    linhas: [
      {
        venda_item_id: "linha-1",
        descricao: "Refrigerante 2L",
        unidade_id: "un-1",
        quantidade: "3.000000",
        devolvida: "0.000000",
        resta: "3.000000",
        valor_resta: "30.00",
      },
    ],
    devolucoes: [],
    devolvido: "0.00",
    ...sobre,
  };
}

function umaDevolucao(sobre: Partial<Devolucao> = {}): Devolucao {
  return {
    id: "dev-1",
    venda_id: "venda-1",
    operador_id: "u-1",
    caixa_id: "caixa-1",
    forma: "dinheiro",
    motivo: "Cliente trouxe de volta",
    total: "10.00",
    created_at: "2026-11-10T10:00:00-03:00",
    itens: [
      {
        id: "di-1",
        venda_item_id: "linha-1",
        quantidade: "1.000000",
        valor: "10.00",
        destino: "estoque",
      },
    ],
    ...sobre,
  };
}

beforeEach(() => {
  vi.mocked(pdv.porNumero).mockResolvedValue([umResumo()]);
  vi.mocked(pdv.devolucoesDaVenda).mockResolvedValue(umaVenda());
});

async function achar(numero = "7") {
  const usuario = userEvent.setup();
  render(<DevolucaoPage onBack={() => {}} />);
  await usuario.type(screen.getByLabelText("Número do cupom"), numero);
  await usuario.click(screen.getByRole("button", { name: "Buscar venda" }));
  return usuario;
}

describe("DevolucaoPage", () => {
  it("acha a venda pelo número do cupom e diz o que resta de cada linha", async () => {
    await achar();

    expect(await screen.findByText("Venda 7")).toBeTruthy();
    // O que resta e até quanto sai vêm do servidor, por linha.
    expect(screen.getByText(/Resta devolver 3, até/)).toBeTruthy();
  });

  it("explica quando a venda não está finalizada, em vez de só não achar", async () => {
    vi.mocked(pdv.porNumero).mockResolvedValue([umResumo({ status: "aberta" })]);
    await achar();

    expect(await screen.findByText(/não está finalizada/)).toBeTruthy();
    expect(pdv.devolucoesDaVenda).not.toHaveBeenCalled();
  });

  it("'Devolver tudo' preenche com o que resta, não com o que foi vendido", async () => {
    // Três vendidas, uma já voltou: "tudo" são as duas que restam. Preencher três faria o
    // servidor recusar a devolução inteira, e o operador não saberia por quê.
    vi.mocked(pdv.devolucoesDaVenda).mockResolvedValue(
      umaVenda({
        linhas: [
          {
            venda_item_id: "linha-1",
            descricao: "Refrigerante 2L",
            unidade_id: "un-1",
            quantidade: "3.000000",
            devolvida: "1.000000",
            resta: "2.000000",
            valor_resta: "20.00",
          },
        ],
        devolvido: "10.00",
      }),
    );
    const usuario = await achar();
    await usuario.click(await screen.findByRole("button", { name: "Devolver tudo" }));

    const campo = screen.getByLabelText<HTMLInputElement>("Refrigerante 2L — quantas voltam");
    expect(campo.value).toBe("2");
  });

  it("não deixa pedir a prévia sem escolher nenhuma linha", async () => {
    const usuario = await achar();
    await usuario.type(await screen.findByLabelText("Motivo"), "Nada escolhido ainda");

    // Motivo preenchido não basta: sem quantidade não há devolução, e o botão não pode
    // mandar uma lista vazia para o servidor recusar.
    expect(screen.getByRole("button", { name: "Ver quanto devolve" })).toHaveProperty(
      "disabled",
      true,
    );
  });

  it("não deixa pedir a prévia sem motivo", async () => {
    const usuario = await achar();
    await usuario.type(
      await screen.findByLabelText("Refrigerante 2L — quantas voltam"),
      "1",
    );

    // Devolução que ninguém explica depois é justamente a que importa explicar.
    expect(screen.getByRole("button", { name: "Ver quanto devolve" })).toHaveProperty(
      "disabled",
      true,
    );
  });

  it("mostra o valor que o servidor calculou antes de devolver, e só então devolve", async () => {
    vi.mocked(pdv.preverDevolucao).mockResolvedValue({ total: "10.00", valores: ["10.00"] });
    vi.mocked(pdv.devolver).mockResolvedValue(umaDevolucao());

    const usuario = await achar();
    await usuario.type(
      await screen.findByLabelText("Refrigerante 2L — quantas voltam"),
      "1",
    );
    await usuario.type(screen.getByLabelText("Motivo"), "Cliente trouxe de volta");
    await usuario.click(screen.getByRole("button", { name: "Ver quanto devolve" }));

    // O número aparece, e nada foi gravado ainda: ver não é devolver.
    expect(await screen.findByText(dinheiro("R$ 10,00"))).toBeTruthy();
    expect(pdv.devolver).not.toHaveBeenCalled();

    await usuario.click(screen.getByRole("button", { name: "Confirmar devolução" }));

    await waitFor(() =>
      expect(pdv.devolver).toHaveBeenCalledWith(
        "venda-1",
        {
          itens: [{ venda_item_id: "linha-1", quantidade: "1", destino: "estoque" }],
          forma: "dinheiro",
          motivo: "Cliente trouxe de volta",
        },
        // Terceiro argumento: a credencial do supervisor, vazia quando o servidor não
        // pediu liberação — ver ADR 0020, decisão 4.
        undefined,
      ),
    );
    expect(await screen.findByText("Devolução registrada")).toBeTruthy();
  });

  it("manda o destino avaria quando o operador diz que tem defeito", async () => {
    vi.mocked(pdv.preverDevolucao).mockResolvedValue({ total: "10.00", valores: ["10.00"] });
    vi.mocked(pdv.devolver).mockResolvedValue(
      umaDevolucao({
        itens: [
          {
            id: "di-1",
            venda_item_id: "linha-1",
            quantidade: "1.000000",
            valor: "10.00",
            destino: "avaria",
          },
        ],
      }),
    );

    const usuario = await achar();
    await usuario.type(
      await screen.findByLabelText("Refrigerante 2L — quantas voltam"),
      "1",
    );
    await usuario.selectOptions(
      screen.getByLabelText("Refrigerante 2L — o que fazer"),
      "avaria",
    );
    await usuario.type(screen.getByLabelText("Motivo"), "Garrafa trincada");
    await usuario.click(screen.getByRole("button", { name: "Ver quanto devolve" }));
    await usuario.click(await screen.findByRole("button", { name: "Confirmar devolução" }));

    await waitFor(() =>
      expect(pdv.devolver).toHaveBeenCalledWith(
        "venda-1",
        {
          itens: [{ venda_item_id: "linha-1", quantidade: "1", destino: "avaria" }],
          forma: "dinheiro",
          motivo: "Garrafa trincada",
        },
        undefined,
      ),
    );
    // E a tela diz que aquilo não voltou ao estoque, em vez de deixar o operador supor.
    expect(await screen.findByText(/não voltou ao estoque/)).toBeTruthy();
  });

  it("vírgula digitada vai como ponto para o servidor", async () => {
    vi.mocked(pdv.preverDevolucao).mockResolvedValue({ total: "15.00", valores: ["15.00"] });
    const usuario = await achar();

    await usuario.type(
      await screen.findByLabelText("Refrigerante 2L — quantas voltam"),
      "1,5",
    );
    await usuario.type(screen.getByLabelText("Motivo"), "Metade de uma caixa");
    await usuario.click(screen.getByRole("button", { name: "Ver quanto devolve" }));

    await waitFor(() =>
      expect(pdv.preverDevolucao).toHaveBeenCalledWith("venda-1", [
        { venda_item_id: "linha-1", quantidade: "1.5", destino: "estoque" },
      ]),
    );
  });

  it("diz quando a devolução ficou fora de sessão de caixa", async () => {
    vi.mocked(pdv.preverDevolucao).mockResolvedValue({ total: "10.00", valores: ["10.00"] });
    vi.mocked(pdv.devolver).mockResolvedValue(umaDevolucao({ caixa_id: null }));

    const usuario = await achar();
    await usuario.type(
      await screen.findByLabelText("Refrigerante 2L — quantas voltam"),
      "1",
    );
    await usuario.type(screen.getByLabelText("Motivo"), "Sem caixa aberto");
    await usuario.click(screen.getByRole("button", { name: "Ver quanto devolve" }));
    await usuario.click(await screen.findByRole("button", { name: "Confirmar devolução" }));

    // Não é erro, e tem de estar visível: o fechamento de ninguém vai contar com ela.
    expect(await screen.findByText(/fora de sessão de caixa/)).toBeTruthy();
  });

  it("linha já devolvida por inteiro não aceita mais quantidade", async () => {
    vi.mocked(pdv.devolucoesDaVenda).mockResolvedValue(
      umaVenda({
        linhas: [
          {
            venda_item_id: "linha-1",
            descricao: "Refrigerante 2L",
            unidade_id: "un-1",
            quantidade: "3.000000",
            devolvida: "3.000000",
            resta: "0.000000",
            valor_resta: "0.00",
          },
        ],
      }),
    );
    await achar();

    expect(await screen.findByText(/já devolvido por inteiro/)).toBeTruthy();
    expect(screen.queryByLabelText("Refrigerante 2L — quantas voltam")).toBeNull();
  });
});
