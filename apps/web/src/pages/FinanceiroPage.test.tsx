import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import type { CentroDeCusto, Conta, Despesa, ResumoFinanceiro } from "../lib/financeiro";
import { FinanceiroPage } from "./FinanceiroPage";

/* O financeiro numa tela só.
 *
 * O que estes testes guardam é a regra que o backend impõe e a tela precisa respeitar: a
 * baixa sem valor vale o que se devia, e a despesa paga perde as ações. E guardam o
 * desenho pedido — cadastro acontece em submodal, sem perder o que já foi digitado no
 * diálogo de baixo.
 *
 * Decisões: docs/adr/0024-contas-a-pagar.md e docs/adr/0025-centro-de-custo.md. */

vi.mock("../lib/financeiro", async (original) => ({
  ...(await original<typeof import("../lib/financeiro")>()),
  financeiro: {
    listarContas: vi.fn(),
    criarConta: vi.fn(),
    desativarConta: vi.fn(),
    reativarConta: vi.fn(),
    listarCentros: vi.fn(),
    criarCentro: vi.fn(),
    desativarCentro: vi.fn(),
    reativarCentro: vi.fn(),
    listarDespesas: vi.fn(),
    resumo: vi.fn(),
    lancarDespesa: vi.fn(),
    editarDespesa: vi.fn(),
    baixarDespesa: vi.fn(),
    cancelarDespesa: vi.fn(),
  },
}));

const { financeiro } = await import("../lib/financeiro");

const LAVOURA: CentroDeCusto = { id: "cc-lavoura", nome: "Lavoura", ativo: true };

const NUBANK: Conta = {
  id: "ct-nubank",
  nome: "Nubank PJ",
  instituicao: "Nubank",
  chave_pix: null,
  ativa: true,
};

const ENERGIA: Despesa = {
  id: "d-energia",
  descricao: "Energia da sede",
  fornecedor_nome: "Enel",
  fornecedor_cpf_cnpj: null,
  valor: "480.00",
  vencimento: "2026-12-10",
  status: "aberta",
  pago_em: null,
  valor_pago: null,
  conta_id: null,
  centro_custo_id: "cc-lavoura",
  observacao: null,
};

const RESUMO: ResumoFinanceiro = {
  em_aberto: "480.00",
  pago: "0",
  vencido: "0",
  quantidade_em_aberto: 1,
  por_centro: [
    { centro_id: "cc-lavoura", nome: "Lavoura", em_aberto: "480.00", pago: "0" },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(financeiro.listarDespesas).mockResolvedValue([ENERGIA]);
  vi.mocked(financeiro.resumo).mockResolvedValue(RESUMO);
  vi.mocked(financeiro.listarContas).mockResolvedValue([NUBANK]);
  vi.mocked(financeiro.listarCentros).mockResolvedValue([LAVOURA]);
  vi.mocked(financeiro.lancarDespesa).mockResolvedValue(ENERGIA);
  vi.mocked(financeiro.baixarDespesa).mockResolvedValue({ ...ENERGIA, status: "paga" });
  vi.mocked(financeiro.criarCentro).mockResolvedValue(LAVOURA);
});

it("mostra o que vence e contra o quê", async () => {
  render(<FinanceiroPage onBack={() => {}} />);

  expect(await screen.findByText("Energia da sede")).toBeTruthy();
  expect(screen.getByText(/1 conta em aberto/)).toBeTruthy();
  // A quebra por centro é a resposta de "contra o quê o dinheiro saiu".
  expect(screen.getByText(/480,00 a pagar/)).toBeTruthy();
});

it("baixa sem valor não manda valor, para o servidor usar o que se devia", async () => {
  const usuario = userEvent.setup();
  render(<FinanceiroPage onBack={() => {}} />);

  await usuario.click(await screen.findByRole("button", { name: "Dar baixa" }));
  await usuario.click(screen.getByRole("button", { name: "Marcar como paga" }));

  await waitFor(() => expect(financeiro.baixarDespesa).toHaveBeenCalled());
  const [, corpo] = vi.mocked(financeiro.baixarDespesa).mock.calls[0];
  expect(corpo.valor_pago).toBeNull();
});

it("despesa paga não oferece baixa nem cancelamento", async () => {
  vi.mocked(financeiro.listarDespesas).mockResolvedValue([
    { ...ENERGIA, status: "paga", pago_em: "2026-12-09", valor_pago: "475.20" },
  ]);
  render(<FinanceiroPage onBack={() => {}} />);

  expect(await screen.findByText("Paga")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Dar baixa" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Cancelar" })).toBeNull();
  // O valor mostrado é o que saiu, e não o que se devia.
  expect(screen.getByText("R$ 475,20")).toBeTruthy();
});

it("cria centro de custo em submodal sem perder o lançamento em andamento", async () => {
  const usuario = userEvent.setup();
  render(<FinanceiroPage onBack={() => {}} />);

  await usuario.click(await screen.findByRole("button", { name: "Lançar despesa" }));
  await usuario.type(screen.getByLabelText("Descrição"), "Adubo");
  await usuario.click(screen.getByRole("button", { name: "+ Novo centro de custo" }));

  await usuario.type(screen.getByLabelText("Nome"), "Pecuária");
  await usuario.click(screen.getByRole("button", { name: "Criar" }));

  await waitFor(() => expect(financeiro.criarCentro).toHaveBeenCalledWith("Pecuária"));
  // O diálogo de baixo continua de pé, com o que já tinha sido digitado.
  const campo = screen.getByLabelText("Descrição") as HTMLInputElement;
  expect(campo.value).toBe("Adubo");
});

