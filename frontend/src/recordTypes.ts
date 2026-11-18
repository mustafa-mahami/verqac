import { Select, Textarea, TextInput } from '@mantine/core';
import { createElement } from 'react';
import i18n from './i18n';

/** What each request type shows and asks for. The engine is the same; the fields differ. */
export type RegisterType = 'daily_report' | 'submittal' | 'inspection' | 'material' | 'test' | 'rfi' | 'ncr';
export type DetailKey = 'item' | 'manufacturer' | 'supplier' | 'drawing_ref' | 'spec_ref' | 'boq_ref' | 'quantity' | 'unit';
export interface CustomField { key: string; kind: 'text' | 'long' | 'select'; options?: string[] }
export interface TypeProfile {
  keys: DetailKey[]; custom: CustomField[];
  kind: boolean; // submittal kind select
  timed: boolean; // requested / performed time, links to approved submittals
  requiredBy: boolean; // "answer needed by" date
  checklist: boolean;
  tab: string;
}

export const PROFILES: Record<RegisterType, TypeProfile> = {
  daily_report: { keys: [], custom: [], kind: false, timed: false, requiredBy: false, checklist: false, tab: 'daily' },
  submittal: { keys: ['item', 'manufacturer', 'supplier', 'drawing_ref', 'spec_ref', 'boq_ref', 'quantity', 'unit'], custom: [],
    kind: true, timed: false, requiredBy: true, checklist: false, tab: 'submittals' },
  inspection: { keys: ['item', 'drawing_ref', 'spec_ref', 'boq_ref'], custom: [],
    kind: false, timed: true, requiredBy: false, checklist: true, tab: 'inspections' },
  material: { keys: ['item', 'manufacturer', 'supplier', 'quantity', 'unit', 'spec_ref', 'boq_ref'],
    custom: [{ key: 'delivery_note', kind: 'text' }, { key: 'storage', kind: 'text' }],
    kind: false, timed: true, requiredBy: false, checklist: false, tab: 'materials' },
  test: { keys: [], custom: [], kind: false, timed: false, requiredBy: false, checklist: false, tab: 'tests' },
  rfi: { keys: ['item', 'drawing_ref', 'spec_ref'],
    custom: [{ key: 'proposed', kind: 'long' }, { key: 'impact', kind: 'select', options: ['none', 'cost', 'time', 'cost_time'] }],
    kind: false, timed: false, requiredBy: true, checklist: false, tab: 'rfis' },
  ncr: { keys: ['item', 'drawing_ref', 'spec_ref'],
    custom: [{ key: 'severity', kind: 'select', options: ['minor', 'major'] }, { key: 'required_action', kind: 'long' }],
    kind: false, timed: false, requiredBy: false, checklist: false, tab: 'ncrs' },
};

export const profile = (code: string): TypeProfile => PROFILES[code as RegisterType] ?? PROFILES.submittal;
export const TYPE_TABS: [RegisterType, string][] = (Object.keys(PROFILES) as RegisterType[]).map((k) => [k, PROFILES[k].tab]);

export const LTR_KEYS = new Set(['drawing_ref', 'spec_ref', 'boq_ref', 'quantity', 'delivery_note']);

/** Field label: a type may name a field its own way (an inspection's "item" is the work inspected). */
export const fieldLabel = (code: string, key: string) =>
  i18n.t(`types.${code}.f.${key}`, { defaultValue: i18n.t(`rec.f.${key}`, { defaultValue: i18n.t(`custom.${key}`) }) });
export const typeText = (code: string, key: string, fallback: string) =>
  i18n.t(`types.${code}.${key}`, { defaultValue: i18n.t(fallback) });
export const choiceLabel = (v: string) => i18n.t(`custom.choice.${v}`, { defaultValue: v });

/** One input for a custom field. */
export function CustomInput({ code, f, value, onChange, disabled }: {
  code: string; f: CustomField; value: string; onChange: (v: string) => void; disabled?: boolean;
}) {
  const label = fieldLabel(code, f.key);
  if (f.kind === 'select')
    return createElement(Select, { label, value: value || null, clearable: true, disabled,
      data: (f.options ?? []).map((o) => ({ value: o, label: choiceLabel(o) })), onChange: (v: string | null) => onChange(v ?? '') });
  if (f.kind === 'long')
    return createElement(Textarea, { label, value, autosize: true, minRows: 2, disabled, style: { gridColumn: '1 / -1' },
      onChange: (e: { currentTarget: { value: string } }) => onChange(e.currentTarget.value) });
  return createElement(TextInput, { label, value, disabled, dir: LTR_KEYS.has(f.key) ? 'ltr' : undefined,
    onChange: (e: { currentTarget: { value: string } }) => onChange(e.currentTarget.value) });
}
