import "fake-indexeddb/auto";

import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ApiError, SemRedeError } from "./api";
import type { Cliente } from "./clientes";
import type { Produto } from "./comercial";
import type { VendaDoAparelho } from "./balcao";

/* A venda composta no aparelho, sem rede.
 *
 * Fatia 4 da `docs/adr/0022-offline-first-as-respostas.md`. O que se afirma aqui é que a
 * operação **continua**: o item entra, o pagamento entra, a conta fecha e a venda espera
 * a rede sem se perder. E que ela espera **uma vez**: reenviar o mesmo pacote não pode
 * virar duas vendas, nem dois pagamentos.
 *
 * O servidor é substituído porque este é o lado do aparelho. Quem prova que a venda entra
 * certa do outro lado é `modules/pdv/tests/test_venda_do_aparelho.py`, contra PostgreSQL
 * de verdade.
 */

vi.mock("./pdv", async (original) => ({
  ...(await original<typeof import("./pdv")>()),
  pdv: { sincronizarVenda: vi.fn() },
}));

const { pdv } = await import("./pdv");
const balcao = await import("./balcao");
const { enviarPendentes } = await import("./sincronia");
const { pendentes } = await import("./fila");
const local = await import("./local");

const EMPRESA = "loja-do-balcao";

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

function umCliente(): Cliente {
  return {
    id: "cliente-1",
    tipo: "fisica",
    nome: "Maria da Silva",
    apelido: null,
    tenant_assinante_id: null,
    cpf_cnpj: "12345678909",
    inscricao_estadual: null,
    email: null,
    telefone: null,
    cep: null,
    logradouro: null,
    numero: null,
    complemento: null,
    bairro: null,
    cidade: null,
    uf: null,
    observacao: null,
    ativo: true,
  };
}

const CONFIG = {
  exige_cancelar_item: false,
  exige_cancelar_venda: false,
  exige_sangria: false,
  exige_devolucao: false,
  exige_desconto: false,
  desconto_livre: "0.00",
  exige_diferenca: false,
  diferenca_livre: "0.00",
  exige_pin_no_pdv: false,
};

/** Uma venda pronta para fechar: um item de R$ 19,90 e o dinheiro na mão. */
function vendaPaga() {
  let venda = balcao.lancar(balcao.vendaNova(), umProduto(), "1");
  venda = balcao.pagar(venda, { forma: "dinheiro", valor: "19.90" });
  return venda;
}

beforeEach(async () => {
  vi.clearAllMocks();
  local.fechar();
  await local.esvaziar(EMPRESA, "fila");
  await local.esvaziar(EMPRESA, "avisos");
  await local.esvaziar(EMPRESA, "configuracao");
});

afterEach(() => local.fechar());

// ----------------------------------------------------------------- compondo a venda

it("o item entra com o preço do catálogo do aparelho", () => {
  const venda = balcao.lancar(balcao.vendaNova(), umProduto(), "2");

  expect(venda.itens).toHaveLength(1);
  expect(venda.itens[0].descricao).toBe("Café torrado 500g");
  expect(venda.itens[0].total).toBe("39.80");
  expect(venda.soma_dos_itens).toBe("39.80");
  expect(venda.total).toBe("39.80");
  // Falta receber tudo: ninguém pagou nada ainda.
  expect(venda.falta).toBe("39.80");
});

it("a identidade da venda nasce no aparelho, e o número não", () => {
  const venda = balcao.vendaNova();

  expect(venda.id).toMatch(/^[0-9a-f-]{36}$/);
  /* O número é do servidor: dois caixas sem rede não têm como combinar um contador, e é
   * o número que o cliente vê no cupom. */
  expect(venda.numero).toBeNull();
});

it("produto sem preço é recusado em vez de ir a zero", () => {
  // Vender de graça por omissão é o defeito que só aparece no fechamento do caixa.
  expect(() => balcao.lancar(balcao.vendaNova(), umProduto({ preco_venda: null }), "1")).toThrow(
    balcao.BalcaoError,
  );
});

it("produto que controla lote não é vendido sem lote", () => {
  /* Sem rede não há saldo por lote para escolher. Deixar passar aqui adiaria a recusa
   * para a sincronização — com a mercadoria já na sacola do cliente. */
  expect(() => balcao.lancar(balcao.vendaNova(), umProduto({ controla_lote: true }), "1")).toThrow(
    /lote/,
  );
});

