/** Time programme: planned start / finish of each stage x location cell. */
export interface PLine { stage_id: string; location_id: string | null; start: string; finish: string }
export type Link = 'fs' | 'ss';
export type Rel = 'after_end' | 'after_start' | 'before_end' | 'before_start';
export interface PCycle {
  stage_id: string; start: string | null; duration: number; lag: number; link?: Link;
  pred?: string | null; rel?: Rel; pred_days?: number; // optional: starts relative to an earlier stage, floor by floor
}
/** Start of floor i (calendar days). "fs": lag = idle days between floors (0 = the day after the floor below ends);
 * "ss": lag = days after the floor below starts (overlapping trades). */
export const floorStart = (c: PCycle, i: number) => addDays(c.start!, i * ((c.link ?? 'fs') === 'fs' ? c.duration + c.lag : c.lag));
export interface ProgrammeOut { lines: PLine[]; cycles: PCycle[]; source: 'manual' | 'cycle' | 'import'; can_edit: boolean; start: string | null; finish: string | null }
export interface ImportRow { name: string; location: string | null; path: string[]; start: string | null; finish: string | null; stage_id: string | null; location_id: string | null }
export interface ProgrammeRev { id: string; number: string; rev_no: number; state_category: string; state_name_ar: string; state_name_en: string }
export interface ProgrammeSummary { revisions: ProgrammeRev[]; baseline_id: string | null; current_id: string | null; can_create: boolean }

const DAY = 86_400_000;
export const addDays = (iso: string, n: number) => new Date(new Date(`${iso}T00:00:00Z`).getTime() + n * DAY).toISOString().slice(0, 10);
export const daysBetween = (a: string, b: string) => Math.round((new Date(`${b}T00:00:00Z`).getTime() - new Date(`${a}T00:00:00Z`).getTime()) / DAY);
export const cellKey = (stage: string, loc: string | null) => `${stage}:${loc ?? ''}`;

const lt = (a: string, b: string) => (a < b ? a : b);
const gt = (a: string, b: string) => (a > b ? a : b);

/** Start from the predecessor's dates ("after its end by 3 days" ...). */
const anchor = (c: PCycle, p: { start: string; finish: string }) => {
  const d = c.pred_days ?? 0;
  switch (c.rel ?? 'after_end') {
    case 'after_start': return addDays(p.start, d);
    case 'before_start': return addDays(p.start, -d);
    case 'before_end': return addDays(p.finish, -d);
    default: return addDays(p.finish, d + 1); // as in MS Project: 0 = the day after it ends
  }
};

/** Dates of every stage in the cycle, in dependency order. A linked stage starts from its predecessor on the same
 * floor, but its crew never starts a floor before its own cycle allows (the later of the two wins). A predecessor
 * outside the cycle is read from the lines already entered. */
export function schedule(cs: PCycle[], units: string[], whole: Set<string>, existing: PLine[]): { lines: PLine[]; error: string | null; missing: string[] } {
  const by = new Map(cs.map((c) => [c.stage_id, c]));
  const done = new Map<string, PLine[]>();
  for (const l of existing) if (!by.has(l.stage_id)) done.set(l.stage_id, [...(done.get(l.stage_id) ?? []), l]);
  const missing: string[] = [];
  const visiting = new Set<string>();
  const span = (ls: PLine[]) => ({ start: ls.map((l) => l.start).reduce(lt), finish: ls.map((l) => l.finish).reduce(gt) });
  const run = (id: string): PLine[] | null => {
    if (done.has(id)) return done.get(id)!;
    const c = by.get(id);
    if (!c) return null;
    if (visiting.has(id)) throw new Error('programme_cycle_loop');
    visiting.add(id);
    const pl = c.pred ? run(c.pred) : null;
    if (c.pred && !pl?.length) missing.push(id);
    const predWhole = !!c.pred && whole.has(c.pred);
    const out: PLine[] = [];
    if (whole.has(id) || !units.length) {
      const st = pl?.length ? anchor(c, span(pl)) : c.start;
      if (st) out.push({ stage_id: id, location_id: null, start: st, finish: addDays(st, c.duration - 1) });
    } else {
      let prev: string | null = null;
      units.forEach((u, i) => {
        let st: string | null = null;
        if (pl?.length) {
          const same = predWhole ? (i === 0 ? pl[0] : null) : pl.find((l) => l.location_id === u);
          if (same) st = anchor(c, same);
        } else if (i === 0) st = c.start;
        if (prev) {
          const own = addDays(prev, (c.link ?? 'fs') === 'fs' ? c.duration + c.lag : c.lag);
          st = st ? gt(st, own) : own;
        }
        if (st) { out.push({ stage_id: id, location_id: u, start: st, finish: addDays(st, c.duration - 1) }); prev = st; }
      });
    }
    visiting.delete(id);
    done.set(id, out);
    return out;
  };
  try {
    const lines = cs.flatMap((c) => run(c.stage_id) ?? []);
    return { lines, error: null, missing };
  } catch (e) {
    return { lines: [], error: (e as Error).message, missing };
  }
}
