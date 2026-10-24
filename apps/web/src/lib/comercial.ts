import { authedJson } from "./api";

export interface Unidade {
  id: string;
  nome: string;
  simbolo: string | null;
  referencia_id: string | null;
  fator_relativo: string;
  /** Quanto vale em relação à raiz: o fardo de 10 caixas de 12 mostra 120. */
  fator: string;
}

export interface Categoria {
  id: string;
  nome: string;
  pai_id: string | null;
}

export interface Produto {
  id: string;
  codigo: string;
  nome: string;
  descricao: string | null;
  gtin: string | null;
  categoria_id: string | null;
  unidade_id: string;
  preco_custo: string | null;
  preco_venda: string | null;
  controla_lote: boolean;
  controla_validade: boolean;
  ativo: boolean;
}

export interface Lote {
  id: string;
  produto_id: string;
  codigo: string;
  validade: string | null;
  fabricacao: string | null;
}

export type TipoMovimento = "entrada" | "saida" | "ajuste";

export interface Movimento {
  id: string;
  produto_id: string;
  lote_id: string | null;
  tipo: TipoMovimento;
  /** Já na unidade base do produto. */
  quantidade: string;
  /** O que foi efetivamente digitado — 10 fardos, por exemplo. */
  quantidade_digitada: string;
  unidade_id: string;
  documento: string | null;
  motivo: string | null;
  ocorrido_em: string;
}

export interface SaldoLote {
  lote_id: string | null;
  codigo: string | null;
  validade: string | null;
  quantidade: string;
}

export interface Saldo {
  produto_id: string;
  unidade_id: string;
  quantidade: string;
  por_lote: SaldoLote[];
}

export const comercial = {
  listUnidades: (): Promise<Unidade[]> => authedJson("/comercial/unidades"),

  createUnidade: (body: {
    nome: string;
    simbolo?: string | null;
    referencia_id?: string | null;
    fator_relativo?: number;
  }): Promise<Unidade> => authedJson("/comercial/unidades", { method: "POST", body }),

  listCategorias: (): Promise<Categoria[]> => authedJson("/comercial/categorias"),

  createCategoria: (body: { nome: string; pai_id?: string | null }): Promise<Categoria> =>
    authedJson("/comercial/categorias", { method: "POST", body }),

  /** Sem `busca`, traz o começo do catálogo; com, filtra no banco (código, GTIN ou nome). */
  listProdutos: (busca?: string): Promise<Produto[]> =>
    authedJson(
      busca && busca.trim() !== ""
        ? `/comercial/produtos?busca=${encodeURIComponent(busca.trim())}`
        : "/comercial/produtos",
    ),

  createProduto: (body: Record<string, unknown>): Promise<Produto> =>
    authedJson("/comercial/produtos", { method: "POST", body }),

  listLotes: (produtoId: string): Promise<Lote[]> =>
    authedJson(`/comercial/lotes?produto_id=${produtoId}`),

  createLote: (body: {
    produto_id: string;
    codigo: string;
    validade?: string | null;
    fabricacao?: string | null;
  }): Promise<Lote> => authedJson("/comercial/lotes", { method: "POST", body }),

  saldo: (produtoId: string): Promise<Saldo> =>
    authedJson(`/comercial/produtos/${produtoId}/saldo`),

  movimentos: (produtoId: string): Promise<Movimento[]> =>
    authedJson(`/comercial/produtos/${produtoId}/movimentos`),

  movimentar: (body: {
    produto_id: string;
    tipo: TipoMovimento;
    quantidade: number;
    unidade_id: string;
    lote_id?: string | null;
    documento?: string | null;
    motivo?: string | null;
  }): Promise<Movimento> => authedJson("/comercial/movimentos", { method: "POST", body }),
};

/** Descreve a embalagem como o lojista a lê: "Caixa (12 un)". */
export function describeUnidade(unidade: Unidade, raiz?: Unidade): string {
  const fator = Number(unidade.fator);
  if (fator === 1) return unidade.nome;
  const base = raiz?.simbolo ?? raiz?.nome ?? "un";
  return `${unidade.nome} (${fator} ${base})`;
}
