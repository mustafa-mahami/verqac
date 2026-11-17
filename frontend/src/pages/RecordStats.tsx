import { Badge, Card, Group, SegmentedControl, Select, SimpleGrid, Text, UnstyledButton } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import type { RecordRow, State, Structure } from '../api';
import { coversLocation, locationOptions } from './Structure';
import { pick } from '../i18n';

/** State categories in workflow order, with the colours the states use. Same for every record type. */
export const CATEGORIES = [
  ['draft', 'gray'], ['submitted', 'blue'], ['responded', 'orange'], ['approved', 'green'], ['approved_as_noted', 'teal'],
  ['revise_and_resubmit', 'orange'], ['rejected', 'red'], ['cancelled', 'dark'],
] as const;

export interface StatsFilter {
  status: string; discipline: string; kind?: string; // kind: submittal type code or "all"
  stage?: string; topic?: string; loc?: string; // a stage id / a location id (building or floor), or "all"
  q?: string; from?: string; to?: string; // text in number/title; submission date range (YYYY-MM-DD, inclusive)
}

/** Local calendar day of a timestamp, as YYYY-MM-DD. */
const dayOf = (iso: string) => { const d = new Date(iso); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };

/** Which rows a filter keeps: status is "all", "overdue" or a state category; discipline is a code or "all". */
export function applyFilter(rows: RecordRow[], f: StatsFilter, ignoreStatus = false, structure?: Structure): RecordRow[] {
  const q = (f.q ?? '').trim().toLowerCase();
  return rows.filter((r) => {
    if (f.discipline !== 'all' && r.discipline?.code !== f.discipline) return false;
    if (f.kind && f.kind !== 'all' && r.submittal_kind !== f.kind) return false;
    if (f.stage && f.stage !== 'all' && r.stage_id !== f.stage) return false;
    if (f.topic && f.topic !== 'all' && r.topic_id !== f.topic) return false;
    if (f.loc && f.loc !== 'all' && structure && !coversLocation(structure, r, f.loc)) return false;
    if (q && !r.number.toLowerCase().includes(q) && !r.title.toLowerCase().includes(q)) return false;
    if (f.from || f.to) {
      if (!r.submitted_at) return false; // drafts were not submitted in any period
      const day = dayOf(r.submitted_at);
      if ((f.from && day < f.from) || (f.to && day > f.to)) return false;
    }
    if (ignoreStatus || f.status === 'all') return true;
    if (f.status === 'overdue') return r.overdue;
    if (f.status === 'resubmit_overdue') return r.resubmit_overdue;
    return r.state.category === f.status;
  });
}

/**
 * Register dashboard: one tile per state category with its count, plus all and overdue.
 * A tile filters the list below; a discipline switch appears when the list spans several disciplines.
 */
