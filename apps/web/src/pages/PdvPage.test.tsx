import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Cliente } from "../lib/clientes";
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
      // As operações embutidas (caixa, devolução, conferência) chamam o servidor assim
      // que o diálogo abre.
      caixaAberto: vi.fn(),
      autorizadores: vi.fn(),
      configuracao: vi.fn(),
    },
  };
});

vi.mock("../lib/comercial", () => ({
  comercial: { listProdutos: vi.fn() },
}));

vi.mock("../lib/clientes", () => ({
  clientes: { listar: vi.fn() },
}));

vi.mock("../lib/financeiro", () => ({
  financeiro: { listarContas: vi.fn() },
}));

const { pdv } = await import("../lib/pdv");
const { comercial } = await import("../lib/comercial");
const { clientes } = await import("../lib/clientes");
const { financeiro } = await import("../lib/financeiro");

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

/** Uma venda com um item lançado, que é a condição para cobrar e fechar. */
function vendaComItem(sobre: Partial<Venda> = {}): Venda {
  return umaVenda({
    itens: [
      {
        id: "item-1",
        produto_id: "produto-1",
        lote_id: null,
        unidade_id: "unidade-1",
        descricao: "Café torrado 500g",
        quantidade: "1",
        preco_unitario: "19.90",
        desconto: "0.00",
        total: "19.90",
      },
    ],
    soma_dos_itens: "19.90",
    total: "19.90",
    falta: "19.90",
    ...sobre,
  });
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

function umCliente(sobre: Partial<Cliente> = {}): Cliente {
  return {
    id: "cliente-1",
    tipo: "fisica",
    nome: "Maria da Silva",
    apelido: null,
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
    ...sobre,
  };
}

function abrirCaixa({
  podeIdentificar = false,
  podeAbrirCaixa = false,
  podeDevolver = false,
  podeConferir = false,
  podeAjustar = false,
} = {}) {
  return render(
    <PdvPage
      onBack={() => {}}
      empresa="Mercado do Teste"
      podeIdentificar={podeIdentificar}
      podeAbrirCaixa={podeAbrirCaixa}
      podeDevolver={podeDevolver}
      podeConferir={podeConferir}
      podeAjustar={podeAjustar}
    />,
  );
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
  vi.mocked(clientes.listar).mockResolvedValue([]);
  // Empresa sem o módulo `financeiro` é o padrão: a escolha de conta nem aparece.
  vi.mocked(financeiro.listarContas).mockResolvedValue([]);
  vi.mocked(pdv.caixaAberto).mockResolvedValue(null);
  vi.mocked(pdv.autorizadores).mockResolvedValue([]);
  vi.mocked(pdv.configuracao).mockResolvedValue({
    exige_cancelar_item: true,
    exige_cancelar_venda: true,
    exige_sangria: true,
    exige_devolucao: true,
    exige_desconto: false,
    desconto_livre: "0.00",
    exige_diferenca: false,
    diferenca_livre: "0.00",
  });
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

describe("PdvPage, recebendo", () => {
  it("já chega com o que falta preenchido", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(vendaComItem());

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    await usuario.click(screen.getByRole("button", { name: "Dinheiro" }));

    // O caso comum do balcão é receber exatamente o que falta. Obrigar a redigitar o
    // valor a cada venda é trabalho repetido com fila esperando.
    expect(screen.getByLabelText("Valor recebido")).toHaveProperty("value", "19.90");
  });

  it("manda o valor com ponto e a forma escolhida", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(vendaComItem());
    vi.mocked(pdv.pagar).mockResolvedValue(vendaComItem({ pago: "20.00", falta: "0.00" }));

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    await usuario.click(screen.getByRole("button", { name: "Pix" }));
    const valor = screen.getByLabelText("Valor recebido");
    await usuario.clear(valor);
    await usuario.type(valor, "20,00");
    await usuario.click(screen.getByRole("button", { name: "Receber" }));

    await waitFor(() =>
      expect(pdv.pagar).toHaveBeenCalledWith("venda-1", {
        forma: "pix",
        valor: "20.00",
        // Nulo porque esta empresa não tem conta cadastrada, que é o caso sem o módulo
        // `financeiro`. Ver ADR 0014.
        conta_id: null,
      }),
    );
  });
});

