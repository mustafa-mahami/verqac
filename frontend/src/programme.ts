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

/** Critical path (CPM) over the cells of a programme: the links of its floor cycle (an earlier stage on the same
 * floor, and each crew's floor-to-floor sequence) are the network; the saved dates are the early dates.
 * Returns each cell's total float in days: 0 (or less) = critical, any delay moves the project's finish. */
export function cpm(lines: PLine[], cycles: PCycle[], units: string[], whole: Set<string>): Map<string, number> {
  type N = { s: number; f: number; d: number; lf: number };
  const day = (iso: string) => Math.round(new Date(`${iso}T00:00:00Z`).getTime() / 86_400_000);
  const nodes = new Map<string, N>();
  for (const l of lines) {
    if (!l.start || !l.finish) continue;
    const s = day(l.start), f = day(l.finish);
    nodes.set(cellKey(l.stage_id, l.location_id), { s, f, d: f - s + 1, lf: Infinity });
  }
  const edges = links(nodes, cycles, units, whole);
  const end = Math.max(...[...nodes.values()].map((n) => n.f));
  for (const n of nodes.values()) n.lf = end;
  // backward pass: relax until stable (small networks)
  for (let pass = 0, changed = true; changed && pass < 500; pass++) {
    changed = false;
    for (const e of edges) {
      const p = nodes.get(e.p)!, s = nodes.get(e.s)!;
      const ls = s.lf - s.d + 1;
      const lf = e.on === 'F' ? ls - e.k : ls - e.k + p.d - 1;
      if (lf < p.lf) { p.lf = lf; changed = true; }
    }
  }
  return new Map([...nodes].map(([k, n]) => [k, n.lf - n.f]));
}

/** Planned % of a cell on a day (linear, as on the server) and its status against the actual %. */
export function cellPlanned(start: string, finish: string, day: string): number {
  if (day < start) return 0;
  if (day >= finish) return 100;
  return Math.round(((daysBetween(start, day) + 1) / (daysBetween(start, finish) + 1)) * 1000) / 10;
}
export function cellStatus(planned: number, actual: number): 'done' | 'not_started' | 'late' | 'ahead' | 'on_track' {
  if (actual >= 100) return 'done';
  if (planned <= 0 && actual <= 0) return 'not_started';
  if (actual + 10 < planned) return 'late';
  if (actual > planned + 5) return 'ahead';
  return 'on_track';
}

export interface NetLink { p: string; s: string; on: 'S' | 'F'; k: number; crew: boolean }

/** The network of a programme: succ.start >= (pred.start | pred.finish) + k. "crew" = the same stage moving up a floor. */
export function links(nodes: Map<string, { s: number; f: number }>, cycles: PCycle[], units: string[], whole: Set<string>): NetLink[] {
  const edges: NetLink[] = [];
  const cellsOf = (stage: string) => (whole.has(stage) ? [cellKey(stage, null)] : units.map((u) => cellKey(stage, u))).filter((k) => nodes.has(k));
  for (const c of cycles) {
    const mine = cellsOf(c.stage_id);
    if (!whole.has(c.stage_id)) {  // the crew moves up floor by floor
      for (let i = 1; i < mine.length; i++)
        edges.push({ p: mine[i - 1], s: mine[i], on: (c.link ?? 'fs') === 'fs' ? 'F' : 'S', k: (c.link ?? 'fs') === 'fs' ? c.lag + 1 : c.lag, crew: true });
    }
    if (!c.pred) continue;
    const d = c.pred_days ?? 0;
    const rel = c.rel ?? 'after_end';
    const on: 'S' | 'F' = rel.endsWith('end') ? 'F' : 'S';
    const k = rel === 'after_end' ? d + 1 : rel === 'after_start' ? d : -d;
    const theirs = cellsOf(c.pred);
    if (!theirs.length || !mine.length) continue;
    if (!whole.has(c.stage_id) && !whole.has(c.pred)) {
      for (const u of units) {
        const a = cellKey(c.pred, u), b = cellKey(c.stage_id, u);
        if (nodes.has(a) && nodes.has(b)) edges.push({ p: a, s: b, on, k, crew: false });
      }
    } else if (!whole.has(c.stage_id)) {  // a floor stage after a whole-project one: its first floor
      edges.push({ p: theirs[0], s: mine[0], on, k, crew: false });
    } else {  // a whole-project stage after a floor stage: the binding floor (latest finish / earliest start)
      const pick = on === 'F' ? theirs.reduce((a, b) => (nodes.get(b)!.f > nodes.get(a)!.f ? b : a))
        : theirs.reduce((a, b) => (nodes.get(b)!.s < nodes.get(a)!.s ? b : a));
      edges.push({ p: pick, s: mine[0], on, k, crew: false });
    }
  }
  return edges;
}

/** The links between the cells of a set of lines (for drawing). */
export function lineLinks(lines: PLine[], cycles: PCycle[], units: string[], whole: Set<string>): NetLink[] {
  const day = (iso: string) => Math.round(new Date(`${iso}T00:00:00Z`).getTime() / 86_400_000);
  const nodes = new Map(lines.filter((l) => l.start && l.finish).map((l) => [cellKey(l.stage_id, l.location_id), { s: day(l.start), f: day(l.finish) }]));
  return links(nodes, cycles, units, whole);
}