export default function RecordStats({ rows, filter, onChange, showDraft, structure, states }: {
  rows: RecordRow[]; filter: StatsFilter; onChange: (f: StatsFilter) => void; showDraft: boolean; structure?: Structure;
  states?: State[];
}) {
  // tile names come from this record type's workflow (an inspection is "accepted", a submittal "approved")
  const stateName = (cat: string) => { const s = states?.find((x) => x.category === cat); return s ? pick(s, 'name') : null; };
  const hasCat = (cat: string) => !states || states.some((x) => x.category === cat);
  const { t } = useTranslation();
  const disciplines = new Map<string, RecordRow['discipline']>();
  rows.forEach((r) => r.discipline && disciplines.set(r.discipline.code, r.discipline));
  const kinds = new Map<string, string>();
  rows.forEach((r) => r.submittal_kind && kinds.set(r.submittal_kind,
    r.submittal_kind_name ? pick({ n_ar: r.submittal_kind_name.ar, n_en: r.submittal_kind_name.en }, 'n') : r.submittal_kind));
  const inScope = applyFilter(rows, filter, true, structure);
  const count = (status: string) => applyFilter(inScope, { ...filter, status }, false, structure).length;
  const usedStages = new Set(rows.map((r) => r.stage_id).filter(Boolean));
  const stageOptions = (structure?.stages ?? []).filter((x) => usedStages.has(x.id)).map((x) => ({ value: x.id!, label: pick(x, 'name') }));
  const usedTopics = new Set(rows.map((r) => r.topic_id).filter(Boolean));
  const topicOptions = (structure?.stages.find((x) => x.id === filter.stage)?.topics ?? [])
    .filter((x) => usedTopics.has(x.id ?? '')).map((x) => ({ value: x.id!, label: pick(x, 'name') }));
  const hasPlaces = rows.some((r) => r.all_locations || r.location_ids.length > 0);

  const tiles: { key: string; color: string }[] = [
    { key: 'all', color: 'verqac' },
    ...CATEGORIES.filter(([c]) => hasCat(c) && (c !== 'draft' || showDraft) && (c !== 'cancelled' || count(c) > 0))
      .map(([key, color]) => ({ key, color })),
    { key: 'overdue', color: 'red' },
    { key: 'resubmit_overdue', color: 'red' },
  ];

  return (
    <Card withBorder p="sm">
      {(disciplines.size > 1 || kinds.size > 1 || stageOptions.length > 0 || hasPlaces) && (
        <Group mb="sm" gap="lg">
          {disciplines.size > 1 && (
            <Group gap="xs">
              <Text size="sm" c="dimmed">{t('stats.discipline')}</Text>
              <SegmentedControl size="xs" value={filter.discipline}
                onChange={(v) => onChange({ ...filter, discipline: v })}
                data={[{ value: 'all', label: t('stats.allDisciplines') },
                  ...[...disciplines.values()].map((d) => ({ value: d!.code, label: pick(d!, 'name') }))]} />
            </Group>
          )}
          {kinds.size > 1 && (
            <Group gap="xs">
              <Text size="sm" c="dimmed">{t('stats.kind')}</Text>
              <SegmentedControl size="xs" value={filter.kind || 'all'}
                onChange={(v) => onChange({ ...filter, kind: v })}
                data={[{ value: 'all', label: t('stats.allDisciplines') },
                  ...[...kinds.entries()].map(([value, label]) => ({ value, label }))]} />
            </Group>
          )}
          {stageOptions.length > 0 && (
            <Group gap="xs">
              <Text size="sm" c="dimmed">{t('structure.filterStage')}</Text>
              <Select size="xs" w={200} searchable value={filter.stage || 'all'} allowDeselect={false}
                data={[{ value: 'all', label: t('structure.all') }, ...stageOptions]}
                onChange={(v) => onChange({ ...filter, stage: v ?? 'all', topic: 'all' })} />
            </Group>
          )}
          {topicOptions.length > 0 && (
            <Group gap="xs">
              <Text size="sm" c="dimmed">{t('structure.filterTopic')}</Text>
              <Select size="xs" w={180} searchable value={filter.topic || 'all'} allowDeselect={false}
                data={[{ value: 'all', label: t('structure.all') }, ...topicOptions]}
                onChange={(v) => onChange({ ...filter, topic: v ?? 'all' })} />
            </Group>
          )}
          {hasPlaces && structure && (
            <Group gap="xs">
              <Text size="sm" c="dimmed">{t('structure.filterLocation')}</Text>
              <Select size="xs" w={220} searchable value={filter.loc || 'all'} allowDeselect={false}
                data={[{ value: 'all', label: t('structure.all') }, ...(locationOptions(structure, [], true) as never[])]}
                onChange={(v) => onChange({ ...filter, loc: v ?? 'all' })} />
            </Group>
          )}
        </Group>
      )}
      <SimpleGrid cols={{ base: 2, xs: 3, sm: 5, lg: tiles.length }} spacing="xs">
        {tiles.map(({ key, color }) => {
          const n = count(key);
          const active = filter.status === key;
          return (
            <UnstyledButton key={key} onClick={() => onChange({ ...filter, status: active && key !== 'all' ? 'all' : key })}
              aria-pressed={active}
              style={{
                borderRadius: 8, padding: '10px 12px',
                border: `1px solid var(--mantine-color-${color}-${active ? 6 : 2})`,
                background: active ? `var(--mantine-color-${color}-light)` : undefined,
                opacity: n === 0 && !active ? 0.55 : 1,
              }}>
              <Text fz={26} fw={700} lh={1.1} c={key.endsWith('overdue') && n > 0 ? 'red' : `${color}.7`}>{n}</Text>
              <Group gap={6} wrap="nowrap" mt={2}>
                {key !== 'all' && !key.endsWith('overdue') && <Badge size="xs" circle color={color} variant="filled"> </Badge>}
                <Text size="xs" fw={500} c="dimmed" lineClamp={1}>{(key !== 'submitted' && stateName(key)) || t(`stats.${key}`)}</Text>
              </Group>
            </UnstyledButton>
          );
        })}
      </SimpleGrid>
    </Card>
  );
}
