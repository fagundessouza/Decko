import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Produto } from "../lib/comercial";
import type { Venda } from "../lib/pdv";
import { PdvPage } from "./PdvPage";

/* A tela do balcão.
 *
 * É a tela que mais se repete no dia e a que menos perdoa: cada item é um código bipado
 * e um Enter, com fila esperando. O que se afirma aqui é o caminho do leitor de código
 * de barras e o foco, que é o que decide se o caixa anda ou para.
 *
 * Dinheiro não é testado aqui de propósito. Total, falta e troco chegam somados do
 * servidor — ADR 0008, decisão 3 — e a tela só desenha. Afirmar aritmética neste nível
 * seria afirmar sobre a fixture, não sobre o produto.
 *
 * O servidor é substituído porque este teste é de interação, não de integração: quem
 * prova o cálculo e o isolamento entre empresas é a suíte do backend, contra PostgreSQL
 * de verdade. As respostas abaixo são fixtures declaradas, nunca carregadas fora daqui. */

vi.mock("../lib/pdv", async (importar) => {
  // O módulo verdadeiro é carregado para FORMAS continuar valendo: a lista de formas de
  // pagamento é dado do produto, não detalhe do teste.
  const real = await importar<typeof import("../lib/pdv")>();
  return {
    ...real,
    pdv: {
      listVendas: vi.fn(),
      ver: vi.fn(),
      abrir: vi.fn(),
      adicionarItem: vi.fn(),
      removerItem: vi.fn(),
      definirDesconto: vi.fn(),
      pagar: vi.fn(),
      removerPagamento: vi.fn(),
      identificar: vi.fn(),
      desidentificar: vi.fn(),
      finalizar: vi.fn(),
      cancelar: vi.fn(),
    },
  };
});

vi.mock("../lib/comercial", () => ({
  comercial: { listProdutos: vi.fn() },
}));

vi.mock("../lib/clientes", () => ({
  clientes: { listar: vi.fn() },
}));

const { pdv } = await import("../lib/pdv");
const { comercial } = await import("../lib/comercial");

function umaVenda(sobre: Partial<Venda> = {}): Venda {
  return {
    id: "venda-1",
    numero: null,
    status: "aberta",
    aberta_em: "2026-11-03T10:00:00-03:00",
    fechada_em: null,
    observacao: null,
    cliente_id: null,
    cliente_nome: null,
    itens: [],
    pagamentos: [],
    soma_dos_itens: "0.00",
    desconto: "0.00",
    total: "0.00",
    pago: "0.00",
    falta: "0.00",
    troco: "0.00",
    ...sobre,
  };
}

function umProduto(sobre: Partial<Produto> = {}): Produto {
  return {
    id: "produto-1",
    codigo: "7891",
    nome: "Café torrado 500g",
    descricao: null,
    gtin: "7891000100103",
    ncm: null,
    cest: null,
    categoria_id: null,
    unidade_id: "unidade-1",
    preco_custo: null,
    preco_venda: "19.90",
    controla_lote: false,
    controla_validade: false,
    estoque_minimo: null,
    ativo: true,
    ...sobre,
  };
}

function abrirCaixa() {
  return render(<PdvPage onBack={() => {}} empresa="Mercado do Teste" podeIdentificar={false} />);
}

/** O campo que recebe o código de barras. */
function campoDeCodigo() {
  return screen.getByLabelText("Código, código de barras ou nome");
}

beforeEach(() => {
  vi.mocked(pdv.listVendas).mockResolvedValue([]);
  vi.mocked(pdv.abrir).mockResolvedValue(umaVenda());
  vi.mocked(pdv.ver).mockResolvedValue(umaVenda());
  vi.mocked(comercial.listProdutos).mockResolvedValue([]);
  vi.mocked(pdv.adicionarItem).mockResolvedValue(umaVenda());
});

describe("PdvPage, ao abrir", () => {
  it("retoma a venda já aberta em vez de começar outra", async () => {
    vi.mocked(pdv.listVendas).mockResolvedValue([
      { id: "venda-9", numero: null, status: "aberta", aberta_em: "", fechada_em: null, total: null },
    ]);

    abrirCaixa();
    await waitFor(() => expect(pdv.ver).toHaveBeenCalledWith("venda-9"));

    // Recarregar a página não pode perder o que já foi bipado: abrir outra venda
    // deixaria a primeira pendurada e o troco sairia errado.
    expect(pdv.abrir).not.toHaveBeenCalled();
  });

  it("abre uma venda quando não há nenhuma pendente", async () => {
    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());
    expect(pdv.ver).not.toHaveBeenCalled();
  });
});

