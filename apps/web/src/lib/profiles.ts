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
}

export const platform = {
  listProfiles: (): Promise<Profile[]> => authedJson("/core/profiles"),

  /** Contrata um segmento inteiro: liga de uma vez os módulos que ele reúne. */
  activateProfile: (name: string): Promise<Module[]> =>
    authedJson(`/core/profiles/${name}/activate`, { method: "POST" }),

  listModules: (): Promise<Module[]> => authedJson("/core/modules"),

  activateModule: (name: string): Promise<Module> =>
    authedJson(`/core/modules/${name}/activate`, { method: "POST" }),
};