it("o pagamento entra e o troco é contado no aparelho", () => {
  let venda = balcao.lancar(balcao.vendaNova(), umProduto(), "1");
  venda = balcao.pagar(venda, { forma: "dinheiro", valor: "20.00" });

  expect(venda.pago).toBe("20.00");
  expect(venda.falta).toBe("0.00");
  expect(venda.troco).toBe("0.10");
});

it("retirar o item desfaz a conta inteira", () => {
  let venda = balcao.lancar(balcao.vendaNova(), umProduto(), "1");
  venda = balcao.lancar(venda, umProduto({ id: "produto-2", nome: "Açúcar" }), "1");
  venda = balcao.retirar(venda, venda.itens[0].id);

  expect(venda.itens).toHaveLength(1);
  expect(venda.itens[0].descricao).toBe("Açúcar");
  expect(venda.total).toBe("19.90");
});

it("o desconto não pode passar da venda", () => {
  const venda = balcao.lancar(balcao.vendaNova(), umProduto(), "1");

  expect(() => balcao.definirDesconto(venda, "25.00")).toThrow(/maior que a venda/);
  expect(balcao.definirDesconto(venda, "0.90").total).toBe("19.00");
});

it("retirar item derruba o desconto que ficou maior que a venda", () => {
  /* Senão a venda trava: o desconto antigo passa a ser maior que o que sobrou, e aí não
   * fecha nem dá para consertar sem cancelar tudo. */
  let venda = balcao.lancar(balcao.vendaNova(), umProduto(), "1");
  venda = balcao.lancar(venda, umProduto({ id: "produto-2", nome: "Açúcar" }), "1");
  venda = balcao.definirDesconto(venda, "25.00");
  venda = balcao.retirar(venda, venda.itens[1].id);

  expect(venda.desconto).toBe("0.00");
  expect(venda.total).toBe("19.90");
});

it("identificar a venda usa o cadastro que o aparelho tem", () => {
  const venda = balcao.identificar(balcao.vendaNova(), umCliente());

  expect(venda.cliente_id).toBe("cliente-1");
  expect(venda.cliente_nome).toBe("Maria da Silva");
  expect(balcao.desidentificar(venda).cliente_id).toBeNull();
});

// ----------------------------------------------------------------- fechando a venda

it("não fecha com dinheiro faltando", () => {
  // A mesma recusa do servidor, dada enquanto o cliente ainda está na frente do caixa.
  const venda = balcao.lancar(balcao.vendaNova(), umProduto(), "1");

  expect(() => balcao.fechar(venda)).toThrow(/Falta receber/);
});

it("não fecha vazia", () => {
  expect(() => balcao.fechar(balcao.vendaNova())).toThrow(/sem itens/);
});

it("só dinheiro devolve troco", () => {
  /* Cobrar no cartão mais do que a venda e devolver a diferença em espécie transforma o
   * caixa em saque. É a regra do servidor, e ela vale aqui para a venda não ser recusada
   * depois de o cliente ir embora. */
  let venda = balcao.lancar(balcao.vendaNova(), umProduto(), "1");
  venda = balcao.pagar(venda, { forma: "debito", valor: "25.00" });

  expect(() => balcao.fechar(venda)).toThrow(/dinheiro devolve troco/);
});

it("a venda fechada guarda a hora do aparelho", () => {
  const fechada = balcao.fechar(vendaPaga());

  expect(fechada.status).toBe("finalizada");
  expect(fechada.fechada_em).not.toBeNull();
  // A hora do servidor é outra, e a trilha precisa das duas — ADR 0019.
  expect(balcao.corpoDaVenda(fechada).registrada_no_aparelho_em).toBe(fechada.fechada_em);
});

// ----------------------------------------------------------------- a fila

it("a venda fechada fica na fila até o servidor aceitar", async () => {
  const fechada = balcao.fechar(vendaPaga());
  await balcao.enfileirarVenda(EMPRESA, fechada);

  const fila = await balcao.vendasNaFila(EMPRESA);
  expect(fila).toHaveLength(1);
  expect(fila[0].id).toBe(fechada.id);
  expect(fila[0].acao).toBe("venda.sincronizar");
});