describe("PdvPage, bipando um código", () => {
  it("lança sozinho quando o código acha um produto só", async () => {
    const usuario = userEvent.setup();
    vi.mocked(comercial.listProdutos).mockResolvedValue([umProduto()]);

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    // É o caminho do leitor de código de barras: ele digita e termina com Enter.
    await usuario.type(campoDeCodigo(), "7891000100103{Enter}");

    await waitFor(() =>
      expect(pdv.adicionarItem).toHaveBeenCalledWith("venda-1", {
        produto_id: "produto-1",
        quantidade: "1",
      }),
    );
  });

  it("deixa o operador escolher quando o termo acha vários", async () => {
    const usuario = userEvent.setup();
    vi.mocked(comercial.listProdutos).mockResolvedValue([
      umProduto({ id: "produto-1", nome: "Café torrado 500g" }),
      umProduto({ id: "produto-2", nome: "Café solúvel 200g" }),
    ]);

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());
    await usuario.type(campoDeCodigo(), "cafe{Enter}");

    expect(await screen.findByText("Café solúvel 200g")).toBeTruthy();
    // Lançar por conta própria aqui poria o produto errado na conta de alguém.
    expect(pdv.adicionarItem).not.toHaveBeenCalled();
  });

  it("não oferece produto inativo", async () => {
    const usuario = userEvent.setup();
    vi.mocked(comercial.listProdutos).mockResolvedValue([
      umProduto({ id: "produto-1", nome: "Café que saiu de linha", ativo: false }),
    ]);

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());
    await usuario.type(campoDeCodigo(), "cafe{Enter}");

    // Com o único resultado descartado, sobra zero: tem de virar aviso, e não um lance
    // silencioso de produto que a loja não vende mais.
    expect(await screen.findByText(/Nenhum produto/)).toBeTruthy();
    expect(pdv.adicionarItem).not.toHaveBeenCalled();
  });

  it("avisa quando o código não acha nada", async () => {
    const usuario = userEvent.setup();

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());
    await usuario.type(campoDeCodigo(), "0000{Enter}");

    expect(await screen.findByText(/Nenhum produto para/)).toBeTruthy();
    expect(pdv.adicionarItem).not.toHaveBeenCalled();
  });

  it("manda a quantidade com ponto, mesmo digitada com vírgula", async () => {
    const usuario = userEvent.setup();
    vi.mocked(comercial.listProdutos).mockResolvedValue([umProduto()]);

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    const quantidade = screen.getByLabelText("Qtd.");
    await usuario.clear(quantidade);
    // Quem está no caixa digita "1,5" — é assim que se escreve número no Brasil. Mandar
    // a vírgula para o servidor faria o decimal virar erro de validação no meio da fila.
    await usuario.type(quantidade, "1,5");
    await usuario.type(campoDeCodigo(), "7891{Enter}");

    await waitFor(() =>
      expect(pdv.adicionarItem).toHaveBeenCalledWith("venda-1", {
        produto_id: "produto-1",
        quantidade: "1.5",
      }),
    );
  });
});

describe("PdvPage, o foco", () => {
  it("volta para o código depois de lançar pelo botão", async () => {
    const usuario = userEvent.setup();
    vi.mocked(comercial.listProdutos).mockResolvedValue([umProduto()]);

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    /* O lance tem de partir do botão, e não de um Enter no próprio campo.
     *
     * Digitar no campo de código já deixa o foco nele, então um teste escrito assim
     * passa mesmo sem o `focarCodigo()` — foi o primeiro erro desta suíte. O caminho em
     * que o foco realmente se perde é o do mouse. */
    await usuario.type(campoDeCodigo(), "7891");
    const lancar = screen.getByRole("button", { name: "Lançar" });
    await usuario.click(lancar);
    expect(document.activeElement).toBe(lancar);

    await waitFor(() => expect(pdv.adicionarItem).toHaveBeenCalled());

    // Sem isto o operador pega no mouse a cada produto, que é o que torna um PDV lento.
    await waitFor(() => expect(document.activeElement).toBe(campoDeCodigo()));
  });
});
