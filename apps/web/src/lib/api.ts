import { session } from "./session";

// Prefixo da API, não de um módulo: cada módulo é montado sob o próprio nome.
const BASE = "/api/v1";
const CORE = `${BASE}/core`;

export interface Credentials {
  tenantSlug: string;
  email: string;
  password: string;
}

export interface UserSummary {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  last_login_at: string | null;
}

export interface TenantSummary {
  id: string;
  name: string;
  slug: string;
}

export interface TenantProfile {
  id: string;
  name: string;
  slug: string;
  cnpj: string | null;
  registro_mapa: string | null;
  crea: string | null;
  cda: string | null;
  inscricao_estadual: string | null;
  inscricao_municipal: string | null;
  rodape: string | null;
}

export interface SessionInfo {
  user: UserSummary;
  tenant: TenantSummary;
  permissions: string[];
}

interface TokenPayload {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/** Extrai a mensagem do corpo de erro do FastAPI, que varia entre 401 e 422. */
async function messageFrom(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail) && body.detail[0]?.msg) return body.detail[0].msg;
  } catch {
    /* resposta sem JSON */
  }
  return fallback;
}

function storeTokens(payload: TokenPayload): void {
  session.setAccessToken(payload.access_token);
  session.setRefreshToken(payload.refresh_token);
}

export async function login(credentials: Credentials): Promise<SessionInfo> {
  const response = await fetch(`${CORE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      tenant_slug: credentials.tenantSlug.trim().toLowerCase(),
      email: credentials.email.trim(),
      password: credentials.password,
    }),
  });

  if (!response.ok) {
    throw new ApiError(
      await messageFrom(response, "Não foi possível entrar. Tente novamente."),
      response.status,
    );
  }

  storeTokens(await response.json());
  session.setTenantSlug(credentials.tenantSlug.trim().toLowerCase());
  return fetchSession();
}

async function requestNewTokens(): Promise<boolean> {
  const token = session.getRefreshToken();
  if (!token) return false;

  const response = await fetch(`${CORE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: token }),
  });

  if (!response.ok) {
    session.clear();
    return false;
  }

  storeTokens(await response.json());
  return true;
}

/* Renovação em voo único: quem chegar enquanto uma está em curso espera a mesma. */
let renovando: Promise<boolean> | null = null;

/** Troca o refresh token por um novo par. Devolve false quando a sessão não vale mais.
 *
 * O refresh token é rotativo: usá-lo invalida o anterior. Duas renovações simultâneas
 * levavam o mesmo token, e a segunda recebia 401 por ele já ter sido consumido — caindo
 * no `session.clear()` abaixo, que apagava o par recém-emitido e derrubava uma sessão
 * perfeitamente válida.
 *
 * Não é hipótese: uma tela que carrega várias listas em paralelo faz todas expirarem
 * juntas e renovarem juntas. No campo, isso é o operador sendo deslogado no meio da
 * aplicação. Compartilhar a chamada em curso faz as concorrentes esperarem o mesmo
 * resultado, e só um token é consumido.
 */
function refresh(): Promise<boolean> {
  renovando ??= requestNewTokens().finally(() => {
    renovando = null;
  });
  return renovando;
}

/** Faz a chamada e, em caso de token expirado, renova uma vez e repete. */
async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const call = (): Promise<Response> =>
    fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        ...init.headers,
        Authorization: `Bearer ${session.getAccessToken() ?? ""}`,
      },
    });

  const response = await call();
  if (response.status !== 401) return response;

  // Uma única tentativa: repetir em laço transformaria sessão expirada em loop infinito.
  if (!(await refresh())) return response;
  return call();
}

/** Chamada autenticada para qualquer módulo, com renovação automática do token. */
export async function authedRequest(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<Response> {
  const init: RequestInit = { method: options.method ?? "GET" };
  if (options.body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(options.body);
  }

  const response = await authedFetch(path, init);
  if (!response.ok) {
    throw new ApiError(
      await messageFrom(response, "Não foi possível completar a operação."),
      response.status,
    );
  }
  return response;
}

export async function authedJson<T>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const response = await authedRequest(path, options);
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export async function fetchSession(): Promise<SessionInfo> {
  const response = await authedFetch("/core/auth/me");
  if (!response.ok) {
    throw new ApiError(await messageFrom(response, "Sessão expirada."), response.status);
  }
  return response.json();
}

/** Restaura a sessão ao abrir a página, quando existe refresh token guardado. */
export async function restoreSession(): Promise<SessionInfo | null> {
  if (!session.getRefreshToken()) return null;
  if (!(await refresh())) return null;
  try {
    return await fetchSession();
  } catch {
    session.clear();
    return null;
  }
}

export async function logout(): Promise<void> {
  const token = session.getRefreshToken();
  if (token) {
    // O servidor precisa saber da saída para revogar o token; falha de rede não pode
    // impedir a limpeza local, então o erro é ignorado de propósito.
    await fetch(`${CORE}/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: token }),
    }).catch(() => undefined);
  }
  session.clear();
}

/** Identificação da empresa: é o que o Planejamento Operacional imprime no cabeçalho. */
export const tenant = {
  read: (): Promise<TenantProfile> => authedJson("/core/tenant"),

  save: (body: Omit<TenantProfile, "id" | "slug">): Promise<TenantProfile> =>
    authedJson("/core/tenant", { method: "PUT", body }),
};