it("sobe o pacote inteiro e sai da fila", async () => {
  const fechada = balcao.fechar(vendaPaga());
  await balcao.enfileirarVenda(EMPRESA, fechada);
  vi.mocked(pdv.sincronizarVenda).mockResolvedValue({
    venda: { ...fechada, numero: 41 },
    ja_existia: false,
    divergencias: [],
  });

  const resultado = await enviarPendentes(EMPRESA);

  expect(resultado.enviados).toBe(1);
  expect(await balcao.vendasNaFila(EMPRESA)).toEqual([]);
  const corpo = vi.mocked(pdv.sincronizarVenda).mock.calls[0][0] as VendaDoAparelho;
  expect(corpo.id).toBe(fechada.id);
  expect(corpo.itens[0].preco_unitario).toBe("19.9000");
  expect(corpo.pagamentos[0].valor).toBe("19.90");
});

it("reenfileirar a mesma venda não vira duas na fila", async () => {
  /* O aparelho não tem como saber a diferença entre "não chegou" e "não voltou". A chave
   * da fila é o id da venda, então o segundo enfileiramento substitui o primeiro. */
  const fechada = balcao.fechar(vendaPaga());
  await balcao.enfileirarVenda(EMPRESA, fechada);
  await balcao.enfileirarVenda(EMPRESA, fechada);

  expect(await balcao.vendasNaFila(EMPRESA)).toHaveLength(1);
});

it("sem rede a venda fica na fila, e nada é perdido", async () => {
  await balcao.enfileirarVenda(EMPRESA, balcao.fechar(vendaPaga()));
  vi.mocked(pdv.sincronizarVenda).mockRejectedValue(new SemRedeError());

  const resultado = await enviarPendentes(EMPRESA);

  expect(resultado.semRede).toBe(true);
  expect(await balcao.vendasNaFila(EMPRESA)).toHaveLength(1);
});

it("venda recusada pelo servidor fica na fila com o motivo", async () => {
  /* É o caso da venda cancelada no sistema enquanto o aparelho estava fora. Tentar de
   * novo não resolveria, e apagar esconderia de quem vendeu que a venda não entrou. */
  await balcao.enfileirarVenda(EMPRESA, balcao.fechar(vendaPaga()));
  vi.mocked(pdv.sincronizarVenda).mockRejectedValue(
    new ApiError("Esta venda foi cancelada no sistema.", 422),
  );

  const resultado = await enviarPendentes(EMPRESA);

  expect(resultado.recusados).toBe(1);
  const fila = await balcao.vendasNaFila(EMPRESA);
  expect(fila[0].erro).toContain("cancelada");
});

it("a fila sobe cadastro e venda juntos, na ordem em que aconteceram", async () => {
  /* Uma venda identificada aponta para um cliente que pode ter sido cadastrado sem rede
   * minutos antes. Mandar a venda primeiro faria o servidor recusá-la por apontar para
   * alguém que ainda não existe lá. */
  const { enfileirar } = await import("./fila");
  /* O id começa com "z" de propósito: o armazenamento devolve por ordem de chave, e um
   * id que cairia **depois** do da venda é o que prova que a ordem vem do momento em que
   * cada um entrou, e não de sorteio. Os dois entram no mesmo milissegundo. */
  await enfileirar(EMPRESA, { id: "zz-cliente", acao: "cliente.criar", corpo: {} });
  await balcao.enfileirarVenda(EMPRESA, balcao.fechar(vendaPaga()));

  const fila = await pendentes(EMPRESA);
  expect(fila.map((item) => item.acao)).toEqual(["cliente.criar", "venda.sincronizar"]);
});

// ----------------------------------------------------------------- a divergência

