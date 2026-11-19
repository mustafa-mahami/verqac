// The list a record was opened from (its order, filters and sort), so the record page can step to the
// previous / next record and go back to the same view, as in Odoo. Kept per browser tab.
const KEY = 'verqac:record-nav';

export interface RecordNav { ids: string[]; back: string }

export function saveNav(ids: string[], back: string): void {
  try { sessionStorage.setItem(KEY, JSON.stringify({ ids, back })); } catch { /* private mode: no pager */ }
}

export function loadNav(id: string): (RecordNav & { index: number }) | null {
  try {
    const v = JSON.parse(sessionStorage.getItem(KEY) ?? 'null') as RecordNav | null;
    const index = v?.ids.indexOf(id) ?? -1;
    return v && index >= 0 ? { ...v, index } : null;
  } catch {
    return null;
  }
}
