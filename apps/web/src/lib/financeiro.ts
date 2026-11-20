import { authedJson } from "./api";

/** Um lugar de dinheiro: banco, chave Pix, ou a gaveta do caixa.
 *
 * Chamava-se conta **de recebimento** enquanto só entrava dinheiro. A baixa da despesa sai
 * da mesma conta em que a venda entra — ver docs/adr/0024-contas-a-pagar.md, decisão 2. */
export interface Conta {
  id: string;
  nome: string;
  instituicao: string | null;
  chave_pix: string | null;
  ativa: boolean;
}

/** Contra o quê o dinheiro saiu: lavoura, pecuária, frota, loja centro. Lista plana. */
export interface CentroDeCusto {
  id: string;
  nome: string;
  ativo: boolean;
}

export type StatusDespesa = "aberta" | "paga" | "cancelada";

/** Uma conta a pagar. `valor` é o que se deve; `valor_pago`, o que de fato saiu. */
export interface Despesa {
  id: string;
  descricao: string;
  fornecedor_nome: string | null;
  fornecedor_cpf_cnpj: string | null;
  valor: string;
  vencimento: string;
  status: StatusDespesa;
  pago_em: string | null;
  valor_pago: string | null;
  conta_id: string | null;
  centro_custo_id: string | null;
  observacao: string | null;
}

export interface PorCentro {
  centro_id: string | null;
  nome: string;
  em_aberto: string;
  pago: string;
}

export interface ResumoFinanceiro {
  em_aberto: string;
  pago: string;
  vencido: string;
  quantidade_em_aberto: number;
  por_centro: PorCentro[];
}

export interface DespesaBody {
  descricao: string;
  valor: string;
  vencimento: string;
  fornecedor_nome?: string | null;
  fornecedor_cpf_cnpj?: string | null;
  centro_custo_id?: string | null;
  observacao?: string | null;
}

function query(params: Record<string, string | undefined>): string {
  const pares = Object.entries(params).filter(([, valor]) => valor);
  if (pares.length === 0) return "";
  return "?" + new URLSearchParams(pares as [string, string][]).toString();
}

export const financeiro = {
  listarContas: (incluirInativas = false): Promise<Conta[]> =>
    authedJson(`/financeiro/contas${incluirInativas ? "?incluir_inativas=true" : ""}`),

  criarConta: (body: {
    nome: string;
    instituicao?: string | null;
    chave_pix?: string | null;
  }): Promise<Conta> => authedJson("/financeiro/contas", { method: "POST", body }),

  desativarConta: (contaId: string): Promise<Conta> =>
    authedJson(`/financeiro/contas/${contaId}/desativar`, { method: "POST" }),

  reativarConta: (contaId: string): Promise<Conta> =>
    authedJson(`/financeiro/contas/${contaId}/reativar`, { method: "POST" }),

  listarCentros: (incluirInativos = false): Promise<CentroDeCusto[]> =>
    authedJson(
      `/financeiro/centros-de-custo${incluirInativos ? "?incluir_inativos=true" : ""}`,
    ),

  criarCentro: (nome: string): Promise<CentroDeCusto> =>
    authedJson("/financeiro/centros-de-custo", { method: "POST", body: { nome } }),

  desativarCentro: (centroId: string): Promise<CentroDeCusto> =>
    authedJson(`/financeiro/centros-de-custo/${centroId}/desativar`, { method: "POST" }),

  reativarCentro: (centroId: string): Promise<CentroDeCusto> =>
    authedJson(`/financeiro/centros-de-custo/${centroId}/reativar`, { method: "POST" }),

  listarDespesas: (filtros: {
    de?: string;
    ate?: string;
    situacao?: StatusDespesa;
    centro_custo_id?: string;
  }): Promise<Despesa[]> => authedJson(`/financeiro/despesas${query(filtros)}`),

  resumo: (de: string, ate: string): Promise<ResumoFinanceiro> =>
    authedJson(`/financeiro/despesas/resumo${query({ de, ate })}`),

  lancarDespesa: (body: DespesaBody): Promise<Despesa> =>
    authedJson("/financeiro/despesas", { method: "POST", body }),

  editarDespesa: (despesaId: string, body: Partial<DespesaBody>): Promise<Despesa> =>
    authedJson(`/financeiro/despesas/${despesaId}`, { method: "PUT", body }),

  baixarDespesa: (
    despesaId: string,
    body: { pago_em: string; valor_pago?: string | null; conta_id?: string | null },
  ): Promise<Despesa> =>
    authedJson(`/financeiro/despesas/${despesaId}/baixar`, { method: "POST", body }),

  cancelarDespesa: (despesaId: string): Promise<Despesa> =>
    authedJson(`/financeiro/despesas/${despesaId}/cancelar`, { method: "POST" }),
};