it("a divergência do estoque fica guardada para alguém ver", async () => {
  /* "A divergência é o produto, não o defeito": a venda entra, o saldo fica negativo, e
   * quem está no balcão precisa saber hoje que vendeu o que não tinha. */
  const fechada = balcao.fechar(vendaPaga());
  await balcao.enfileirarVenda(EMPRESA, fechada);
  vi.mocked(pdv.sincronizarVenda).mockResolvedValue({
    venda: { ...fechada, numero: 42 },
    ja_existia: false,
    divergencias: [
      {
        produto_id: "produto-1",
        descricao: "Café torrado 500g",
        vendido: "1.000000",
        saldo_depois: "-2.000000",
      },
    ],
  });

  await enviarPendentes(EMPRESA);

  const avisos = await balcao.avisos(EMPRESA);
  expect(avisos).toHaveLength(1);
  expect(avisos[0].numero).toBe(42);
  expect(avisos[0].divergencias[0].saldo_depois).toBe("-2.000000");

  await balcao.esquecerAviso(EMPRESA, avisos[0].id);
  expect(await balcao.avisos(EMPRESA)).toEqual([]);
});

it("venda que bate o estoque não deixa aviso nenhum", async () => {
  const fechada = balcao.fechar(vendaPaga());
  await balcao.enfileirarVenda(EMPRESA, fechada);
  vi.mocked(pdv.sincronizarVenda).mockResolvedValue({
    venda: { ...fechada, numero: 43 },
    ja_existia: false,
    divergencias: [],
  });

  await enviarPendentes(EMPRESA);

  expect(await balcao.avisos(EMPRESA)).toEqual([]);
});

// ----------------------------------------------------------------- a liberação que falta

it("sem configuração guardada, nada que dependa de supervisor passa", () => {
  /* O aparelho nunca soube a regra desta loja. Supor "pode" seria inventar permissão —
   * e a liberação é conferida no servidor, nunca aqui. */
  expect(balcao.podeSemLiberacao(null, "cancelar_item")).toBe(false);
  expect(balcao.podeSemLiberacao(null, "desconto", "1.00")).toBe(false);
});

it("o que a loja não exige supervisor para fazer continua valendo sem rede", () => {
  expect(balcao.podeSemLiberacao(CONFIG, "cancelar_item")).toBe(true);
  expect(balcao.podeSemLiberacao({ ...CONFIG, exige_cancelar_item: true }, "cancelar_item")).toBe(
    false,
  );
});

it("o desconto livre da loja vale sem rede, e o acima dele não", () => {
  const loja = { ...CONFIG, exige_desconto: true, desconto_livre: "5.00" };

  expect(balcao.podeSemLiberacao(loja, "desconto", "5.00")).toBe(true);
  expect(balcao.podeSemLiberacao(loja, "desconto", "5.01")).toBe(false);
});

it("a configuração guardada é por empresa", async () => {
  /* Duas empresas no mesmo balcão não podem herdar a regra uma da outra: o isolamento no
   * servidor é do PostgreSQL, e aqui é o nome do banco do aparelho. */
  await balcao.guardarConfiguracao(EMPRESA, { ...CONFIG, exige_cancelar_item: true });

  expect(await balcao.configuracaoGuardada(EMPRESA)).toMatchObject({
    exige_cancelar_item: true,
  });
  expect(await balcao.configuracaoGuardada("outra-loja")).toBeNull();
});

// ------------------------------------------------- o aparelho que já usava a versão antiga

it("o aparelho que já tinha a versão antiga ganha os armazéns novos", async () => {
  /* `onupgradeneeded` só roda quando a versão do banco muda. O armazém novo não existe no
   * aparelho de quem já usou o Decko antes desta fatia — e ler um armazém que não existe
   * não devolve vazio, estoura. Quem está no balcão perderia a tela por causa disso. */
  const EMPRESA_ANTIGA = "loja-que-ja-usava";
  local.fechar();
  await new Promise<void>((resolve, reject) => {
    const pedido = indexedDB.open(`decko:${EMPRESA_ANTIGA}`, 2);
    pedido.onupgradeneeded = () => {
      for (const armazem of ["fila", "clientes", "produtos"]) {
        pedido.result.createObjectStore(armazem, { keyPath: "id" });
      }
    };
    pedido.onsuccess = () => {
      pedido.result.close();
      resolve();
    };
    pedido.onerror = () => reject(pedido.error);
  });

  await balcao.guardarConfiguracao(EMPRESA_ANTIGA, CONFIG);

  expect(await balcao.configuracaoGuardada(EMPRESA_ANTIGA)).toMatchObject(CONFIG);
  expect(await balcao.avisos(EMPRESA_ANTIGA)).toEqual([]);
});