/** Forecast from actual progress (status date = today): finished cells keep their dates, running ones finish after
 * their remaining days, and cells not started yet move through the links (never before today). */
export type Actual = { start: string | null; finish: string | null; pct: number; on?: string | null };

/** Forecast dates. pace = false: what is left takes the planned time. pace = true: the actual speed —
 * a running cell finishes at its own pace so far (days spent / % done), and a cell not started yet takes
 * its planned duration times the stage's pace on the cells already worked (finished or running). */
export function forecast(lines: PLine[], cycles: PCycle[], units: string[], whole: Set<string>,
  actual: Map<string, Actual>, today: string, pace = false): PLine[] {
  const day = (iso: string) => Math.round(new Date(`${iso}T00:00:00Z`).getTime() / 86_400_000);
  const iso = (n: number) => new Date(n * 86_400_000).toISOString().slice(0, 10);
  const T = day(today);
  // the stage's pace: actual (or projected) duration / planned duration, over its worked cells
  const ratios = new Map<string, number[]>();
  const own = new Map<string, number>(); // running cells: days still needed at their own pace
  for (const l of lines) {
    if (!l.start || !l.finish) continue;
    const d = day(l.finish) - day(l.start) + 1;
    const a = actual.get(cellKey(l.stage_id, l.location_id));
    if (!a || !a.start) continue;
    const fs = day(a.start);
    let r: number | null = null;
    if (a.pct >= 100 && a.finish) r = (day(a.finish) - fs + 1) / d;
    else if (a.pct > 0 && a.pct < 100) {
      const spent = Math.max(1, (a.on ? day(a.on) : T) - fs + 1);
      r = spent / (a.pct / 100) / d;
      own.set(cellKey(l.stage_id, l.location_id), Math.max(1, Math.ceil(spent * (1 - a.pct / 100) / (a.pct / 100))));
    }
    if (r !== null && Number.isFinite(r)) ratios.set(l.stage_id, [...(ratios.get(l.stage_id) ?? []), r]);
  }
  const factor = (stage: string) => {
    const rs = ratios.get(stage);
    if (!pace || !rs?.length) return 1;
    return Math.min(4, Math.max(0.25, rs.reduce((x, y) => x + y, 0) / rs.length));
  };
  type N = { s: number; f: number; d: number; fixed: boolean; base: number; stage: string; loc: string | null };
  const nodes = new Map<string, N>();
  for (const l of lines) {
    if (!l.start || !l.finish) continue;
    const s = day(l.start), f = day(l.finish), d0 = f - s + 1;
    const d = Math.max(1, Math.round(d0 * factor(l.stage_id)));
    const key = cellKey(l.stage_id, l.location_id);
    const a = actual.get(key);
    let n: N;
    if (a && a.pct >= 100) {
      const fs = a.start ? day(a.start) : s, ff = a.finish ? day(a.finish) : Math.max(fs, Math.min(f, T));
      n = { s: fs, f: Math.max(fs, ff), d, fixed: true, base: fs, stage: l.stage_id, loc: l.location_id };
    } else if (a && (a.pct > 0 || a.start)) {
      const fs = a.start ? day(a.start) : Math.min(s, T);
      const left = pace && own.has(key) ? own.get(key)! : Math.max(1, Math.ceil(d * (1 - a.pct / 100)));
      n = { s: fs, f: Math.max(T, fs) + left - 1, d, fixed: true, base: fs, stage: l.stage_id, loc: l.location_id };
    } else {
      n = { s: Math.max(s, T), f: Math.max(s, T) + d - 1, d, fixed: false, base: T, stage: l.stage_id, loc: l.location_id };
    }
    nodes.set(key, n);
  }
  const edges = links(new Map([...nodes].map(([k, n]) => [k, { s: n.s, f: n.f }])), cycles, units, whole);
  const into = new Map<string, NetLink[]>();
  for (const e of edges) into.set(e.s, [...(into.get(e.s) ?? []), e]);
  // a cell with no link keeps its planned start (but not before today)
  for (const [k, n] of nodes) if (!n.fixed && !into.has(k)) { n.base = Math.max(n.s, T); n.s = n.base; n.f = n.s + n.d - 1; }
  for (let pass = 0, changed = true; changed && pass < 500; pass++) {
    changed = false;
    for (const [k, n] of nodes) {
      if (n.fixed || !into.has(k)) continue;
      let es = T;
      for (const e of into.get(k)!) {
        const p = nodes.get(e.p)!;
        es = Math.max(es, (e.on === 'F' ? p.f : p.s) + e.k);
      }
      if (es !== n.s) { n.s = es; n.f = es + n.d - 1; changed = true; }
    }
  }
  return [...nodes.values()].map((n) => ({ stage_id: n.stage, location_id: n.loc, start: iso(n.s), finish: iso(n.f) }));
}
