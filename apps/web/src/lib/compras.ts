import { authedJson } from "./api";

export type StatusNota = "rascunho" | "confirmada" | "descartada";

/** Por que o item ficou ligado àquele produto. A tela mostra isso ao lojista. */
export type OrigemVinculo = "gtin" | "fornecedor" | "manual" | "novo";

export type OrigemSugestao = "gtin" | "fornecedor" | "semelhanca";

export interface Candidato {
  produto_id: string;
  nome: string;
  origem: OrigemSugestao;
  pontuacao: number;
  /** Falso para palpite de nome: ele sugere, mas não liga sozinho. */
  automatico: boolean;
}

export interface NotaItem {
  id: string;
  numero_item: number;
  /** Como o fornecedor escreveu. */
  codigo_fornecedor: string;
  descricao: string;
  gtin: string | null;
  ncm: string | null;
  cest: string | null;
  unidade_comercial: string | null;
  quantidade: string;
  valor_unitario: string;
  valor_total: string;
  /** O destino, quando já decidido. */
  produto_id: string | null;
  origem_vinculo: OrigemVinculo | null;
  unidade_id: string | null;
  sugestoes: Candidato[];
}

export interface NotaResumo {
  id: string;
  chave: string;
  numero: string | null;
  serie: string | null;
  emitente_cnpj: string;
  emitente_nome: string | null;
  emitida_em: string | null;
  valor_total: string;
  status: StatusNota;
}

export interface Nota extends NotaResumo {
  itens: NotaItem[];
  /** Quantos itens ainda esperam decisão. A nota não fecha com algum aqui. */
  pendentes: number;
}

export interface Confirmacao {
  nota: NotaResumo;
  produtos_criados: number;
  itens_lancados: number;
}

export const compras = {
  listNotas: (status?: StatusNota): Promise<NotaResumo[]> =>
    authedJson(status ? `/compras/notas?status=${status}` : "/compras/notas"),

  /** O navegador lê o arquivo escolhido e manda o texto. */
  importar: (xml: string): Promise<Nota> =>
    authedJson("/compras/notas", { method: "POST", body: { xml } }),

  ver: (notaId: string): Promise<Nota> => authedJson(`/compras/notas/${notaId}`),

  vincular: (
    notaId: string,
    itemId: string,
    body: { produto_id: string; unidade_id?: string | null },
  ): Promise<Nota> =>
    authedJson(`/compras/notas/${notaId}/itens/${itemId}/produto`, { method: "PUT", body }),

  marcarComoNovo: (notaId: string, itemId: string, unidadeId: string): Promise<Nota> =>
    authedJson(`/compras/notas/${notaId}/itens/${itemId}/novo`, {
      method: "PUT",
      body: { unidade_id: unidadeId },
    }),

  confirmar: (notaId: string): Promise<Confirmacao> =>
    authedJson(`/compras/notas/${notaId}/confirmar`, { method: "POST" }),

  descartar: (notaId: string): Promise<NotaResumo> =>
    authedJson(`/compras/notas/${notaId}/descartar`, { method: "POST" }),
};

/** O texto que explica ao lojista por que o item foi reconhecido. */
export function explicarVinculo(origem: OrigemVinculo | null): string {
  switch (origem) {
    case "gtin":
      return "Reconhecido pelo código de barras";
    case "fornecedor":
      return "Reconhecido pelo código deste fornecedor";
    case "manual":
      return "Você escolheu este produto";
    case "novo":
      return "Vai ser cadastrado como produto novo";
    default:
      return "";
  }
}
