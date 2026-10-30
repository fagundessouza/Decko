import { authedJson } from "./api";

/** O que a assinatura permite hoje. Vem derivado do servidor, nunca de coluna. */
export type Acesso = "em_dia" | "em_aviso" | "bloqueada";

export type StatusAssinatura = "ativa" | "cancelada";
export type StatusCobranca = "aberta" | "paga" | "cancelada";

export interface Plano {
  id: string;
  nome: string;
  descricao: string | null;
  preco_mensal: string;
  ativo: boolean;
}

export interface Cobranca {
  id: string;
  /** Primeiro dia do mês cobrado. */
  competencia: string;
  valor: string;
  vencimento: string;
  status: StatusCobranca;
  pago_em: string | null;
  forma_pagamento: string | null;
  prazo_ate: string | null;
  prazo_motivo: string | null;
  /** O último dia antes do bloqueio, com o prazo de confiança já somado pelo servidor. */
  bloqueia_em: string;
}

export interface Assinatura {
  id: string;
  cliente_id: string;
  cliente_nome: string;
  plano_id: string;
  plano_nome: string;
  status: StatusAssinatura;
  inicio: string;
  dia_vencimento: number;
  acesso: Acesso;
  em_aberto: string;
  cobrancas: Cobranca[];
}

export const assinaturas = {
  listarPlanos: (): Promise<Plano[]> => authedJson("/assinaturas/planos"),

  criarPlano: (body: {
    nome: string;
    preco_mensal: string;
    descricao?: string | null;
  }): Promise<Plano> => authedJson("/assinaturas/planos", { method: "POST", body }),

  listar: (incluirCanceladas = false): Promise<Assinatura[]> =>
    authedJson(
      `/assinaturas/assinaturas${incluirCanceladas ? "?incluir_canceladas=true" : ""}`,
    ),

  assinar: (body: {
    cliente_id: string;
    plano_id: string;
    inicio: string;
    dia_vencimento: number;
  }): Promise<Assinatura> => authedJson("/assinaturas/assinaturas", { method: "POST", body }),

  cancelar: (assinaturaId: string): Promise<Assinatura> =>
    authedJson(`/assinaturas/assinaturas/${assinaturaId}/cancelar`, { method: "POST" }),

  /** Gera a cobrança do mês para cada assinatura ativa. Repetir não cobra de novo. */
  gerar: (ano: number, mes: number): Promise<{ competencia: string; criadas: number }> =>
    authedJson("/assinaturas/cobrancas/gerar", { method: "POST", body: { ano, mes } }),

  baixar: (
    cobrancaId: string,
    body: { pago_em: string; forma_pagamento?: string | null },
  ): Promise<Assinatura> =>
    authedJson(`/assinaturas/cobrancas/${cobrancaId}/baixar`, { method: "POST", body }),

  /** Dá mais tempo antes de bloquear. Ato de gente: exige motivo, e fica na trilha. */
  concederPrazo: (
    cobrancaId: string,
    body: { ate: string; motivo: string },
  ): Promise<Assinatura> =>
    authedJson(`/assinaturas/cobrancas/${cobrancaId}/prazo`, { method: "POST", body }),
};
