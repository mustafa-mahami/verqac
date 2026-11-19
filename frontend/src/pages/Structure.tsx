import {
  ActionIcon, Alert, Badge, Button, Checkbox, Group, Modal, MultiSelect, NumberInput, Popover, ScrollArea, Select, Stack, Switch, Table, Text, TextInput, Tooltip,
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { Fragment, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, type Place, type RecordRow, type StageScope, type StageT, type Structure, type CheckItem, type TemplateStage, type TopicT } from '../api';
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

/** The inspection checklist of one topic: lines in Arabic and English, in order. */
function ChecklistEditor({ items, onChange, editable }: { items: CheckItem[]; onChange: (x: CheckItem[]) => void; editable: boolean }) {
  const { t } = useTranslation();
  const set = (i: number, patch: Partial<CheckItem>) => onChange(items.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  return (
    <Stack gap={6}>
      {items.length === 0 && <Text size="sm" c="dimmed">{t('checklist.empty')}</Text>}
      {items.map((x, i) => (
        <Group key={i} gap={6} wrap="nowrap" align="flex-start">
          <Text size="xs" c="dimmed" w={18} pt={6}>{i + 1}</Text>
          <TextInput size="xs" flex={1} placeholder={t('structure.nameAr')} disabled={!editable} value={x.ar}
            onChange={(e) => set(i, { ar: e.currentTarget.value })} />
          <TextInput size="xs" flex={1} dir="ltr" placeholder={t('structure.nameEn')} disabled={!editable} value={x.en}
            onChange={(e) => set(i, { en: e.currentTarget.value })} />
          {editable && (
            <Group gap={2} wrap="nowrap">
              <ActionIcon size="sm" variant="subtle" color="gray" disabled={i === 0} aria-label="up" onClick={() => onChange(move(items, i, -1))}>↑</ActionIcon>
              <ActionIcon size="sm" variant="subtle" color="gray" disabled={i === items.length - 1} aria-label="down" onClick={() => onChange(move(items, i, 1))}>↓</ActionIcon>
              <ActionIcon size="sm" variant="subtle" color="red" aria-label="remove" onClick={() => onChange(items.filter((_, j) => j !== i))}>×</ActionIcon>
            </Group>
          )}
        </Group>
      ))}
      {editable && (
        <Group><Button size="compact-xs" variant="subtle" onClick={() => onChange([...items, { ar: '', en: '' }])}>+ {t('checklist.add')}</Button></Group>
      )}
      <Text size="xs" c="dimmed">{t('checklist.hint')}</Text>
    </Stack>
  );
}

/** Subjects under one stage: names, order, on/off (project stages), delete unless used. */
function TopicsEditor({ topics, onChange, editable, withActive, checklists }: {
  topics: TopicT[]; onChange: (t: TopicT[]) => void; editable: boolean; withActive: boolean; checklists: boolean;
}) {
  const { t } = useTranslation();
  const set = (i: number, patch: Partial<TopicT>) => onChange(topics.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const [open, setOpen] = useState<number | null>(null);
  const cur = open !== null ? topics[open] : null;
  return (
    <Stack gap={4} ps="lg" py={4}>
      <Modal opened={cur !== null} onClose={() => setOpen(null)} size="xl"
        title={cur ? `${t('checklist.title')} · ${pick(cur, 'name')}` : ''}>
        {cur && open !== null && <ChecklistEditor items={cur.checklist ?? []} editable={editable}
          onChange={(c) => set(open, { checklist: c })} />}
        <Group justify="flex-end" mt="md"><Button size="xs" onClick={() => setOpen(null)}>{t('checklist.done')}</Button></Group>
      </Modal>
      {topics.map((x, i) => (
        <Group key={x.id ?? `n-${i}`} gap={6} wrap="nowrap" opacity={x.is_active === false ? 0.55 : 1}>
          <TextInput size="xs" flex={1} aria-label={t('structure.nameAr')} placeholder={t('structure.nameAr')} disabled={!editable}
            value={x.name_ar} onChange={(e) => set(i, { name_ar: e.currentTarget.value })} />
          <TextInput size="xs" flex={1} dir="ltr" aria-label={t('structure.nameEn')} placeholder={t('structure.nameEn')} disabled={!editable}
            value={x.name_en} onChange={(e) => set(i, { name_en: e.currentTarget.value })} />
          {checklists && (
            <Button size="compact-xs" variant={(x.checklist ?? []).length ? 'light' : 'subtle'} color="gray" onClick={() => setOpen(i)}>
              {t('checklist.button', { count: (x.checklist ?? []).length })}
            </Button>
          )}
          {withActive && <Switch size="xs" disabled={!editable} checked={x.is_active !== false} aria-label={t('settings.kindActive')}
            onChange={(e) => set(i, { is_active: e.currentTarget.checked })} />}
          {editable && (
            <Group gap={2} wrap="nowrap">
              <ActionIcon size="sm" variant="subtle" color="gray" disabled={i === 0} aria-label="up" onClick={() => onChange(move(topics, i, -1))}>↑</ActionIcon>
              <ActionIcon size="sm" variant="subtle" color="gray" disabled={i === topics.length - 1} aria-label="down" onClick={() => onChange(move(topics, i, 1))}>↓</ActionIcon>
              <Tooltip label={t('structure.usedHint')} disabled={!x.used}>
                <ActionIcon size="sm" variant="subtle" color="red" disabled={x.used} aria-label="remove"
                  onClick={() => onChange(topics.filter((_, j) => j !== i))}>×</ActionIcon>
              </Tooltip>
            </Group>
          )}
        </Group>
      ))}
      {editable && (
        <Group>
          <Button size="compact-xs" variant="subtle"
            onClick={() => onChange([...topics, { id: null, name_ar: '', name_en: '', checklist: [], ...(withActive ? { is_active: true, used: false } : {}) }])}>
            + {t('structure.addTopic')}
          </Button>
        </Group>
      )}
    </Stack>
  );
}

/** The floors a per-location stage applies to (none ticked = all of them). */
function StageFloors({ units, value, onChange, editable }: {
  units: { value: string; label: string }[]; value: string[]; onChange: (ids: string[]) => void; editable: boolean;
}) {
  const { t } = useTranslation();
  const mine = value.filter((v) => units.some((u) => u.value === v));
  const all = !mine.length || mine.length === units.length;
  return (
    <Popover width={260} position="bottom-start" shadow="md">
      <Popover.Target>
        <Button size="compact-xs" variant="subtle" color={all ? 'gray' : 'orange'} mt={2}>
          {all ? t('structure.allFloors') : t('structure.someFloors', { n: mine.length, of: units.length })} ▾
        </Button>
      </Popover.Target>
      <Popover.Dropdown>
        <Text size="xs" c="dimmed" mb={6}>{t('structure.floorsHint')}</Text>
        <Group gap={6} mb={6}>
          <Button size="compact-xs" variant="light" disabled={!editable} onClick={() => onChange([])}>{t('structure.allFloors')}</Button>
        </Group>
        <ScrollArea.Autosize mah={260}>
          <Checkbox.Group value={all ? units.map((u) => u.value) : mine} onChange={(v) => onChange(v)}>
            <Stack gap={4}>{units.map((u) => <Checkbox key={u.value} size="xs" value={u.value} label={u.label} disabled={!editable} />)}</Stack>
          </Checkbox.Group>
        </ScrollArea.Autosize>
      </Popover.Dropdown>
    </Popover>
  );
}

/** Rows of stages with name, scope, weight and their subjects; for type templates and a project's own stages. */
export function StagesEditor<S extends TemplateStage & { is_active?: boolean; used?: boolean; scope_locked?: boolean; location_ids?: string[] | null }>({ stages, onChange, editable, blank, checklists = true, units }: {
  stages: S[]; onChange: (s: S[]) => void; editable: boolean; blank: S; checklists?: boolean;
  units?: { value: string; label: string }[]; // a project's floors: a per-location stage can be limited to some
}) {
  const { t } = useTranslation();
  const set = (i: number, patch: Partial<S>) => onChange(stages.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const total = weightTotal(stages);
  const withActive = stages.some((s) => s.is_active !== undefined);
  const [open, setOpen] = useState<number | null>(null);
  const cols = 5 + (withActive ? 1 : 0) + (editable ? 1 : 0);
  return (
    <Stack gap="xs">
      <Table.ScrollContainer minWidth={640}>
        <Table verticalSpacing={4} horizontalSpacing={6} withRowBorders={false}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('structure.nameAr')}</Table.Th><Table.Th>{t('structure.nameEn')}</Table.Th>
              <Table.Th w={150}>{t('structure.scope')}</Table.Th><Table.Th w={100}>{t('structure.weight')}</Table.Th>
              <Table.Th w={110}>{t('structure.topics')}</Table.Th>
              {withActive && <Table.Th w={50} />}{editable && <Table.Th w={100} />}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {stages.map((s, i) => (
              <Fragment key={i}>
              <Table.Tr opacity={s.is_active === false ? 0.55 : 1}>
                <Table.Td><TextInput size="xs" disabled={!editable} value={s.name_ar} onChange={(e) => set(i, { name_ar: e.currentTarget.value } as Partial<S>)} /></Table.Td>
                <Table.Td><TextInput size="xs" dir="ltr" disabled={!editable} value={s.name_en} onChange={(e) => set(i, { name_en: e.currentTarget.value } as Partial<S>)} /></Table.Td>
                <Table.Td>
                  <Tooltip label={t('structure.scopeLocked')} disabled={!s.scope_locked} multiline w={280}>
                    <div><Select size="xs" disabled={!editable || !!s.scope_locked} allowDeselect={false} value={s.scope}
                      data={[{ value: 'per_location', label: t('structure.perLocation') }, { value: 'whole', label: t('structure.whole') }]}
                      onChange={(v) => set(i, { scope: (v ?? 'per_location') as StageScope } as Partial<S>)} /></div>
                  </Tooltip>
                  {units && units.length > 1 && s.scope === 'per_location' && (
                    <StageFloors units={units} value={s.location_ids ?? []} editable={editable}
                      onChange={(ids) => set(i, { location_ids: ids.length && ids.length < units.length ? ids : null } as Partial<S>)} />
                  )}
                </Table.Td>
                <Table.Td>
                  <NumberInput size="xs" min={0} max={100} decimalScale={2} hideControls disabled={!editable} rightSection="%"
                    value={Number(s.weight)} onChange={(v) => set(i, { weight: Number(v) || 0 } as Partial<S>)} />
                </Table.Td>
                <Table.Td>
                  <Button size="compact-xs" variant={open === i ? 'light' : 'subtle'} onClick={() => setOpen(open === i ? null : i)}>
                    {t('structure.topicsCount', { count: (s.topics ?? []).length })} {open === i ? '▴' : '▾'}
                  </Button>
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
              {open === i && (
                <Table.Tr>
                  <Table.Td colSpan={cols} bg="gray.0">
                    <TopicsEditor topics={s.topics ?? []} editable={editable} withActive={withActive} checklists={checklists}
                      onChange={(tp) => set(i, { topics: tp } as Partial<S>)} />
                  </Table.Td>
                </Table.Tr>
              )}
              </Fragment>
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

/** The subject of a record: stage, then a topic of that stage (or a typed subject), then where it applies. */
export function PlacePicker({ structure, value, onChange, keep, title, onTitle }: {
  structure: Structure; value: Place; onChange: (p: Place) => void; keep?: Place;
  title: string; onTitle: (v: string) => void;
}) {
  const { t } = useTranslation();
  const empty = structure.stages.length === 0 && structure.locations.length === 0;
  const stages = structure.stages.filter((s) => s.is_active || s.id === keep?.stage_id);
  const stage: StageT | undefined = structure.stages.find((s) => s.id === value.stage_id);
  const topics = (stage?.topics ?? []).filter((x) => x.is_active !== false || x.id === keep?.topic_id);
  const whole = stage?.scope === 'whole';
  const useTopic = topics.length > 0;
  return (
    <Stack gap={6}>
      {empty && <Alert color="gray" variant="light" py="xs"><Text size="sm">{t(structure.can_edit ? 'structure.noneYetEditor' : 'structure.noneYet')}</Text></Alert>}
      <Group grow align="flex-start">
        {!empty && (
          <Select label={t('structure.stage')} clearable searchable value={value.stage_id}
            data={stages.map((s) => ({ value: s.id!, label: pick(s, 'name') }))}
            onChange={(v) => {
              const st = structure.stages.find((s) => s.id === v);
              onChange({ ...value, stage_id: v, topic_id: null, ...(st?.scope === 'whole' ? { all_locations: true, location_ids: [] } : {}) });
            }} />
        )}
        {useTopic ? (
          <Select label={t('rec.title')} required searchable value={value.topic_id} placeholder={t('structure.pickTopic')}
            data={topics.map((x) => ({ value: x.id!, label: pick(x, 'name') }))}
            onChange={(v) => onChange({ ...value, topic_id: v })} />
        ) : (
          <TextInput label={t('rec.title')} required value={title} onChange={(e) => onTitle(e.currentTarget.value)} />
        )}
      </Group>
      {!empty && (
        <Stack gap={4}>
          <MultiSelect label={`${unitLabel(structure)} / ${groupLabel(structure)}`} searchable clearable
            disabled={value.all_locations} placeholder={value.all_locations ? t('structure.wholeProject') : t('structure.pickLocations')}
            data={locationOptions(structure, keep?.location_ids ?? [])} value={value.all_locations ? [] : value.location_ids}
            onChange={(ids) => onChange({ ...value, location_ids: ids })} />
          <Checkbox size="xs" label={t('structure.wholeProject')} checked={value.all_locations} disabled={whole}
            onChange={(e) => onChange({ ...value, all_locations: e.currentTarget.checked, location_ids: [] })} />
          {whole && <Text size="xs" c="dimmed">{t('structure.wholeStageHint')}</Text>}
        </Stack>
      )}
    </Stack>
  );
}

/** Name of a register row: its topic in the current language, or the typed subject. */
export function rowTitle(s: Structure | undefined, r: Pick<RecordRow, 'topic_id' | 'title'>): string {
  if (s && r.topic_id) for (const st of s.stages) {
    const x = st.topics?.find((tp) => tp.id === r.topic_id);
    if (x) return pick(x, 'name');
  }
  return r.title;
}
