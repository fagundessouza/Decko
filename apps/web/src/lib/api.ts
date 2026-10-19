import { session } from "./session";

const BASE = "/api/v1/core";

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
  const response = await fetch(`${BASE}/auth/login`, {
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

/** Troca o refresh token por um novo par. Devolve false quando a sessão não vale mais. */
async function refresh(): Promise<boolean> {
  const token = session.getRefreshToken();
  if (!token) return false;

  const response = await fetch(`${BASE}/auth/refresh`, {
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

export async function fetchSession(): Promise<SessionInfo> {
  const response = await authedFetch("/auth/me");
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
    await fetch(`${BASE}/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: token }),
    }).catch(() => undefined);
  }
  session.clear();
}
