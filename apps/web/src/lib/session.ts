/* Guarda da sessão no navegador.
 *
 * O token de acesso fica apenas em memória: ele é curto e, em localStorage, qualquer
 * script injetado na página o leria. O refresh token precisa sobreviver ao recarregar a
 * página, então vai para localStorage — é uma concessão consciente, e a mitigação é ele
 * ser rotativo e revogável no servidor, de modo que o roubo tem validade limitada.
 *
 * A proteção completa exige cookie httpOnly, o que depende de mudança no backend e de
 * tratamento de CSRF. Está registrado no roadmap, não esquecido.
 */

const REFRESH_KEY = "decko.refresh_token";
const TENANT_KEY = "decko.tenant_slug";
const THEME_KEY = "decko.theme";

let accessToken: string | null = null;

/** localStorage lança em janela anônima e com dados de site bloqueados. */
function readLocal(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeLocal(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* sessão sem persistência ainda funciona até o recarregamento */
  }
}

export const session = {
  getAccessToken: (): string | null => accessToken,
  setAccessToken: (token: string | null): void => {
    accessToken = token;
  },

  getRefreshToken: (): string | null => readLocal(REFRESH_KEY),
  setRefreshToken: (token: string | null): void => writeLocal(REFRESH_KEY, token),

  /* O código da empresa é lembrado porque o operador digita sempre o mesmo, todo dia. */
  getTenantSlug: (): string => readLocal(TENANT_KEY) ?? "",
  setTenantSlug: (slug: string): void => writeLocal(TENANT_KEY, slug),

  clear: (): void => {
    accessToken = null;
    writeLocal(REFRESH_KEY, null);
  },
};

export type Theme = "light" | "dark";

/* O tema é escolhido por estação de trabalho, não imposto pela matriz: o caixa do
 * corredor claro e o do depósito escuro têm necessidades diferentes.
 * Ver docs/BRAND.md, seção 3. */
export const theme = {
  get(): Theme {
    return readLocal(THEME_KEY) === "dark" ? "dark" : "light";
  },
  apply(value: Theme): void {
    document.documentElement.setAttribute("data-theme", value);
    writeLocal(THEME_KEY, value);
  },
};