describe("PdvPage, fechando", () => {
  it("não deixa fechar enquanto falta receber", async () => {
    vi.mocked(pdv.abrir).mockResolvedValue(vendaComItem({ falta: "19.90" }));

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    // Fechar com saldo em aberto registraria a saída do estoque sem o dinheiro entrar.
    expect(screen.getByRole("button", { name: "Fechar venda" })).toHaveProperty("disabled", true);
  });

  it("não deixa cobrar nem fechar venda sem item", async () => {
    vi.mocked(pdv.abrir).mockResolvedValue(umaVenda());

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    expect(screen.getByRole("button", { name: "Dinheiro" })).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "Fechar venda" })).toHaveProperty("disabled", true);
  });

  it("fecha e mostra o número da venda e o troco", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(
      vendaComItem({ pago: "20.00", falta: "0.00", troco: "0.10" }),
    );
    vi.mocked(pdv.finalizar).mockResolvedValue(
      vendaComItem({
        numero: 42,
        status: "finalizada",
        pago: "20.00",
        falta: "0.00",
        troco: "0.10",
      }),
    );

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    await usuario.click(screen.getByRole("button", { name: "Fechar venda" }));

    // O número é o que o cliente ouve e o que se procura depois; o troco é o que a mão
    // devolve. Os dois têm de estar na tela sem rolagem nem clique.
    expect(await screen.findByText("42")).toBeTruthy();
    // Em dois lugares: o resumo da tela e o recibo imprimível, que tem de concordar com
    // ela — recibo que discorda do troco na tela é discussão no balcão.
    expect(screen.getAllByText("Troco").length).toBeGreaterThan(0);
  });

  it("não mostra linha de troco quando não há troco", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(vendaComItem({ pago: "19.90", falta: "0.00" }));
    vi.mocked(pdv.finalizar).mockResolvedValue(
      vendaComItem({ numero: 43, status: "finalizada", pago: "19.90", falta: "0.00", troco: "0.00" }),
    );

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());
    await usuario.click(screen.getByRole("button", { name: "Fechar venda" }));

    expect(await screen.findByText("43")).toBeTruthy();
    // Troco zero não é informação: é ruído. Vale para o resumo e para o recibo, e a
    // busca sem escopo cobre os dois.
    expect(screen.queryAllByText("Troco")).toHaveLength(0);
  });
});

describe("PdvPage, os atalhos de teclado", () => {
  it("F1 abre o recebimento em dinheiro, já com o que falta", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(vendaComItem());

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    await usuario.keyboard("{F1}");

    expect(await screen.findByText("Receber em Dinheiro")).toBeTruthy();
    expect(screen.getByLabelText("Valor recebido")).toHaveProperty("value", "19.90");
  });

  it("F4 abre o recebimento em Pix", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(vendaComItem());

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());
    await usuario.keyboard("{F4}");

    expect(await screen.findByText("Receber em Pix")).toBeTruthy();
  });

  it("segura a tecla para o navegador não levar a tela embora", async () => {
    vi.mocked(pdv.abrir).mockResolvedValue(vendaComItem());

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    // F1 abre a ajuda do navegador e F3 a busca. Sem `preventDefault`, o atalho funciona
    // e o caixa perde a tela de vista no mesmo gesto.
    const evento = new KeyboardEvent("keydown", { key: "F1", cancelable: true, bubbles: true });
    document.dispatchEvent(evento);
    expect(evento.defaultPrevented).toBe(true);
  });

  it("não faz nada em venda sem item", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(umaVenda());

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());
    await usuario.keyboard("{F1}");

    // O botão recusa venda vazia; atalho que aceitasse seria um caminho por fora da regra.
    expect(screen.queryByText("Receber em Dinheiro")).toBeNull();
  });

  it("não troca a forma com o recebimento já aberto", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(vendaComItem());

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());
    await usuario.keyboard("{F1}");
    expect(await screen.findByText("Receber em Dinheiro")).toBeTruthy();

    await usuario.keyboard("{F4}");

    // Trocar por baixo de quem já está digitando o valor faria o título do diálogo mentir
    // sobre o que vai ser registrado.
    expect(screen.getByText("Receber em Dinheiro")).toBeTruthy();
    expect(screen.queryByText("Receber em Pix")).toBeNull();
  });

  it("ignora a tecla com Ctrl, que é atalho do navegador", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(vendaComItem());

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());
    await usuario.keyboard("{Control>}{F1}{/Control}");

    expect(screen.queryByText("Receber em Dinheiro")).toBeNull();
  });
});

