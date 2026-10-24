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
  /** O que precisa estar instalado junto. Instalar já traz, mas a vitrine avisa antes. */
  depends: string[];
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
};
