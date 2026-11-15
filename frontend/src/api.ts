// Access token lives in memory only; the refresh token is an httpOnly cookie the
// browser sends to /api/v1/auth. On a 401 the client refreshes once and retries.

let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;

export class ApiError extends Error {
  constructor(public status: number, public code: string) {
    super(code);
  }
}

export function setAccessToken(token: string | null) {
  accessToken = token;
}

async function doRefresh(): Promise<boolean> {
  const r = await fetch('/api/v1/auth/refresh', { method: 'POST', credentials: 'include' });
  if (!r.ok) {
    accessToken = null;
    return false;
  }
  accessToken = (await r.json()).access_token;
  return true;
}

export function refreshSession(): Promise<boolean> {
  refreshing ??= doRefresh().finally(() => (refreshing = null));
  return refreshing;
}

export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  const r = await fetch(`/api/v1${path}`, { ...init, headers, credentials: 'include' });
  if (r.status === 401 && retry && !path.startsWith('/auth/')) {
    if (await refreshSession()) return api<T>(path, init, false);
  }
  if (!r.ok) {
    let code = 'generic';
    try {
      const body = await r.json();
      if (typeof body.detail === 'string') code = body.detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(r.status, code);
  }
  return (r.status === 204 ? undefined : await r.json()) as T;
}

// ---- types (mirror app/schemas/core.py)
export interface User { id: string; email: string; full_name_ar: string; full_name_en: string; locale: string }
export interface Org { id: string; kind: string; name_ar: string; name_en: string }
export interface Me { user: User; orgs: { org: Org; org_role: string }[] }
export interface Role { id: string; code: string; name_ar: string; name_en: string; party_kind: string }
export interface Party { id: string; kind: string; status: string; org: Org | null; placeholder_name: string | null }
export interface Project {
  id: string; owner_org_id: string; code: string; name_ar: string; name_en: string;
  client_name: string | null; donor_name: string | null; contract_no: string | null;
  description: string | null; start_date: string | null; end_date: string | null;
}
export interface ProjectItem { project: Project; my_role: Role | null; parties: Party[] }
