import { authedJson } from "./api";

export type StatusVenda = "aberta" | "finalizada" | "cancelada";

export type FormaPagamento = "dinheiro" | "debito" | "credito" | "pix" | "outro";

export const FORMAS: { valor: FormaPagamento; label: string; atalho: string }[] = [
  { valor: "dinheiro", label: "Dinheiro", atalho: "F1" },
  { valor: "debito", label: "Débito", atalho: "F2" },
  { valor: "credito", label: "Crédito", atalho: "F3" },
  { valor: "pix", label: "Pix", atalho: "F4" },
];

export interface ItemVenda {
  id: string;
  produto_id: string;
  lote_id: string | null;
  unidade_id: string;
  descricao: string;
  quantidade: string;
  preco_unitario: string;
  desconto: string;
  total: string;
}

export interface PagamentoVenda {
  id: string;
  forma: FormaPagamento;
  valor: string;
}

/* Os totais vêm somados do servidor — a tela não soma dinheiro. Ver ADR 0008, decisão 3. */
export interface Venda {
  id: string;
  numero: number | null;
  status: StatusVenda;
  aberta_em: string;
  fechada_em: string | null;
  observacao: string | null;
  itens: ItemVenda[];
  pagamentos: PagamentoVenda[];
  soma_dos_itens: string;
  desconto: string;
  total: string;
  pago: string;
  falta: string;
  troco: string;
}

export interface VendaResumo {
  id: string;
  numero: number | null;
  status: StatusVenda;
  aberta_em: string;
  fechada_em: string | null;
  total: string | null;
}

export const pdv = {
  listVendas: (status?: StatusVenda): Promise<VendaResumo[]> =>
    authedJson(status ? `/pdv/vendas?status=${status}` : "/pdv/vendas"),

  abrir: (): Promise<Venda> => authedJson("/pdv/vendas", { method: "POST" }),

  ver: (vendaId: string): Promise<Venda> => authedJson(`/pdv/vendas/${vendaId}`),

  adicionarItem: (
    vendaId: string,
    body: {
      produto_id: string;
      quantidade: string;
      unidade_id?: string | null;
      lote_id?: string | null;
      preco_unitario?: string | null;
      desconto?: string;
    },
  ): Promise<Venda> => authedJson(`/pdv/vendas/${vendaId}/itens`, { method: "POST", body }),

  removerItem: (vendaId: string, itemId: string): Promise<Venda> =>
    authedJson(`/pdv/vendas/${vendaId}/itens/${itemId}`, { method: "DELETE" }),

  definirDesconto: (vendaId: string, desconto: string): Promise<Venda> =>
    authedJson(`/pdv/vendas/${vendaId}/desconto`, { method: "PUT", body: { desconto } }),

  pagar: (vendaId: string, body: { forma: FormaPagamento; valor: string }): Promise<Venda> =>
    authedJson(`/pdv/vendas/${vendaId}/pagamentos`, { method: "POST", body }),

  removerPagamento: (vendaId: string, pagamentoId: string): Promise<Venda> =>
    authedJson(`/pdv/vendas/${vendaId}/pagamentos/${pagamentoId}`, { method: "DELETE" }),

  finalizar: (vendaId: string): Promise<Venda> =>
    authedJson(`/pdv/vendas/${vendaId}/finalizar`, { method: "POST" }),

  cancelar: (vendaId: string): Promise<Venda> =>
    authedJson(`/pdv/vendas/${vendaId}/cancelar`, { method: "POST" }),
};
