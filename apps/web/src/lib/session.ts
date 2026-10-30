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
const RECIBO_KEY = "decko.recibo_largura";
const COMPANIES_KEY = "decko.companies";

/* Quantas empresas o seletor lembra. Computador de balcão passa por muita gente; guardar
 * para sempre toda empresa que já entrou ali vira um histórico que ninguém pediu. */
const LIMITE_DE_EMPRESAS = 8;

/** Uma empresa já usada **neste aparelho**. Não é "as suas empresas" — ver ADR 0012. */
export interface KnownCompany {
  slug: string;
  name: string;
}

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

  /* As empresas que já entraram neste navegador, da mais recente para a mais antiga.
   *
   * Fica no aparelho porque **não há rota que responda isso**, e de propósito: perguntar
   * ao servidor em quais empresas um e-mail tem conta exigiria atravessar o isolamento com
   * privilégio, e devolveria um oráculo de enumeração. Ver ADR 0012, decisão 1. */
  getCompanies: (): KnownCompany[] => {
    const bruto = readLocal(COMPANIES_KEY);
    if (!bruto) return [];
    try {
      const lido: unknown = JSON.parse(bruto);
      if (!Array.isArray(lido)) return [];
      return lido.filter(
        (item): item is KnownCompany =>
          typeof item === "object" &&
          item !== null &&
          typeof (item as KnownCompany).slug === "string" &&
          typeof (item as KnownCompany).name === "string",
      );
    } catch {
      // Conteúdo corrompido é lista vazia, nunca uma tela quebrada.
      return [];
    }
  },

  rememberCompany: (empresa: KnownCompany): void => {
    const atuais = session.getCompanies().filter((item) => item.slug !== empresa.slug);
    const proximas = [empresa, ...atuais].slice(0, LIMITE_DE_EMPRESAS);
    writeLocal(COMPANIES_KEY, JSON.stringify(proximas));
  },

  forgetCompany: (slug: string): void => {
    const restantes = session.getCompanies().filter((item) => item.slug !== slug);
    writeLocal(COMPANIES_KEY, restantes.length === 0 ? null : JSON.stringify(restantes));
  },

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


/** Largura do papel da impressora térmica. 58 e 80 mm são as duas do balcão. */
export type LarguraDoRecibo = "58mm" | "80mm";

/* Escolhida **por estação**, como o tema e pela mesma razão: a impressora é do balcão, não
 * da matriz, e duas lojas da mesma empresa podem ter papel diferente.
 * Ver docs/BRAND.md, seção 3. */
export const recibo = {
  getLargura(): LarguraDoRecibo {
    return readLocal(RECIBO_KEY) === "58mm" ? "58mm" : "80mm";
  },
  setLargura(largura: LarguraDoRecibo): void {
    writeLocal(RECIBO_KEY, largura);
    document.documentElement.style.setProperty("--dk-recibo-largura", largura);
  },
  aplicar(): void {
    document.documentElement.style.setProperty("--dk-recibo-largura", recibo.getLargura());
  },
};
