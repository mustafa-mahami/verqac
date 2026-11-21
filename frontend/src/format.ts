import i18n from './i18n';

/** Dates with Latin digits in both languages (engineering documents use them). */
/** One page width everywhere: moving between tabs and pages, the content keeps its edges (wide tables scroll inside). */
export const PAGE_WIDTH = 1440;

export function fmtDate(iso: string | null | undefined, withTime = false): string {
  if (!iso) return '';
  const d = new Date(iso);
  const locale = i18n.language === 'en' ? 'en-GB' : 'ar-PS-u-nu-latn';
  return d.toLocaleString(locale, withTime
    ? { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }
    : { year: 'numeric', month: '2-digit', day: '2-digit' });
}

export function fmtSize(n: number): string {
  return n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/** Workflow state colours (stored on the state) to Mantine colours. */
export const stateColor = (c: string) => ({ dark: 'dark', gray: 'gray', blue: 'blue', green: 'green', teal: 'teal', orange: 'orange', red: 'red' } as Record<string, string>)[c] ?? 'gray';

/** Whole days from today to a date-only value (YYYY-MM-DD); negative when it has passed. */
export function daysUntil(day: string): number {
  const [y, m, d] = day.split('-').map(Number);
  const now = new Date();
  return Math.round((Date.UTC(y, m - 1, d) - Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
}

/** Colour of an "answer needed by" date while the record is open. */
export const requiredColor = (day: string) => { const n = daysUntil(day); return n < 0 ? 'red' : n <= 7 ? 'orange' : 'blue'; };