describe("PdvPage, identificando o cliente", () => {
  it("não oferece identificação quando a empresa não tem o módulo", async () => {
    abrirCaixa({ podeIdentificar: false });
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    /* Empresa que já tinha o PDV não ganha o módulo de clientes sozinha: instalar na
     * empresa dos outros sem pedido é o que a ADR 0010 recusa. Então a tela não oferece,
     * em vez de oferecer e falhar. */
    expect(screen.queryByRole("button", { name: "Identificar cliente" })).toBeNull();
    expect(screen.queryByText("Venda anônima.")).toBeNull();
  });

  it("diz que a venda é anônima, que é o caso normal", async () => {
    abrirCaixa({ podeIdentificar: true });
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    // A frase existe para não parecer um campo por preencher: balcão quase sempre vende
    // sem identificar, e isso não é pendência.
    expect(screen.getByText("Venda anônima.")).toBeTruthy();
  });

  it("prende o cliente escolhido à venda", async () => {
    const usuario = userEvent.setup();
    vi.mocked(clientes.listar).mockResolvedValue([umCliente()]);
    vi.mocked(pdv.identificar).mockResolvedValue(
      umaVenda({ cliente_id: "cliente-1", cliente_nome: "Maria da Silva" }),
    );

    abrirCaixa({ podeIdentificar: true });
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    await usuario.click(screen.getByRole("button", { name: "Identificar cliente" }));
    await usuario.type(screen.getByLabelText("Cliente"), "maria");
    await usuario.click(screen.getByRole("button", { name: "Procurar" }));
    await usuario.click(await screen.findByRole("button", { name: /Maria da Silva/ }));

    await waitFor(() => expect(pdv.identificar).toHaveBeenCalledWith("venda-1", "cliente-1"));
    expect(await screen.findByText("Maria da Silva")).toBeTruthy();
  });

  it("deixa tirar o cliente de volta", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(
      umaVenda({ cliente_id: "cliente-1", cliente_nome: "Maria da Silva" }),
    );
    vi.mocked(pdv.desidentificar).mockResolvedValue(umaVenda());

    abrirCaixa({ podeIdentificar: true });
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    await usuario.click(screen.getByRole("button", { name: "Tirar" }));

    await waitFor(() => expect(pdv.desidentificar).toHaveBeenCalledWith("venda-1"));
  });

  it("não identifica nada quando a busca não acha ninguém", async () => {
    const usuario = userEvent.setup();

    abrirCaixa({ podeIdentificar: true });
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    await usuario.click(screen.getByRole("button", { name: "Identificar cliente" }));
    await usuario.type(screen.getByLabelText("Cliente"), "ninguem");
    await usuario.click(screen.getByRole("button", { name: "Procurar" }));

    // A frase manda para o lugar certo em vez de só dizer não.
    expect(await screen.findByText(/Cadastre em Clientes/)).toBeTruthy();
    expect(pdv.identificar).not.toHaveBeenCalled();
  });
});

describe("PdvPage, a conta que recebeu", () => {
  it("não pergunta a conta quando a empresa não tem nenhuma", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(vendaComItem());

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());
    await usuario.click(screen.getByRole("button", { name: "Dinheiro" }));

    // O módulo `financeiro` pode não estar ativo. Perguntar "caiu em qual conta" sem ter
    // conta nenhuma é um campo vazio no meio do caixa.
    expect(screen.queryByLabelText("Caiu em")).toBeNull();
  });

  it("manda a conta escolhida junto do pagamento", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(vendaComItem());
    vi.mocked(pdv.pagar).mockResolvedValue(vendaComItem({ pago: "19.90", falta: "0.00" }));
    vi.mocked(financeiro.listarContas).mockResolvedValue([
      { id: "conta-1", nome: "Banco do Brasil", instituicao: null, chave_pix: null, ativa: true },
      { id: "conta-2", nome: "Gaveta do caixa", instituicao: null, chave_pix: null, ativa: true },
    ]);

    abrirCaixa();
    await waitFor(() => expect(financeiro.listarContas).toHaveBeenCalled());
    await usuario.click(screen.getByRole("button", { name: "Pix" }));

    await usuario.selectOptions(await screen.findByLabelText("Caiu em"), "conta-1");
    await usuario.click(screen.getByRole("button", { name: "Receber" }));

    // É o que permite fechar o caixa sabendo o que entrou em cada lugar — ADR 0014.
    await waitFor(() =>
      expect(pdv.pagar).toHaveBeenCalledWith("venda-1", {
        forma: "pix",
        valor: "19.90",
        conta_id: "conta-1",
      }),
    );
  });
});

