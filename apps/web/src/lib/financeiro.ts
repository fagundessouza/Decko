import { authedJson } from "./api";

/** Um destino de dinheiro: banco, chave Pix, ou a gaveta do caixa. */
export interface ContaRecebimento {
  id: string;
  nome: string;
  instituicao: string | null;
  chave_pix: string | null;
  ativa: boolean;
}

export const financeiro = {
  listarContas: (incluirInativas = false): Promise<ContaRecebimento[]> =>
    authedJson(`/financeiro/contas${incluirInativas ? "?incluir_inativas=true" : ""}`),

  criarConta: (body: {
    nome: string;
    instituicao?: string | null;
    chave_pix?: string | null;
  }): Promise<ContaRecebimento> =>
    authedJson("/financeiro/contas", { method: "POST", body }),

  desativarConta: (contaId: string): Promise<ContaRecebimento> =>
    authedJson(`/financeiro/contas/${contaId}/desativar`, { method: "POST" }),

  reativarConta: (contaId: string): Promise<ContaRecebimento> =>
    authedJson(`/financeiro/contas/${contaId}/reativar`, { method: "POST" }),
};
