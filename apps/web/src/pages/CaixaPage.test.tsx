import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Conferencia } from "../lib/pdv";
import { CaixaPage } from "./CaixaPage";

/* A conferência de caixa.
 *
 * O que estes testes protegem não é a soma — ela vem do servidor e tem teste contra banco
 * real. É a **conferência cega**: a `docs/adr/0008-ponto-de-venda.md` decidiu que quem
 * conta não vê o esperado, porque contar vendo o número que deveria dar não é conferir, é
 * confirmar. Sem teste, isso se perde na primeira vez que alguém "melhorar" a tela
 * mostrando tudo de uma vez. */

vi.mock("../lib/pdv", async (importar) => {
  const real = await importar<typeof import("../lib/pdv")>();
  return { ...real, pdv: { conferencia: vi.fn() } };
});

const { pdv } = await import("../lib/pdv");

function umaConferencia(sobre: Partial<Conferencia> = {}): Conferencia {
  return {
    de: "2026-11-10T00:00:00-03:00",
    ate: "2026-11-10T23:59:59-03:00",
    vendas: 4,
    canceladas: 0,
    bruto: "40.00",
    descontos: "0.00",
    liquido: "40.00",
    recebido: "40.00",
    por_forma: [
      { forma: "dinheiro", quantidade: 2, valor: "20.00" },
      { forma: "pix", quantidade: 1, valor: "10.00" },
    ],
    por_conta: [{ conta_id: null, conta_nome: null, valor: "40.00" }],
    por_operador: [
      { operador_id: "u-1", operador_nome: "Maria Operadora", vendas: 4, valor: "40.00" },
    ],
    devolucoes: 0,
    devolvido: "0.00",
    devolvido_em_especie: "0.00",
    avarias: [],
    ...sobre,
  };
}

beforeEach(() => {
  vi.mocked(pdv.conferencia).mockResolvedValue(umaConferencia());
});

async function contar(valor: string) {
  const usuario = userEvent.setup();
  render(<CaixaPage onBack={() => {}} />);
  await usuario.type(screen.getByLabelText("Quanto há na gaveta"), valor);
  await usuario.click(screen.getByRole("button", { name: "Conferir" }));
  return usuario;
}

describe("CaixaPage", () => {
  it("não mostra o esperado antes de a contagem ser feita", () => {
    render(<CaixaPage onBack={() => {}} />);

    // Nada do resultado pode vazar para esta etapa: nem o esperado, nem os totais do dia,
    // nem a quebra por forma de pagamento — qualquer um deles entrega a resposta.
    expect(screen.queryByText("Esperado pelo sistema")).toBeNull();
    expect(screen.queryByText(/R\$.20,00/)).toBeNull();
    expect(screen.queryByText("Por forma de pagamento")).toBeNull();
    expect(pdv.conferencia).not.toHaveBeenCalled();
  });

  it("nem sequer pergunta ao servidor antes de contar", async () => {
    const usuario = userEvent.setup();
    render(<CaixaPage onBack={() => {}} />);

    await usuario.type(screen.getByLabelText("Quanto há na gaveta"), "18,00");

    // A busca só acontece no clique. Buscar ao abrir deixaria o valor na resposta da rede,
    // ao alcance de quem abrir o inspetor antes de contar.
    expect(pdv.conferencia).not.toHaveBeenCalled();
  });

  it("diz o quanto falta quando a gaveta tem menos", async () => {
    await contar("18,00");

    expect(await screen.findByText("Esperado pelo sistema")).toBeTruthy();
    expect(screen.getByText(/falta de/)).toBeTruthy();
    expect(screen.getByText(/R\$.2,00/)).toBeTruthy();
  });

  it("diz que sobrou quando a gaveta tem mais", async () => {
    await contar("25,00");

    expect(await screen.findByText(/sobra de/)).toBeTruthy();
    expect(screen.getByText(/R\$.5,00/)).toBeTruthy();
  });

  it("diz que bateu quando o valor confere", async () => {
    await contar("20,00");

    // "Bateu certo" em vez de "diferença de R$ 0,00": zero não é informação, é ruído.
    expect(await screen.findByText("Bateu certo.")).toBeTruthy();
    expect(screen.queryByText(/falta de|sobra de/)).toBeNull();
  });

  it("conta só o dinheiro, e não o que entrou por cartão ou pix", async () => {
    // A gaveta tem os R$ 20,00 em espécie; os outros R$ 20,00 entraram por débito e pix.
    await contar("20,00");

    expect(await screen.findByText("Bateu certo.")).toBeTruthy();
    // O recebido do dia continua aparecendo, para leitura — o que não pode é entrar na
    // conta da gaveta.
    expect(screen.getByText("Recebido")).toBeTruthy();
  });

  it("manda o dia inteiro, em instantes com fuso", async () => {
    await contar("20,00");

    await waitFor(() => expect(pdv.conferencia).toHaveBeenCalled());
    const [de, ate] = vi.mocked(pdv.conferencia).mock.calls[0];
    // Meia-noite e o fim do dia, no fuso de quem está olhando: o servidor não adivinha
    // qual é o dia local de quem está no balcão.
    expect(de.getHours()).toBe(0);
    expect(de.getMinutes()).toBe(0);
    expect(ate.getHours()).toBe(23);
    expect(ate.getTime()).toBeGreaterThan(de.getTime());
  });

  it("desconta da gaveta o que foi devolvido em espécie", async () => {
    // Vinte em espécie entraram, cinco voltaram ao cliente: a gaveta tem de ter quinze.
    // Sem este desconto a conferência acusaria falta todo dia em que a loja devolve algo —
    // e um número que nunca bate deixa de ser conferido na segunda semana.
    vi.mocked(pdv.conferencia).mockResolvedValue(
      umaConferencia({ devolucoes: 1, devolvido: "5.00", devolvido_em_especie: "5.00" }),
    );
    await contar("15,00");

    expect(await screen.findByText("Bateu certo.")).toBeTruthy();
    expect(screen.getByText("Devolvido em espécie")).toBeTruthy();
  });

  it("devolução no cartão não mexe na conta da gaveta", async () => {
    // O cliente recebeu pela adquirente, não pela gaveta: os vinte em espécie continuam lá.
    vi.mocked(pdv.conferencia).mockResolvedValue(
      umaConferencia({ devolucoes: 1, devolvido: "5.00", devolvido_em_especie: "0.00" }),
    );
    await contar("20,00");

    expect(await screen.findByText("Bateu certo.")).toBeTruthy();
    expect(screen.getByText(/Devoluções \(1\)/)).toBeTruthy();
  });

  it("lista as avarias à parte, porque elas não são estoque", async () => {
    vi.mocked(pdv.conferencia).mockResolvedValue(
      umaConferencia({
        avarias: [
          {
            produto_id: "p-1",
            descricao: "Refrigerante 2L",
            unidade_id: "un-1",
            unidade_simbolo: "UN",
            quantidade: "2.000000",
          },
        ],
      }),
    );
    await contar("20,00");

    // Contar avaria como estoque faria o sistema dizer que dá para vender o que quebrou.
    expect(await screen.findByText("Avarias e trocas")).toBeTruthy();
    expect(screen.getByText("Refrigerante 2L")).toBeTruthy();
    expect(screen.getByText("2 UN")).toBeTruthy();
  });
});
