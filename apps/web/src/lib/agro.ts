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

export interface Plan {
  id: string;
  numero: number;
  status: string;
  client_id: string;
  property_id: string;
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

  createClient: (body: { nome: string; cpf_cnpj: string }): Promise<AgroClient> =>
    authedJson("/agro/clients", { method: "POST", body }),

  listProperties: (): Promise<AgroProperty[]> => authedJson("/agro/properties"),

  createProperty: (body: {
    client_id: string;
    nome: string;
    municipio: string;
    uf: string;
    latitude?: number | null;
    longitude?: number | null;
  }): Promise<AgroProperty> => authedJson("/agro/properties", { method: "POST", body }),

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
