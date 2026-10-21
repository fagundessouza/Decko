import { authedJson, authedRequest } from "./api";

export interface AgroClient {
  id: string;
  nome: string;
  cpf_cnpj: string;
}

export interface AgroProperty {
  id: string;
  client_id: string;
  nome: string;
  municipio: string;
  uf: string;
  latitude: string | null;
  longitude: string | null;
}

export interface Product {
  id: string;
  nome_comercial: string;
  formulacao: string | null;
  classe_toxicologica: string | null;
  registro_mapa: string | null;
  is_adjuvante: boolean;
}

export interface Prescription {
  id: string;
  numero: string;
  emitido_em: string;
  agronomo_nome: string | null;
  agronomo_crea: string | null;
}

/** Linha da tabela de produtos do planejamento.
 *
 * `formulacao` e `classe_toxicologica` são a cópia feita quando a linha entrou, não o
 * valor atual do cadastro: um documento já emitido não muda de conteúdo.
 */
export interface PlanProduct {
  id: string;
  product_id: string;
  formulacao: string | null;
  classe_toxicologica: string | null;
  dosagem_ha: string | null;
  volume_ha: string | null;
  total_produto: string | null;
  adjuvante: string | null;
}

export interface ConsolidationPlan {
  id: string;
  numero: number;
  status: string;
  data_aplicacao: string | null;
  contratante: string;
  contratante_documento: string;
  propriedade: string;
  municipio: string;
  uf: string;
  cultura: string;
  area_ha: string | null;
  aeronave: string;
  produtos: string[];
  leituras: number;
  violacoes: number;
}

export interface Consolidation {
  ano: number;
  mes: number;
  quantidade: number;
  area_total_ha: string;
  planos_com_violacao: number;
  planos_sem_data: number;
  totais_por_produto: { produto: string; total: string }[];
  planos: ConsolidationPlan[];
}

export interface Plan {
  id: string;
  numero: number;
  status: string;
  client_id: string;
  property_id: string;
  prescription_id: string | null;
  data_aplicacao: string | null;
  cultura: string | null;
  area_ha: string | null;
  param_temperatura_maxima_c: string | null;
  param_umidade_relativa_min_pct: string | null;
  param_velocidade_vento_max_kmh: string | null;
}

export interface WeatherReading {
  id: string;
  data: string;
  periodo: "matutino" | "vespertino";
  momento: "inicio" | "final";
  hora: string | null;
  temperatura_c: string | null;
  umidade_relativa_pct: string | null;
  velocidade_vento_kmh: string | null;
  provider: string | null;
  violou_parametro: boolean;
}

export interface WeatherCapture {
  leitura: WeatherReading;
  alertas: string[];
}

export const agro = {
  listClients: (): Promise<AgroClient[]> => authedJson("/agro/clients"),

  createClient: (body: {
    nome: string;
    cpf_cnpj: string;
    telefone?: string | null;
    email?: string | null;
  }): Promise<AgroClient> => authedJson("/agro/clients", { method: "POST", body }),

  listProperties: (): Promise<AgroProperty[]> => authedJson("/agro/properties"),

  createProperty: (body: {
    client_id: string;
    nome: string;
    municipio: string;
    uf: string;
    latitude?: number | null;
    longitude?: number | null;
  }): Promise<AgroProperty> => authedJson("/agro/properties", { method: "POST", body }),

  listProducts: (): Promise<Product[]> => authedJson("/agro/products"),

  createProduct: (body: {
    nome_comercial: string;
    formulacao?: string | null;
    classe_toxicologica?: string | null;
    registro_mapa?: string | null;
  }): Promise<Product> => authedJson("/agro/products", { method: "POST", body }),

  listPrescriptions: (): Promise<Prescription[]> => authedJson("/agro/prescriptions"),

  createPrescription: (body: {
    numero: string;
    emitido_em: string;
    agronomo_nome?: string | null;
    agronomo_crea?: string | null;
  }): Promise<Prescription> => authedJson("/agro/prescriptions", { method: "POST", body }),

  listPlanProducts: (planId: string): Promise<PlanProduct[]> =>
    authedJson(`/agro/plans/${planId}/products`),

  addPlanProduct: (
    planId: string,
    body: {
      product_id: string;
      dosagem_ha?: number | null;
      volume_ha?: number | null;
      total_produto?: number | null;
      adjuvante?: string | null;
    },
  ): Promise<PlanProduct> =>
    authedJson(`/agro/plans/${planId}/products`, { method: "POST", body }),

  removePlanProduct: async (planId: string, itemId: string): Promise<void> => {
    await authedRequest(`/agro/plans/${planId}/products/${itemId}`, { method: "DELETE" });
  },

  linkPrescription: (planId: string, prescriptionId: string | null): Promise<Plan> =>
    authedJson(`/agro/plans/${planId}/prescription`, {
      method: "PUT",
      body: { prescription_id: prescriptionId },
    }),

  consolidation: (ano: number, mes: number): Promise<Consolidation> =>
    authedJson(`/agro/consolidation/${ano}/${mes}`),

  /** CSV baixado como blob porque a rota exige o cabeçalho de autenticação. */
  downloadConsolidation: async (ano: number, mes: number): Promise<void> => {
    const response = await authedRequest(`/agro/consolidation/${ano}/${mes}/csv`);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `consolidacao-${ano}-${String(mes).padStart(2, "0")}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  },

  listPlans: (): Promise<Plan[]> => authedJson("/agro/plans"),

  createPlan: (body: Record<string, unknown>): Promise<Plan> =>
    authedJson("/agro/plans", { method: "POST", body }),

  listWeather: (planId: string): Promise<WeatherReading[]> =>
    authedJson(`/agro/plans/${planId}/weather`),

  captureWeather: (
    planId: string,
    body: {
      data: string;
      periodo: string;
      momento: string;
      hora: string;
      latitude?: number;
      longitude?: number;
    },
  ): Promise<WeatherCapture> =>
    authedJson(`/agro/plans/${planId}/weather`, { method: "POST", body }),

  /** O PDF é baixado como blob porque a rota exige o cabeçalho de autenticação. */
  downloadPdf: async (planId: string, numero: number): Promise<void> => {
    const response = await authedRequest(`/agro/plans/${planId}/pdf`);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `planejamento-operacional-${numero}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
  },
};

/** Posição do aparelho, que é o que diz onde o voo realmente aconteceu. */
export function currentPosition(): Promise<{ latitude: number; longitude: number }> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("Este aparelho não informa a localização."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) =>
        resolve({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        }),
      (error) =>
        reject(
          new Error(
            error.code === error.PERMISSION_DENIED
              ? "Permissão de localização negada. Libere o acesso ou informe a área manualmente."
              : "Não foi possível obter a localização agora.",
          ),
        ),
      // O campo costuma ter sinal fraco; vale esperar um pouco por uma posição boa.
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
    );
  });
}
