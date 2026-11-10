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
  /** Em qual conta o dinheiro caiu. Nulo quando o caixa não escolheu — e isso é normal. */
  conta_id: string | null;
  conta_nome: string | null;
}

/* Os totais vêm somados do servidor — a tela não soma dinheiro. Ver ADR 0008, decisão 3. */
export interface Venda {
  id: string;
  numero: number | null;
  status: StatusVenda;
  aberta_em: string;
  fechada_em: string | null;
  observacao: string | null;
  /** Nulo é o caso normal: venda anônima de balcão. */
  cliente_id: string | null;
  /** Lido na hora pelo servidor, não copiado para dentro da venda. */
  cliente_nome: string | null;
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

export interface LinhaDaForma {
  forma: FormaPagamento;
  quantidade: number;
  valor: string;
}

export interface LinhaDaConta {
  conta_id: string | null;
  conta_nome: string | null;
  valor: string;
}

export interface LinhaDoOperador {
  operador_id: string | null;
  operador_nome: string | null;
  vendas: number;
  valor: string;
}

/** O que entrou num período. Leitura do que aconteceu, não fechamento de caixa. */
export interface Conferencia {
  de: string;
  ate: string;
  vendas: number;
  canceladas: number;
  bruto: string;
  descontos: string;
  liquido: string;
  recebido: string;
  por_forma: LinhaDaForma[];
  por_conta: LinhaDaConta[];
  por_operador: LinhaDoOperador[];
}

export const pdv = {
  /* Os instantes vão com fuso, de propósito: o dia que importa é o dia local de quem
   * está no balcão, e o servidor não tem como adivinhar qual é. */
  conferencia: (de: Date, ate: Date): Promise<Conferencia> =>
    authedJson(
      `/pdv/conferencia?de=${encodeURIComponent(de.toISOString())}` +
        `&ate=${encodeURIComponent(ate.toISOString())}`,
    ),

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

  pagar: (
    vendaId: string,
    body: { forma: FormaPagamento; valor: string; conta_id?: string | null },
  ): Promise<Venda> =>
    authedJson(`/pdv/vendas/${vendaId}/pagamentos`, { method: "POST", body }),

  removerPagamento: (vendaId: string, pagamentoId: string): Promise<Venda> =>
    authedJson(`/pdv/vendas/${vendaId}/pagamentos/${pagamentoId}`, { method: "DELETE" }),

  identificar: (vendaId: string, clienteId: string): Promise<Venda> =>
    authedJson(`/pdv/vendas/${vendaId}/cliente`, {
      method: "PUT",
      body: { cliente_id: clienteId },
    }),

  desidentificar: (vendaId: string): Promise<Venda> =>
    authedJson(`/pdv/vendas/${vendaId}/cliente`, { method: "DELETE" }),

  finalizar: (vendaId: string): Promise<Venda> =>
    authedJson(`/pdv/vendas/${vendaId}/finalizar`, { method: "POST" }),

  cancelar: (vendaId: string): Promise<Venda> =>
    authedJson(`/pdv/vendas/${vendaId}/cancelar`, { method: "POST" }),
};
