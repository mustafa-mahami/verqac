import {
  ActionIcon, Alert, Badge, Button, Checkbox, Group, MultiSelect, NumberInput, Select, Stack, Switch, Table, Text, TextInput, Tooltip,
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api, type Place, type RecordRow, type StageScope, type StageT, type Structure, type TemplateStage } from '../api';
import i18n, { pick } from '../i18n';

export const useStructure = (projectId: string) =>
  useQuery({ queryKey: ['structure', projectId], queryFn: () => api<Structure>(`/projects/${projectId}/structure`) });

const lang = () => (i18n.language === 'en' ? 'en' : 'ar');
export const groupLabel = (s: Structure) => (lang() === 'en' ? s.labels.group_en : s.labels.group_ar);
export const unitLabel = (s: Structure) => (lang() === 'en' ? s.labels.unit_en : s.labels.unit_ar);

export function move<T>(list: T[], i: number, d: number): T[] {
  const next = [...list];
  [next[i], next[i + d]] = [next[i + d], next[i]];
  return next;
}

export const weightTotal = (stages: (TemplateStage & { is_active?: boolean })[]) =>
  Math.round(stages.filter((s) => s.is_active !== false).reduce((a, s) => a + (Number(s.weight) || 0), 0) * 100) / 100;

/** Rows of stages with name, scope, weight; used for type templates and for a project's own stages. */
export function StagesEditor<S extends TemplateStage & { is_active?: boolean; used?: boolean }>({ stages, onChange, editable, blank }: {
  stages: S[]; onChange: (s: S[]) => void; editable: boolean; blank: S;
}) {
  const { t } = useTranslation();
  const set = (i: number, patch: Partial<S>) => onChange(stages.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const total = weightTotal(stages);
  const withActive = stages.some((s) => s.is_active !== undefined);
  return (
    <Stack gap="xs">
      <Table.ScrollContainer minWidth={640}>
        <Table verticalSpacing={4} horizontalSpacing={6} withRowBorders={false}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('structure.nameAr')}</Table.Th><Table.Th>{t('structure.nameEn')}</Table.Th>
              <Table.Th w={150}>{t('structure.scope')}</Table.Th><Table.Th w={100}>{t('structure.weight')}</Table.Th>
              {withActive && <Table.Th w={50} />}{editable && <Table.Th w={100} />}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {stages.map((s, i) => (
              <Table.Tr key={i} opacity={s.is_active === false ? 0.55 : 1}>
                <Table.Td><TextInput size="xs" disabled={!editable} value={s.name_ar} onChange={(e) => set(i, { name_ar: e.currentTarget.value } as Partial<S>)} /></Table.Td>
                <Table.Td><TextInput size="xs" dir="ltr" disabled={!editable} value={s.name_en} onChange={(e) => set(i, { name_en: e.currentTarget.value } as Partial<S>)} /></Table.Td>
                <Table.Td>
                  <Select size="xs" disabled={!editable} allowDeselect={false} value={s.scope}
                    data={[{ value: 'per_location', label: t('structure.perLocation') }, { value: 'whole', label: t('structure.whole') }]}
                    onChange={(v) => set(i, { scope: (v ?? 'per_location') as StageScope } as Partial<S>)} />
                </Table.Td>
                <Table.Td>
                  <NumberInput size="xs" min={0} max={100} decimalScale={2} hideControls disabled={!editable} rightSection="%"
                    value={Number(s.weight)} onChange={(v) => set(i, { weight: Number(v) || 0 } as Partial<S>)} />
                </Table.Td>
                {withActive && (
                  <Table.Td>
                    <Tooltip label={t(s.is_active ? 'settings.kindActive' : 'structure.inactive')}>
                      <Switch size="xs" disabled={!editable} checked={s.is_active !== false} aria-label={t('settings.kindActive')}
                        onChange={(e) => set(i, { is_active: e.currentTarget.checked } as Partial<S>)} />
                    </Tooltip>
                  </Table.Td>
                )}
                {editable && (
                  <Table.Td>
                    <Group gap={2} wrap="nowrap">
                      <ActionIcon size="sm" variant="subtle" color="gray" disabled={i === 0} aria-label="up" onClick={() => onChange(move(stages, i, -1))}>↑</ActionIcon>
                      <ActionIcon size="sm" variant="subtle" color="gray" disabled={i === stages.length - 1} aria-label="down" onClick={() => onChange(move(stages, i, 1))}>↓</ActionIcon>
                      <Tooltip label={t('structure.usedHint')} disabled={!s.used}>
                        <ActionIcon size="sm" variant="subtle" color="red" disabled={s.used} aria-label="remove"
                          onClick={() => onChange(stages.filter((_, j) => j !== i))}>×</ActionIcon>
                      </Tooltip>
                    </Group>
                  </Table.Td>
                )}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <Group justify="space-between">
        {editable ? <Button size="xs" variant="subtle" onClick={() => onChange([...stages, { ...blank }])}>+ {t('structure.addStage')}</Button> : <span />}
        {stages.length > 0 && (
          <Badge tt="none" variant="light" color={Math.abs(total - 100) < 0.01 ? 'green' : 'red'}>
            {t('structure.total')}: {total}%
          </Badge>
        )}
      </Group>
    </Stack>
  );
}

/** Text for a register row: "البلاط · مبنى 1 – الطابق 3، السطح" */
export function placeText(s: Structure | undefined, r: Pick<RecordRow, 'stage_id' | 'all_locations' | 'location_ids'>): string {
  if (!s) return '';
  const { t } = i18n;
  const stage = s.stages.find((x) => x.id === r.stage_id);
  const many = s.locations.length > 1;
  const names: string[] = [];
  for (const id of r.location_ids) {
    for (const g of s.locations) {
      if (g.id === id) names.push(`${pick(g, 'name')} (${t('structure.wholeGroup')})`);
      const u = g.units.find((x) => x.id === id);
      if (u) names.push(many ? `${pick(g, 'name')} – ${pick(u, 'name')}` : pick(u, 'name'));
    }
  }
  const where = r.all_locations ? t('structure.wholeProject') : names.join(lang() === 'ar' ? '، ' : ', ');
  return [stage ? pick(stage, 'name') : '', where].filter(Boolean).join(' · ');
}

/** Does a row cover a location (a whole group, or a unit, directly or through its group)? */
export function coversLocation(s: Structure, r: Pick<RecordRow, 'all_locations' | 'location_ids'>, loc: string): boolean {
  if (r.all_locations) return true;
  if (r.location_ids.includes(loc)) return true;
  for (const g of s.locations) {
    if (g.id === loc) return g.units.some((u) => r.location_ids.includes(u.id ?? ''));
    if (g.units.some((u) => u.id === loc)) return r.location_ids.includes(g.id ?? '');
  }
  return false;
}

/** Location options for a picker or a filter, grouped by building when there are several. */
export function locationOptions(s: Structure, keep: string[] = [], withGroups = true) {
  const many = s.locations.length > 1;
  const ok = (x: { id: string | null; is_active: boolean }) => x.is_active || keep.includes(x.id ?? '');
  const groups = s.locations.filter(ok).map((g) => ({
    group: pick(g, 'name'),
    items: [
      ...(many && withGroups ? [{ value: g.id!, label: `${pick(g, 'name')} — ${i18n.t('structure.wholeGroup')}` }] : []),
      ...g.units.filter(ok).map((u) => ({ value: u.id!, label: many ? `${pick(g, 'name')} – ${pick(u, 'name')}` : pick(u, 'name') })),
    ],
  }));
  return many ? groups : groups.flatMap((g) => g.items);
}

/** Stage + locations of a record: one stage; the whole project or one or more buildings / floors. */
export function PlacePicker({ structure, value, onChange, keep }: {
  structure: Structure; value: Place; onChange: (p: Place) => void; keep?: Place;
}) {
  const { t } = useTranslation();
  const stages = structure.stages.filter((s) => s.is_active || s.id === keep?.stage_id);
  if (structure.stages.length === 0 && structure.locations.length === 0)
    return <Alert color="gray" variant="light" py="xs"><Text size="sm">{t(structure.can_edit ? 'structure.noneYetEditor' : 'structure.noneYet')}</Text></Alert>;
  const stage: StageT | undefined = structure.stages.find((s) => s.id === value.stage_id);
  const whole = stage?.scope === 'whole';
  return (
    <Stack gap={6}>
      <Group grow align="flex-start">
        <Select label={t('structure.stage')} clearable searchable value={value.stage_id}
          data={stages.map((s) => ({ value: s.id!, label: pick(s, 'name') }))}
          onChange={(v) => {
            const st = structure.stages.find((s) => s.id === v);
            onChange({ ...value, stage_id: v, ...(st?.scope === 'whole' ? { all_locations: true, location_ids: [] } : {}) });
          }} />
        <Stack gap={4}>
          <MultiSelect label={`${unitLabel(structure)} / ${groupLabel(structure)}`} searchable clearable
            disabled={value.all_locations} placeholder={value.all_locations ? t('structure.wholeProject') : t('structure.pickLocations')}
            data={locationOptions(structure, keep?.location_ids ?? [])} value={value.all_locations ? [] : value.location_ids}
            onChange={(ids) => onChange({ ...value, location_ids: ids })} />
          <Checkbox size="xs" label={t('structure.wholeProject')} checked={value.all_locations} disabled={whole}
            onChange={(e) => onChange({ ...value, all_locations: e.currentTarget.checked, location_ids: [] })} />
        </Stack>
      </Group>
      {whole && <Text size="xs" c="dimmed">{t('structure.wholeStageHint')}</Text>}
    </Stack>
  );
}
