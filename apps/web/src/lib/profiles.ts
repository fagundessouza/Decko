import { authedJson } from "./api";

export interface Profile {
  name: string;
  label: string;
  description: string;
  modules: string[];
  active: boolean;
}

export interface Module {
  name: string;
  label: string;
  version: string;
  required: boolean;
  active: boolean;
  /** Como o módulo aparece na vitrine. Vem do manifesto, não de uma lista na interface. */
  category: string;
  summary: string;
  icon: string;
  /** Cor de identidade do módulo. Nome do papel; o valor mora nos tokens. */
  accent: string;
  /** O que precisa estar instalado junto. Instalar já traz, mas a vitrine avisa antes. */
  depends: string[];
  /** Se o módulo traz itens iniciais. Quem o instalou antes de a semente existir não os
   *  tem, e pede aqui. */
  has_seed: boolean;
}

/** O que a carga de itens iniciais acrescentou nesta empresa. */
export interface SeedResult {
  module: string;
  created: string[];
}

/** Uma linha da trilha de auditoria. `action` vem como o servidor a gravou. */
export interface AuditEntry {
  id: string;
  action: string;
  entity: string;
  entity_id: string | null;
  data: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
  user_id: string | null;
  /** Nulo quando a ação não teve autor, ou quando o usuário foi removido depois. */
  author: string | null;
}

export interface AuditPage {
  total: number;
  entries: AuditEntry[];
}

export const platform = {
  listProfiles: (): Promise<Profile[]> => authedJson("/core/profiles"),

  /** Contrata um segmento inteiro: liga de uma vez os módulos que ele reúne. */
  activateProfile: (name: string): Promise<Module[]> =>
    authedJson(`/core/profiles/${name}/activate`, { method: "POST" }),

  listModules: (): Promise<Module[]> => authedJson("/core/modules"),

  /** Instala o módulo e o que ele precisa. Devolve tudo o que passou a existir. */
  activateModule: (name: string): Promise<Module[]> =>
    authedJson(`/core/modules/${name}/activate`, { method: "POST" }),

  deactivateModule: (name: string): Promise<Module> =>
    authedJson(`/core/modules/${name}/activate`, { method: "DELETE" }),

  /** Traz os itens iniciais do módulo. Repetir não duplica nem recria o que foi apagado. */
  seedModule: (name: string): Promise<SeedResult> =>
    authedJson(`/core/modules/${name}/seed`, { method: "POST" }),

  /** A trilha de auditoria da empresa, da mais recente para a mais antiga. */
  readAudit: (params: { prefixo?: string; limit?: number; offset?: number } = {}) => {
    const busca = new URLSearchParams();
    if (params.prefixo) busca.set("action_prefix", params.prefixo);
    busca.set("limit", String(params.limit ?? 50));
    busca.set("offset", String(params.offset ?? 0));
    return authedJson(`/core/audit?${busca.toString()}`) as Promise<AuditPage>;
  },
};
