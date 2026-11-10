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

export type TipoMovimentoCaixa = "sangria" | "suprimento";

export interface MovimentoCaixa {
  id: string;
  tipo: TipoMovimentoCaixa;
  valor: string;
  motivo: string;
  created_at: string;
}

/** Uma sessão de caixa: o que passou pelas mãos de um operador, entre abrir e fechar.
 *
 * Repare no que **não** vem: o esperado, enquanto a sessão está aberta. É a conferência
 * cega da ADR 0008 valendo também na rede — devolvê-lo bastaria abrir o inspetor para ver
 * o número antes de contar. Ele chega na resposta do fechamento. */
export interface Caixa {
  id: string;
  operador_id: string;
  aberto_em: string;
  fechado_em: string | null;
  abertura: string;
  contado: string | null;
  esperado: string | null;
  diferenca: string | null;
  observacao: string | null;
  movimentos: MovimentoCaixa[];
}

export type DestinoDevolucao = "estoque" | "avaria";

export const DESTINOS: { valor: DestinoDevolucao; label: string; ajuda: string }[] = [
  {
    valor: "estoque",
    label: "Volta para vender",
    ajuda: "Entra de novo no estoque, como entrada na razão.",
  },
  {
    valor: "avaria",
    label: "Tem defeito",
    ajuda: "Não volta ao estoque vendável; fica na lista de avarias.",
  },
];

export interface ItemDevolucao {
  id: string;
  venda_item_id: string;
  quantidade: string;
  valor: string;
  destino: DestinoDevolucao;
}

export interface Devolucao {
  id: string;
  venda_id: string;
  operador_id: string | null;
  /** Nulo quando quem registrou não tinha caixa aberto: fica fora de sessão. */
  caixa_id: string | null;
  forma: FormaPagamento;
  motivo: string;
  total: string;
  created_at: string;
  itens: ItemDevolucao[];
}

/** Uma linha da venda e o que dela ainda dá para devolver. */
export interface LinhaDevolvivel {
  venda_item_id: string;
  descricao: string;
  unidade_id: string;
  quantidade: string;
  devolvida: string;
  resta: string;
  /** Quanto sai da gaveta se esta linha voltar inteira. Conta do servidor. */
  valor_resta: string;
}

export interface DevolucoesDaVenda {
  venda_id: string;
  numero: number | null;
  fechada_em: string | null;
  total: string;
  linhas: LinhaDevolvivel[];
  devolucoes: Devolucao[];
  devolvido: string;
}

/** Quanto sai da gaveta, conferido pelo servidor e sem nada gravado. */
export interface PreviaDevolucao {
  total: string;
  valores: string[];
}

export interface LinhaDeAvaria {
  produto_id: string;
  descricao: string;
  unidade_id: string;
  unidade_simbolo: string | null;
  quantidade: string;
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
  /* O que voltou. Sem isto a gaveta não fecha numa loja que devolve. */
  devolucoes: number;
  devolvido: string;
  devolvido_em_especie: string;
  avarias: LinhaDeAvaria[];
}

export const pdv = {
  caixaAberto: (): Promise<Caixa | null> => authedJson("/pdv/caixa/aberto"),

  abrirCaixa: (abertura: string): Promise<Caixa> =>
    authedJson("/pdv/caixa", { method: "POST", body: { abertura } }),

  movimentarCaixa: (
    caixaId: string,
    body: { tipo: TipoMovimentoCaixa; valor: string; motivo: string },
  ): Promise<Caixa> =>
    authedJson(`/pdv/caixa/${caixaId}/movimentos`, { method: "POST", body }),

  fecharCaixa: (
    caixaId: string,
    body: { contado: string; observacao?: string | null },
  ): Promise<Caixa> => authedJson(`/pdv/caixa/${caixaId}/fechar`, { method: "POST", body }),

  /* Os instantes vão com fuso, de propósito: o dia que importa é o dia local de quem
   * está no balcão, e o servidor não tem como adivinhar qual é. */
  conferencia: (de: Date, ate: Date): Promise<Conferencia> =>
    authedJson(
      `/pdv/conferencia?de=${encodeURIComponent(de.toISOString())}` +
        `&ate=${encodeURIComponent(ate.toISOString())}`,
    ),

  listVendas: (status?: StatusVenda): Promise<VendaResumo[]> =>
    authedJson(status ? `/pdv/vendas?status=${status}` : "/pdv/vendas"),

  /** Acha a venda pelo número do cupom, que é o que o cliente traz no balcão. */
  porNumero: (numero: number): Promise<VendaResumo[]> =>
    authedJson(`/pdv/vendas?numero=${numero}`),

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

  devolucoesDaVenda: (vendaId: string): Promise<DevolucoesDaVenda> =>
    authedJson(`/pdv/vendas/${vendaId}/devolucoes`),

  /* A prévia e a devolução passam pela mesma conta no servidor, então o valor que o
   * operador vê antes é o valor que sai da gaveta depois. */
  preverDevolucao: (
    vendaId: string,
    itens: { venda_item_id: string; quantidade: string; destino: DestinoDevolucao }[],
  ): Promise<PreviaDevolucao> =>
    authedJson(`/pdv/vendas/${vendaId}/devolucoes/previa`, {
      method: "POST",
      body: { itens },
    }),

  devolver: (
    vendaId: string,
    body: {
      itens: { venda_item_id: string; quantidade: string; destino: DestinoDevolucao }[];
      forma: FormaPagamento;
      motivo: string;
    },
  ): Promise<Devolucao> =>
    authedJson(`/pdv/vendas/${vendaId}/devolucoes`, { method: "POST", body }),
};
