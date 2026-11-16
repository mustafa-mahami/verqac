import { Badge, Card, Group, SegmentedControl, SimpleGrid, Text, UnstyledButton } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import type { RecordRow } from '../api';
import { pick } from '../i18n';

/** State categories in workflow order, with the colours the states use. Same for every record type. */
export const CATEGORIES = [
  ['draft', 'gray'], ['submitted', 'blue'], ['approved', 'green'], ['approved_as_noted', 'teal'],
  ['revise_and_resubmit', 'orange'], ['rejected', 'red'], ['cancelled', 'dark'],
] as const;

export interface StatsFilter {
  status: string; discipline: string;
  q?: string; from?: string; to?: string; // text in number/title; submission date range (YYYY-MM-DD, inclusive)
}

/** Local calendar day of a timestamp, as YYYY-MM-DD. */
const dayOf = (iso: string) => { const d = new Date(iso); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };

/** Which rows a filter keeps: status is "all", "overdue" or a state category; discipline is a code or "all". */
export function applyFilter(rows: RecordRow[], f: StatsFilter, ignoreStatus = false): RecordRow[] {
  const q = (f.q ?? '').trim().toLowerCase();
  return rows.filter((r) => {
    if (f.discipline !== 'all' && r.discipline?.code !== f.discipline) return false;
    if (q && !r.number.toLowerCase().includes(q) && !r.title.toLowerCase().includes(q)) return false;
    if (f.from || f.to) {
      if (!r.submitted_at) return false; // drafts were not submitted in any period
      const day = dayOf(r.submitted_at);
      if ((f.from && day < f.from) || (f.to && day > f.to)) return false;
    }
    if (ignoreStatus || f.status === 'all') return true;
    return f.status === 'overdue' ? r.overdue : r.state.category === f.status;
  });
}

/**
 * Register dashboard: one tile per state category with its count, plus all and overdue.
 * A tile filters the list below; a discipline switch appears when the list spans several disciplines.
 */
export default function RecordStats({ rows, filter, onChange, showDraft }: {
  rows: RecordRow[]; filter: StatsFilter; onChange: (f: StatsFilter) => void; showDraft: boolean;
}) {
  const { t } = useTranslation();
  const disciplines = new Map<string, RecordRow['discipline']>();
  rows.forEach((r) => r.discipline && disciplines.set(r.discipline.code, r.discipline));
  const inScope = applyFilter(rows, filter, true);
  const count = (status: string) => applyFilter(inScope, { ...filter, status }).length;

  const tiles: { key: string; color: string }[] = [
    { key: 'all', color: 'verqac' },
    ...CATEGORIES.filter(([c]) => (c !== 'draft' || showDraft) && (c !== 'cancelled' || count(c) > 0))
      .map(([key, color]) => ({ key, color })),
    { key: 'overdue', color: 'red' },
  ];

  return (
    <Card withBorder p="sm">
      {disciplines.size > 1 && (
        <Group mb="sm" gap="xs">
          <Text size="sm" c="dimmed">{t('stats.discipline')}</Text>
          <SegmentedControl size="xs" value={filter.discipline}
            onChange={(v) => onChange({ ...filter, discipline: v })}
            data={[{ value: 'all', label: t('stats.allDisciplines') },
              ...[...disciplines.values()].map((d) => ({ value: d!.code, label: pick(d!, 'name') }))]} />
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
              <Text fz={26} fw={700} lh={1.1} c={key === 'overdue' && n > 0 ? 'red' : `${color}.7`}>{n}</Text>
              <Group gap={6} wrap="nowrap" mt={2}>
                {key !== 'all' && key !== 'overdue' && <Badge size="xs" circle color={color} variant="filled"> </Badge>}
                <Text size="xs" fw={500} c="dimmed" lineClamp={1}>{t(`stats.${key}`)}</Text>
              </Group>
            </UnstyledButton>
          );
        })}
      </SimpleGrid>
    </Card>
  );
}
