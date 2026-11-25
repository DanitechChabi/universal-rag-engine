// Client de l'API (ADR-0023) : même origine, session par cookies HttpOnly uniquement.
// Le code ne lit ni ne stocke jamais de jeton ; seul le jeton anti-CSRF (cookie lisible) est
// renvoyé en en-tête sur les requêtes qui modifient.

export const API = "/api/v1";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    title: string,
  ) {
    super(title);
  }
}

export class Unauthenticated extends ApiError {
  constructor() {
    super(401, "auth.required", "Session expirée");
  }
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)urag_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

let refreshing: Promise<boolean> | null = null;

async function refresh(): Promise<boolean> {
  // Une seule tentative à la fois, partagée par les requêtes concurrentes.
  refreshing ??= fetch(`${API}/auth/refresh`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": csrfToken() },
  })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

export async function raw(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (method !== "GET" && method !== "HEAD") headers.set("X-CSRF-Token", csrfToken());
  if (init.body && typeof init.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API}${path}`, { ...init, headers, credentials: "same-origin" });
  if (response.status === 401 && retry && !path.startsWith("/auth/")) {
    if (await refresh()) return raw(path, init, false);
    throw new Unauthenticated();
  }
  if (!response.ok) {
    let code = "error";
    let title = response.statusText;
    try {
      const body = await response.json();
      code = body.code ?? code;
      title = body.title ?? title;
    } catch {
      // réponse sans corps JSON
    }
    if (response.status === 401) throw new Unauthenticated();
    throw new ApiError(response.status, code, title);
  }
  return response;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await raw(path, init);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const put = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "PUT", body: body === undefined ? undefined : JSON.stringify(body) });

export const del = <T>(path: string) => api<T>(path, { method: "DELETE" });

export type Me = {
  user_id: string;
  login: string;
  display_name: string;
  organization: string;
  roles: string[];
  ai_mode: string;
};
