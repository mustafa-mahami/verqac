export type Group = 'supervision' | 'contractor' | 'labour';
export interface CrewLine { group: Group; sub: string | null; name: string; name_en?: string | null; role?: string | null; role_en?: string | null; count: number; hours: number | null }
export interface ListItem { ar: string; en: string; role_ar?: string | null; role_en?: string | null; active: boolean }
export interface EquipLine { name: string; count: number; hours: number | null; idle_hours: number | null; note: string | null }
export interface MaterialLine { material: string; qty: number | null; unit: string | null; supplier: string | null; delivery_note: string | null; submittal_id: string | null; mir_id: string | null }
export interface WorkLine { stage_id: string | null; topic_id: string | null; location_ids: string[]; all_locations: boolean; description: string | null; qty: number | null; unit: string | null; crew: number | null; progress: number | null }
export interface DelayLine { cause: string; hours: number | null; description: string | null; link_id: string | null }
export interface DailyData {
  shift: 'day' | 'night' | 'both'; work_status: 'normal' | 'partial' | 'stopped'; stop_reason: string | null; weather: string | null;
  temp_min: number | null; temp_max: number | null; wind: string | null; hours_from: string | null; hours_to: string | null;
  crew: CrewLine[]; equipment: EquipLine[]; materials: MaterialLine[]; works: WorkLine[]; planned: WorkLine[]; delays: DelayLine[];
  hse: { incidents: number; near_misses: number; toolbox: number; notes: string | null }; visitors: string | null; notes: string | null;
}
export interface DailyOut extends DailyData {
  record_id: string; report_date: string; can_edit: boolean; day_no: number | null; weekday: number; day_off: 'weekend' | 'holiday' | null; holiday: string | null; current: Record<string, number>; totals: Record<string, number>;
  qa: { code: string; name_ar: string; name_en: string; submitted: number; answered: number }[];
}
export interface DailySettings { crew: Record<Group, 'names' | 'counts'>; link_materials: boolean; lists: Record<string, ListItem[]> }
export const OTHER_LISTS = ['subcontractors', 'equipment'] as const;
/** The list a crew group uses: people in "names" mode, positions / trades in "counts" mode. */
export const crewList = (s: DailySettings, g: Group) => `${g}_${s.crew[g] === 'names' ? 'names' : 'desc'}`;
export const itemLabel = (x: { ar: string; en: string }, lang: string) => (lang === 'en' ? x.en || x.ar : x.ar || x.en);
export interface ProgressOut {
  project: number; stages: Record<string, number>; as_of: string | null;
  cells: { stage_id: string; location_id: string | null; progress: number; progress_on: string | null; started_on: string | null; finished_on: string | null }[];
  snapshots: { day: string; actual: number; planned: number | null }[];
}
export const GROUPS: Group[] = ['supervision', 'contractor', 'labour'];
export const WEATHER = ['sunny', 'cloudy', 'rain', 'storm', 'snow', 'fog', 'dust', 'hot', 'cold'];
export const CAUSES = ['weather', 'materials', 'design', 'approval', 'equipment', 'labour', 'utilities', 'access', 'other'];
export const blankWork = (): WorkLine => ({ stage_id: null, topic_id: null, location_ids: [], all_locations: false, description: null, qty: null, unit: null, crew: null, progress: null });
