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
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
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
export interface ProjectItem { project: Project; my_role: Role | null; parties: Party[]; stats: ProjectStats }

export interface Discipline { id: string; code: string; name_ar: string; name_en: string }
export interface InviteOut { link: string; email: string; email_sent: boolean; expires_at: string }
export interface PendingInvite { email: string; expires_at: string }
export interface TeamParty extends Party { can_manage_team: boolean; pending_invite: PendingInvite | null }
export interface Member { id: string; user: User; party_id: string; role: Role; discipline_ids: string[]; is_active: boolean }
export interface Team {
  project: Project; can_manage_project: boolean; my_party_id: string | null; parties: TeamParty[]; members: Member[];
}
export interface OrgMember { user: User; org_role: string }
export interface InvitationInfo {
  kind: 'org_member' | 'project_party'; email: string; status: 'valid' | 'accepted' | 'expired'; user_exists: boolean;
  inviter_name_ar: string; inviter_name_en: string; org: Org | null; project: Project | null;
  party_kind: string | null; party_placeholder: string | null; role: Role | null;
}

/** Download a protected file (the token is in memory, so a plain link cannot carry it). */
export async function openProtected(path: string, filename: string, inline = false) {
  const go = () => fetch(`/api/v1${path}`, { headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {}, credentials: 'include' });
  let r = await go();
  if (r.status === 401 && (await refreshSession())) r = await go();
  if (!r.ok) throw new ApiError(r.status, 'generic');
  const url = URL.createObjectURL(await r.blob());
  if (inline) {
    window.open(url, '_blank');
  } else {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export interface State { id: string; code: string; name_ar: string; name_en: string; category: string; color: string }
export interface RecordType { id: string; code: string; prefix: string; name_ar: string; name_en: string; review_days: number }
export interface RecordMeta { record_type: RecordType; can_create: boolean; disciplines: Discipline[]; party_kind: string | null }
export interface RecordRow {
  id: string; number: string; rev_no: number; title: string; state: State; discipline: Discipline | null;
  submitted_at: string | null; due_at: string | null; answered_at: string | null; overdue: boolean; revisions: number;
}
export interface SubmittalDetails {
  submittal_kind: string | null; item: string | null; manufacturer: string | null; supplier: string | null;
  drawing_ref: string | null; spec_ref: string | null; boq_ref: string | null; quantity: string | number | null; unit: string | null;
}
export interface Transition { action: string; name_ar: string; name_en: string; requires_comment: boolean; style: string; effect: string }
export interface RecordEvent {
  id: number; action: string; to_state: State | null; actor: User; on_behalf_of: User | null; channel: string;
  comment: string | null; stamp: string | null; at: string;
}
export interface RecordComment { id: string; author: User; party_kind: string; visibility: string; body: string; created_at: string }
export interface Attachment { id: string; file_id: string; filename: string; content_type: string; size: number; kind: string; party_kind: string; created_at: string }
export interface RecordDetail {
  id: string; project_id: string; record_type: RecordType; number: string; rev_no: number; title: string;
  description: string | null; discipline: Discipline | null; state: State; from_party_kind: string;
  created_by: User; created_at: string; submitted_by: User | null; submitted_at: string | null; due_at: string | null;
  overdue: boolean; answered_by: User | null; answered_on_behalf_of: User | null; answered_at: string | null;
  response_comment: string | null; details: SubmittalDetails; transitions: Transition[]; can_edit: boolean;
  can_revise: boolean; can_attach: string[]; can_act_on_behalf: boolean; events: RecordEvent[];
  comments: RecordComment[]; attachments: Attachment[]; revisions: { id: string; rev_no: number; state: State }[];
}

export interface ProjectStats { records: number; open: number; overdue: number }
export interface ProjectSettings { review_days: Record<string, number>; can_edit: boolean }
