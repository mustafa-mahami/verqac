/** Time programme: planned start / finish of each stage x location cell. */
export interface PLine { stage_id: string; location_id: string | null; start: string; finish: string }
export interface PCycle { stage_id: string; start: string | null; duration: number; lag: number }
export interface ProgrammeOut { lines: PLine[]; cycles: PCycle[]; source: 'manual' | 'cycle' | 'import'; can_edit: boolean; start: string | null; finish: string | null }
export interface ImportRow { name: string; location: string | null; path: string[]; start: string | null; finish: string | null; stage_id: string | null; location_id: string | null }
export interface ProgrammeRev { id: string; number: string; rev_no: number; state_category: string; state_name_ar: string; state_name_en: string }
export interface ProgrammeSummary { revisions: ProgrammeRev[]; baseline_id: string | null; current_id: string | null; can_create: boolean }

const DAY = 86_400_000;
export const addDays = (iso: string, n: number) => new Date(new Date(`${iso}T00:00:00Z`).getTime() + n * DAY).toISOString().slice(0, 10);
export const daysBetween = (a: string, b: string) => Math.round((new Date(`${b}T00:00:00Z`).getTime() - new Date(`${a}T00:00:00Z`).getTime()) / DAY);
export const cellKey = (stage: string, loc: string | null) => `${stage}:${loc ?? ''}`;