it("cancelar pede confirmação antes de mexer em alguma coisa", async () => {
  const usuario = userEvent.setup();
  render(<FinanceiroPage onBack={() => {}} />);

  await usuario.click(await screen.findByRole("button", { name: "Cancelar" }));

  expect(screen.getByText("Esta conta não será paga?")).toBeTruthy();
  expect(financeiro.cancelarDespesa).not.toHaveBeenCalled();
});

it("com o módulo de custo, a quebra soma estoque e despesa", async () => {
  const { custos } = await import("../lib/custos");
  vi.spyOn(custos, "porCentro").mockResolvedValue([
    {
      centro_id: "cc-lavoura",
      nome: "Lavoura",
      consumo: "1000.00",
      despesa: "3000.00",
      total: "4000.00",
    },
  ]);

  render(<FinanceiroPage temCustos onBack={() => {}} />);

  expect(await screen.findByText("Quanto custou cada centro")).toBeTruthy();
  expect(screen.getByText("R$ 4.000,00")).toBeTruthy();
  expect(screen.getByText(/1.000,00 de estoque/)).toBeTruthy();
});

it("sem o módulo de custo, a quebra continua sendo só de despesa", async () => {
  render(<FinanceiroPage onBack={() => {}} />);

  expect(await screen.findByText("Contra o quê")).toBeTruthy();
  expect(screen.queryByText("Quanto custou cada centro")).toBeNull();
});

it("lançar consumo avisa, antes de enviar, que o produto não tem preço de custo", async () => {
  const usuario = userEvent.setup();
  const { comercial } = await import("../lib/comercial");
  vi.spyOn(comercial, "listUnidades").mockResolvedValue([
    { id: "un", nome: "Unidade", simbolo: null, referencia_id: null, fator: "1" } as never,
  ]);
  vi.spyOn(comercial, "listProdutos").mockResolvedValue([
    {
      id: "p-semente",
      codigo: "SEM-1",
      nome: "Semente",
      unidade_id: "un",
      preco_custo: null,
      ativo: true,
    } as never,
  ]);
  const { custos } = await import("../lib/custos");
  vi.spyOn(custos, "porCentro").mockResolvedValue([]);
  vi.spyOn(custos, "listarConsumos").mockResolvedValue([]);

  render(<FinanceiroPage temCustos onBack={() => {}} />);
  await usuario.click(await screen.findByRole("button", { name: "Lançar consumo" }));

  await screen.findByLabelText("Buscar produto");
  await usuario.selectOptions(screen.getByLabelText("Produto"), "p-semente");
  await usuario.type(screen.getByLabelText("Quantidade"), "10");

  /* O aviso aparece na tela, e não só na recusa do servidor: quem está lançando dez
     linhas descobriria tarde demais. */
  expect(
    await screen.findByText(/não tem preço de custo. Informe o valor/i),
  ).toBeTruthy();
});

it("o centro de custo é obrigatório para lançar consumo", async () => {
  const usuario = userEvent.setup();
  const { comercial } = await import("../lib/comercial");
  vi.spyOn(comercial, "listUnidades").mockResolvedValue([
    { id: "un", nome: "Unidade", simbolo: null, referencia_id: null, fator: "1" } as never,
  ]);
  vi.spyOn(comercial, "listProdutos").mockResolvedValue([
    {
      id: "p-adubo",
      codigo: "AD-1",
      nome: "Adubo",
      unidade_id: "un",
      preco_custo: "10.00",
      ativo: true,
    } as never,
  ]);
  const { custos } = await import("../lib/custos");
  vi.spyOn(custos, "porCentro").mockResolvedValue([]);
  vi.spyOn(custos, "listarConsumos").mockResolvedValue([]);

  render(<FinanceiroPage temCustos onBack={() => {}} />);
  await usuario.click(await screen.findByRole("button", { name: "Lançar consumo" }));
  await screen.findByLabelText("Buscar produto");
  await usuario.selectOptions(screen.getByLabelText("Produto"), "p-adubo");
  await usuario.type(screen.getByLabelText("Quantidade"), "10");

  const lancar = screen.getByRole("button", { name: "Lançar" });
  expect((lancar as HTMLButtonElement).disabled).toBe(true);

  await usuario.selectOptions(screen.getByLabelText("Centro de custo"), "cc-lavoura");
  expect((screen.getByRole("button", { name: "Lançar" }) as HTMLButtonElement).disabled).toBe(
    false,
  );
});

it("sem nada lançado no mês, a seção de custo continua de pé com o caminho adiante", async () => {
  /* Se ela sumisse, o botão de lançar consumo sumiria junto — e o primeiro dia de uso
     seria um beco sem saída. `docs/BRAND.md`, seção 8: estado vazio explica o próximo
     passo, nunca uma tela em branco. */
  const { custos } = await import("../lib/custos");
  vi.spyOn(custos, "porCentro").mockResolvedValue([]);
  vi.spyOn(custos, "listarConsumos").mockResolvedValue([]);

  render(<FinanceiroPage temCustos onBack={() => {}} />);

  expect(await screen.findByText("Quanto custou cada centro")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Lançar consumo" })).toBeTruthy();
  expect(screen.getByText(/Nada lançado contra centro de custo neste mês/)).toBeTruthy();
});