describe("PdvPage, desfazendo", () => {
  /* As três operações que tiram algo da venda.
   *
   * São as que mais merecem guarda: num balcão, retirar o item errado, apagar um
   * pagamento já recebido ou cancelar a venda inteira são erros que custam dinheiro e
   * que o operador comete com a fila olhando. */

  it("retira o item pelo botão que diz qual é", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(vendaComItem());
    vi.mocked(pdv.removerItem).mockResolvedValue(umaVenda());

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    // O rótulo nomeia o produto: "Retirar", sozinho, numa lista de itens, não diz qual
    // sai — e é o que o leitor de tela anuncia.
    await usuario.click(screen.getByRole("button", { name: "Retirar Café torrado 500g" }));

    await waitFor(() => expect(pdv.removerItem).toHaveBeenCalledWith("venda-1", "item-1", undefined));
  });

  it("retira um pagamento já lançado", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(
      vendaComItem({
        pagamentos: [
          {
            id: "pagamento-1",
            forma: "dinheiro",
            valor: "19.90",
            conta_id: null,
            conta_nome: null,
          },
        ],
        pago: "19.90",
        falta: "0.00",
      }),
    );
    vi.mocked(pdv.removerPagamento).mockResolvedValue(vendaComItem());

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    // Digitou 50 onde era 5: sem desfazer, a saída é cancelar a venda inteira e bipar
    // tudo de novo.
    await usuario.click(screen.getByRole("button", { name: "Retirar pagamento" }));

    await waitFor(() =>
      expect(pdv.removerPagamento).toHaveBeenCalledWith("venda-1", "pagamento-1"),
    );
  });

  it("cancela a venda e fica sem venda aberta", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(vendaComItem());
    vi.mocked(pdv.cancelar).mockResolvedValue(vendaComItem({ status: "cancelada" }));

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    await usuario.click(screen.getByRole("button", { name: "Cancelar venda" }));
    await waitFor(() => expect(pdv.cancelar).toHaveBeenCalledWith("venda-1", undefined));

    /* Cancelar não pode deixar a tela apontando para uma venda que não existe mais. O
     * caixa fica sem venda aberta, e a única coisa oferecida é abrir outra. */
    expect(await screen.findByRole("button", { name: "Abrir venda" })).toBeTruthy();
  });

  it("abre outra venda depois de fechar a anterior", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(vendaComItem({ pago: "19.90", falta: "0.00" }));
    vi.mocked(pdv.finalizar).mockResolvedValue(
      vendaComItem({ numero: 7, status: "finalizada", pago: "19.90", falta: "0.00" }),
    );

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());
    await usuario.click(screen.getByRole("button", { name: "Fechar venda" }));
    expect(await screen.findByText("7")).toBeTruthy();

    vi.mocked(pdv.abrir).mockClear();
    await usuario.click(screen.getByRole("button", { name: "Nova venda" }));

    // A fila não espera: o caminho do fim de uma venda para o começo da próxima é um
    // clique, sem voltar para a tela inicial.
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());
  });
});

describe("PdvPage, o desconto", () => {
  /* O servidor aceitava desconto desde o início e nenhuma tela chamava: a rota existia,
   * `lib/pdv.ts` embrulhava, e o operador não tinha como dar. A regra continua sendo do
   * servidor — não negativo, não maior que a soma, só em venda aberta — e estes testes
   * cuidam só do caminho até lá. */

  it("não oferece desconto em venda sem item", async () => {
    vi.mocked(pdv.abrir).mockResolvedValue(umaVenda());

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    // Sem item a soma é zero, e qualquer desconto seria recusado pelo servidor. Oferecer
    // um caminho que só pode falhar é pior que não oferecer.
    expect(screen.getByRole("button", { name: "Dar desconto" })).toHaveProperty("disabled", true);
  });

  it("manda o valor com ponto, mesmo digitado com vírgula", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(vendaComItem());
    vi.mocked(pdv.definirDesconto).mockResolvedValue(vendaComItem({ desconto: "1.50" }));

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    await usuario.click(screen.getByRole("button", { name: "Dar desconto" }));
    await usuario.type(await screen.findByLabelText("Desconto"), "1,50");
    await usuario.click(screen.getByRole("button", { name: "Aplicar" }));

    await waitFor(() => expect(pdv.definirDesconto).toHaveBeenCalledWith("venda-1", "1.50", undefined));
  });

  it("zero tira o desconto que já existia", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(vendaComItem({ desconto: "2.00" }));
    vi.mocked(pdv.definirDesconto).mockResolvedValue(vendaComItem());

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());

    // Com desconto posto, o botão diz outra coisa — quem olha a tela precisa saber que
    // já há um, e que vai alterá-lo em vez de somar outro.
    const botao = screen.getByRole("button", { name: "Alterar desconto" });
    await usuario.click(botao);

    const campo = await screen.findByLabelText("Desconto");
    // Já vem preenchido com o que está valendo, para não parecer que zerou sozinho.
    expect(campo).toHaveProperty("value", "2.00");

    await usuario.clear(campo);
    await usuario.type(campo, "0");
    await usuario.click(screen.getByRole("button", { name: "Aplicar" }));

    await waitFor(() => expect(pdv.definirDesconto).toHaveBeenCalledWith("venda-1", "0", undefined));
  });

  it("os atalhos de pagamento não disparam com o desconto aberto", async () => {
    const usuario = userEvent.setup();
    vi.mocked(pdv.abrir).mockResolvedValue(vendaComItem());

    abrirCaixa();
    await waitFor(() => expect(pdv.abrir).toHaveBeenCalled());
    await usuario.click(screen.getByRole("button", { name: "Dar desconto" }));
    expect(await screen.findByLabelText("Desconto")).toBeTruthy();

    await usuario.keyboard("{F1}");

    // F1 por cima do diálogo de desconto abriria o recebimento em cima dele.
    expect(screen.queryByText("Receber em Dinheiro")).toBeNull();
  });
});

