import { authedJson } from "./api";

/** O que um centro custou no período, pelas duas fontes.
 *
 * Este é o número que responde "quanto custou a lavoura": o que saiu do estoque mais o
 * que foi pago em despesa. Ver docs/adr/0026-consumo-interno-e-custo-por-centro.md. */
export interface CustoDoCentro {
  centro_id: string;
  nome: string;
  consumo: string;
  despesa: string;
  total: string;
}

export interface Consumo {
  id: string;
  centro_custo_id: string;
  centro_nome: string;
  produto_nome: string;
  quantidade: string;
  valor: string;
  custo_unitario: string | null;
  ocorrido_em: string;
  observacao: string | null;
}

export const custos = {
  porCentro: (de: string, ate: string): Promise<CustoDoCentro[]> =>
    authedJson(`/custos/por-centro?de=${de}&ate=${ate}`),

  listarConsumos: (de: string, ate: string): Promise<Consumo[]> =>
    authedJson(`/custos/consumos?de=${de}&ate=${ate}`),
};
