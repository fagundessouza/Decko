import "fake-indexeddb/auto";

import { beforeEach, afterEach, expect, it, vi } from "vitest";

import { SemRedeError } from "./api";

/* O catálogo guardado no aparelho.
 *
 * Fatia 3 da `docs/adr/0022-offline-first-as-respostas.md`. Sem rede, o balcão ainda
 * precisa achar o produto — pelo código de barras, que é como o leitor trabalha, ou pelo
 * nome, que é como se procura digitando.
 */

vi.mock("./comercial", async (original) => ({
  ...(await original<typeof import("./comercial")>()),
  comercial: { listProdutos: vi.fn() },
}));

vi.mock("./pdv", async (original) => ({
  ...(await original<typeof import("./pdv")>()),
  pdv: { catalogoDoAparelho: vi.fn() },
}));

const { comercial } = await import("./comercial");
const { pdv } = await import("./pdv");
const { atualizar, procurar } = await import("./catalogo");
const local = await import("./local");

const EMPRESA = "loja-do-catalogo";

function umProduto(sobre: Partial<Record<string, unknown>> = {}) {
  return {
    id: crypto.randomUUID(),
    codigo: "COD-1",
    nome: "Refrigerante 2L",
    descricao: null,
    gtin: "7891234567895",
    ncm: null,
    cest: null,
    categoria_id: null,
    unidade_id: "u-1",
    preco_custo: null,
    preco_venda: "9.90",
    controla_lote: false,
    controla_validade: false,
    estoque_minimo: null,
    ativo: true,
    ...sobre,
  } as never;
}

beforeEach(async () => {
  vi.clearAllMocks();
  local.fechar();
  await local.esvaziar(EMPRESA, "produtos");
});

afterEach(() => local.fechar());

it("com rede, procura no servidor e não toca no aparelho", async () => {
  vi.mocked(comercial.listProdutos).mockResolvedValue([umProduto()]);

  const achado = await procurar(EMPRESA, "refri");

  expect(achado.doAparelho).toBe(false);
  expect(comercial.listProdutos).toHaveBeenCalledWith("refri");
});

it("guarda o recorte que o servidor manda", async () => {
  vi.mocked(pdv.catalogoDoAparelho).mockResolvedValue([
    umProduto({ nome: "Pão" }),
    umProduto({ nome: "Leite" }),
  ]);

  expect(await atualizar(EMPRESA)).toBe(2);
  expect(await local.lerTodos(EMPRESA, "produtos")).toHaveLength(2);
});

it("sem rede, acha pelo código de barras inteiro", async () => {
  /* É o leitor passando o produto. Acerto parcial aqui lançaria o item errado no cupom,
   * que é o tipo de erro que só aparece na conferência do caixa. */
  vi.mocked(pdv.catalogoDoAparelho).mockResolvedValue([
    umProduto({ nome: "Refrigerante 2L", gtin: "7891234567895" }),
    umProduto({ nome: "Água 500ml", gtin: "7899999999999" }),
  ]);
  await atualizar(EMPRESA);
  vi.mocked(comercial.listProdutos).mockRejectedValue(new SemRedeError());

  const achado = await procurar(EMPRESA, "7891234567895");

  expect(achado.doAparelho).toBe(true);
  expect(achado.produtos.map((p) => p.nome)).toEqual(["Refrigerante 2L"]);
});

it("sem rede, acha por pedaço do nome", async () => {
  vi.mocked(pdv.catalogoDoAparelho).mockResolvedValue([
    umProduto({ nome: "Refrigerante 2L" }),
    umProduto({ nome: "Refrigerante lata" }),
    umProduto({ nome: "Pão de forma" }),
  ]);
  await atualizar(EMPRESA);
  vi.mocked(comercial.listProdutos).mockRejectedValue(new SemRedeError());

  const achado = await procurar(EMPRESA, "refrigerante");

  expect(achado.produtos.map((p) => p.nome)).toEqual([
    "Refrigerante 2L",
    "Refrigerante lata",
  ]);
});

it("código de barras parecido não vale: ou é o número, ou não é", async () => {
  vi.mocked(pdv.catalogoDoAparelho).mockResolvedValue([
    umProduto({ nome: "Refrigerante 2L", gtin: "7891234567895", codigo: "R2L" }),
  ]);
  await atualizar(EMPRESA);
  vi.mocked(comercial.listProdutos).mockRejectedValue(new SemRedeError());

  const achado = await procurar(EMPRESA, "789123456789");

  expect(achado.produtos).toHaveLength(0);
});

it("sem rede e sem nada guardado, devolve vazio em vez de quebrar", async () => {
  vi.mocked(comercial.listProdutos).mockRejectedValue(new SemRedeError());

  const achado = await procurar(EMPRESA, "qualquer");

  expect(achado.doAparelho).toBe(true);
  expect(achado.produtos).toHaveLength(0);
});

it("erro que não é de rede sobe, em vez de virar busca no aparelho", async () => {
  /* Dizer "sem conexão" para um defeito manda o operador conferir o roteador por causa
   * de um problema que está no sistema. */
  vi.mocked(comercial.listProdutos).mockRejectedValue(new Error("qualquer outra coisa"));

  await expect(procurar(EMPRESA, "refri")).rejects.toThrow("qualquer outra coisa");
});

it("armazenamento bloqueado não derruba a busca com rede", async () => {
  vi.spyOn(local, "gravarVarios").mockRejectedValue(new local.LocalIndisponivelError());
  vi.mocked(pdv.catalogoDoAparelho).mockResolvedValue([umProduto()]);

  expect(await atualizar(EMPRESA)).toBe(1);
});
