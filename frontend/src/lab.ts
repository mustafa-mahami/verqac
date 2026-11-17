import { api } from './api';

export interface LabLine {
  sample: string | null; parameter: string; unit: string | null; method: string | null; age: number | null;
  kind: 'number' | 'okng'; value: number | null; text: string | null; min: number | null; max: number | null;
  role: 'strength7' | 'strength28' | null; legible: boolean; result?: 'pass' | 'fail' | 'na' | null;
}
export interface LabTemplate {
  id: string | null; code: string | null; name_ar: string; name_en: string; material: string; standard: string | null;
  acceptance: 'all' | 'concrete'; samples: string | null; lines: LabLine[]; is_active: boolean;
}
export interface ConcreteClass {
  id: string | null; grade: string; name: string | null; aliases: string | null; specimen: 'cube' | 'cylinder'; fck: number;
  mean_margin: number; individual_rule: 'minus' | 'percent'; individual_margin: number; elements: string | null;
  topic_ids: string[]; ref: string | null; is_active: boolean; tests?: number;
}
export interface LabData {
  template_id: string | null; material: string | null; acceptance: 'all' | 'concrete'; lab_name: string | null;
  lab_report_no: string | null; sampling_date: string | null; test_date: string | null; report_date: string | null;
  grade: string | null; class_id: string | null; fck: number | null; mean_margin: number | null;
  individual_rule: 'minus' | 'percent' | null; individual_margin: number | null; element: string | null;
  quantity: number | null; quantity_uom: string | null; specimen_count: number | null; specification: string | null;
  lab_conclusion: 'pass' | 'fail' | null; lines: LabLine[];
}
export interface LabOut extends LabData {
  result: 'pass' | 'fail' | null; note: string | null; strength_avg: number | null; strength_min: number | null; below: number;
  checked: number; failed: number; decision: string | null; decision_note: string | null; decision_at: string | null;
  conflict: boolean; can_edit: boolean; can_decide: boolean; ai_enabled: boolean;
  ai_state: 'reading' | 'ready' | 'error' | 'applied' | null; ai_message: string | null;
  ai_draft: (Partial<LabData> & { class_match?: string; cert_grade?: string | null; cert_strength?: number | null; remarks?: string | null; model?: string }) | null;
  ai_file_id: string | null;
}

export const MATERIALS = ['CON', 'STL', 'BC', 'SOIL', 'ASP', 'BLK', 'TIL', 'WP', 'MEP', 'OTH'];
export const DECISIONS = ['retest', 'core', 'accepted', 'repair', 'rejected', 'other'];

export const blankLine = (p: Partial<LabLine> = {}): LabLine => ({
  sample: null, parameter: '', unit: null, method: null, age: null, kind: 'number', value: null, text: null,
  min: null, max: null, role: null, legible: true, ...p,
});

/** Lines of a new test from its template: concrete = 7-day and 28-day lines per specimen, else every parameter per sample. */
export function linesFromTemplate(tpl: LabTemplate, opts: { specimens?: number; fck?: number | null; samples?: string }): LabLine[] {
  if (tpl.acceptance === 'concrete') {
    const out: LabLine[] = [];
    for (let i = 1; i <= (opts.specimens || 0); i++) {
      out.push(blankLine({ sample: `${i}-1`, parameter: 'Compressive strength 7-day', unit: 'MPa', age: 7, role: 'strength7' }));
      out.push(blankLine({ sample: `${i}-1`, parameter: 'Compressive strength 28-day', unit: 'MPa', age: 28, role: 'strength28', min: opts.fck ?? null }));
    }
    return out;
  }
  const samples = (opts.samples ?? tpl.samples ?? '').split(',').map((x) => x.trim()).filter(Boolean);
  return (samples.length ? samples : [null]).flatMap((s) => tpl.lines.map((l) => blankLine({ ...l, sample: s ?? l.sample, value: null, text: null })));
}

export const saveLab = (recordId: string, data: Partial<LabData> & { ai_applied?: boolean }) =>
  api<LabOut>(`/records/${recordId}/lab`, { method: 'PUT', body: JSON.stringify(data) });

export const labPayload = (d: LabData): LabData => ({
  template_id: d.template_id, material: d.material, acceptance: d.acceptance, lab_name: d.lab_name, lab_report_no: d.lab_report_no,
  sampling_date: d.sampling_date || null, test_date: d.test_date || null, report_date: d.report_date || null, grade: d.grade,
  class_id: d.class_id, fck: d.fck, mean_margin: d.mean_margin, individual_rule: d.individual_rule,
  individual_margin: d.individual_margin, element: d.element, quantity: d.quantity, quantity_uom: d.quantity_uom,
  specimen_count: d.specimen_count, specification: d.specification, lab_conclusion: d.lab_conclusion,
  lines: d.lines.map(({ result: _r, ...x }) => x),
});