describe("PdvPage, as teclas de função", () => {
  it("engole F1 a F4 mesmo sem venda aberta", async () => {
    // O defeito que isto guarda: o efeito só se ligava com venda e item, então na tela
    // parada — a maior parte do expediente — F1 abria a ajuda do navegador e F3 a busca,
    // por cima do caixa. Tecla que às vezes faz outra coisa é pior do que tecla que não
    // faz nada.
    abrirCaixa();
    // O PDV abre a venda sozinho quando não há pendente: esperar pelo campo de código
    // é esperar pela tela pronta.
    await screen.findByLabelText("Código, código de barras ou nome");

    for (const tecla of ["F1", "F2", "F3", "F4"]) {
      // `fireEvent` devolve false quando o evento foi cancelado.
      expect(fireEvent.keyDown(document, { key: tecla })).toBe(false);
    }
  });

  it("não toma a tecla quando há modificador", async () => {
    // Ctrl+F4 fecha a aba, e tomar isso do usuário seria pior do que não ter atalho.
    abrirCaixa();
    // O PDV abre a venda sozinho quando não há pendente: esperar pelo campo de código
    // é esperar pela tela pronta.
    await screen.findByLabelText("Código, código de barras ou nome");

    expect(fireEvent.keyDown(document, { key: "F4", ctrlKey: true })).toBe(true);
  });
});

describe("PdvPage, as operações de caixa", () => {
  it("não oferece o que a pessoa não alcança", async () => {
    abrirCaixa();
    // O PDV abre a venda sozinho quando não há pendente: esperar pelo campo de código
    // é esperar pela tela pronta.
    await screen.findByLabelText("Código, código de barras ou nome");

    expect(screen.queryByRole("button", { name: "Meu caixa" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Devolução" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Conferência do dia" })).toBeNull();
  });

  it("abre o caixa do operador sobreposto, sem sair do balcão", async () => {
    const usuario = userEvent.setup();
    abrirCaixa({ podeAbrirCaixa: true });

    await usuario.click(await screen.findByRole("button", { name: "Meu caixa" }));

    // Diálogo de verdade: trava o que está atrás e fecha no Esc — é o que o torna
    // operação sobreposta, e não outra tela.
    const dialogo = await screen.findByRole("dialog");
    expect(dialogo).toBeTruthy();
    expect(await screen.findByLabelText("Fundo de troco")).toBeTruthy();
  });

  it("oferece a conferência do dia a quem pode conferir", async () => {
    const usuario = userEvent.setup();
    abrirCaixa({ podeConferir: true });

    await usuario.click(await screen.findByRole("button", { name: "Conferência do dia" }));

    expect(await screen.findByLabelText("Quanto há na gaveta")).toBeTruthy();
  });

  it("abre os ajustes do caixa para quem administra a loja", async () => {
    const usuario = userEvent.setup();
    abrirCaixa({ podeAjustar: true });

    await usuario.click(await screen.findByRole("button", { name: "Ajustes do caixa" }));

    // É configuração do caixa, e é no caixa que se procura por ela.
    expect(await screen.findByLabelText("Sangria")).toBeTruthy();
  });

  it("cada botão depende da sua própria permissão", async () => {
    // Afirmar só "sem permissão nenhuma, nada aparece" não guarda nada: cada guarda
    // esconderia o erro da outra. Aqui uma permissão está ligada e as demais não.
    abrirCaixa({ podeConferir: true });
    await screen.findByRole("button", { name: "Conferência do dia" });

    expect(screen.queryByRole("button", { name: "Meu caixa" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Devolução" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Ajustes do caixa" })).toBeNull();
  });
});
