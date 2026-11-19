import { Alert, Badge, Button, Card, Group, Progress, ScrollArea, SegmentedControl, SimpleGrid, Stack, Table, Text, TextInput, Title, Tooltip } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { api, openProtected } from '../api';
import { fmtDate } from '../format';
import { pick } from '../i18n';
import { addDays, daysBetween } from '../programme';

type Named = { name_ar: string; name_en: string };
interface StageRow extends Named { stage_id: string; weight: number; start: number; end: number; planned: number | null;
  locations_ar: string[]; locations_en: string[]; days: number; qty: { qty: number; unit: string }[] }
interface PeriodOut {
  kind: Kind; start: string; end: string; upto: string; prev: string; next: string | null;
  working_days: number; reports: number; pending: number; missing: string[]; stopped: string[]; partial: string[];
  weather: Record<string, number>; progress_start: number; progress_end: number; planned_end: number | null;
  planned_start: number | null; spi: number | null; stages: StageRow[];
  crew_totals: Record<string, { man_days: number; avg: number; peak: number }>;
  crew: { group: string; sub: string | null; name: string; name_en: string | null; man_days: number; days: number; peak: number }[];
  equipment: { name: string; unit_days: number; days: number; hours: number; idle_hours: number }[];
  delays: { cause: string; count: number; hours: number }[];
  delay_items: { day: string; cause: string; hours: number | null; description: string | null }[];
  hse: { incidents: number; near_misses: number; toolbox: number };
  materials: { day: string; material: string; qty: number | null; unit: string | null; supplier: string | null; delivery_note: string | null }[];
  late: { stage_id: string; stage_ar: string; stage_en: string; where_ar: string; where_en: string; planned: number; actual: number; plan_finish: string | null }[];
  requests: (Named & { code: string; submitted: number; answered: number; approved: number; returned: number; open: number; overdue: number })[];
  overdue: { id: string; number: string; title: string; code: string; due_at: string; days: number }[];
}

type Kind = 'week' | 'month' | 'custom';
const GROUPS = ['supervision', 'contractor', 'labour'];
const f1 = (v: number) => (Math.round(v * 10) / 10).toString();

function Kpi({ value, label, color }: { value: string; label: string; color?: string }) {
  return (
    <Card withBorder padding="sm">
      <Text fw={700} size="xl" c={color}>{value}</Text>
      <Text size="xs" c="dimmed">{label}</Text>
    </Card>
  );
}

function Section({ title, children, extra }: { title: string; children: React.ReactNode; extra?: React.ReactNode }) {
  return (
    <Card withBorder>
      <Group justify="space-between" mb="xs"><Title order={5}>{title}</Title>{extra}</Group>
      <ScrollArea type="auto" scrollbars="x">{children}</ScrollArea>
    </Card>
  );
}

/** Weekly / monthly report, put together from the approved daily reports. */
export default function PeriodicPanel({ projectId }: { projectId: string }) {
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const [kind, setKind] = useState<Kind>('week');
  const [day, setDay] = useState<string | null>(null);
  const [range, setRange] = useState<{ from: string; to: string }>({ from: '', to: '' });
  const valid = kind !== 'custom' || (!!range.from && !!range.to && range.to >= range.from && daysBetween(range.from, range.to) < 400);
  const qs = kind === 'custom' ? `kind=custom&start=${range.from}&end=${range.to}` : `kind=${kind}${day ? `&day=${day}` : ''}`;
  const q = useQuery({
    queryKey: ['period', projectId, qs],
    queryFn: () => api<PeriodOut>(`/projects/${projectId}/period-report?${qs}`),
    enabled: valid, placeholderData: (prev) => prev,
  });
  const o = valid ? q.data : undefined;
  const len = o ? daysBetween(o.start, o.end) + 1 : 0;
  const go = (to: string) => (kind === 'custom' ? setRange({ from: to, to: addDays(to, len - 1) }) : setDay(to));
  const lang = i18n.language === 'en' ? 'en' : 'ar';
  const dates = (xs: string[]) => xs.map((d) => fmtDate(d)).join(' · ');
  const pdf = (l: string) => openProtected(`/projects/${projectId}/period-report/pdf?${kind === 'custom' ? qs : `kind=${kind}&day=${o?.start ?? ''}`}&lang=${l}`,
    `${kind === 'week' ? 'weekly' : kind === 'month' ? 'monthly' : 'period'}-${o?.start}.pdf`, true);

  return (
    <Stack>
      <Group justify="space-between">
        <Group gap="xs">
          <SegmentedControl size="xs" value={kind} onChange={(v) => {
            if (v === 'custom' && o) setRange({ from: o.start, to: o.end });
            setKind(v as Kind); setDay(null);
          }}
            data={[{ value: 'week', label: t('per.week') }, { value: 'month', label: t('per.month') }, { value: 'custom', label: t('per.custom') }]} />
          <Button size="xs" variant="default" disabled={!o} onClick={() => o && go(o.prev)}>{t('per.prev')}</Button>
          {kind === 'custom' ? (
            <>
              <TextInput size="xs" type="date" w={150} value={range.from} error={!valid} max={new Date().toISOString().slice(0, 10)}
                onChange={(e) => setRange({ ...range, from: e.currentTarget.value })} leftSection={<Text size="xs">{t('gantt.from')}</Text>} leftSectionWidth={36} />
              <TextInput size="xs" type="date" w={150} value={range.to} error={!valid}
                onChange={(e) => setRange({ ...range, to: e.currentTarget.value })} leftSection={<Text size="xs">{t('gantt.to')}</Text>} leftSectionWidth={36} />
            </>
          ) : <Text fw={600} size="sm">{o ? `${fmtDate(o.start)} — ${fmtDate(o.end)}` : ''}</Text>}
          <Button size="xs" variant="default" disabled={!o?.next} onClick={() => o?.next && go(o.next)}>{t('per.next')}</Button>
          {day && kind !== 'custom' && <Button size="xs" variant="subtle" onClick={() => setDay(null)}>{t('per.current')}</Button>}
        </Group>
        <Group gap="xs">
          <Button size="xs" variant="light" disabled={!o} onClick={() => pdf('ar')}>PDF عربي</Button>
          <Button size="xs" variant="light" disabled={!o} onClick={() => pdf('en')}>PDF English</Button>
        </Group>
      </Group>
      {!valid && <Text size="xs" c="red">{t('per.badRange')}</Text>}
      {o && o.upto < o.end && <Text size="xs" c="dimmed">{t('per.upto', { date: fmtDate(o.upto) })}</Text>}
      <Text size="xs" c="dimmed">{t('per.hint')}</Text>
      {o && (
        <>
          <SimpleGrid cols={{ base: 2, sm: 4 }}>
            <Kpi value={`${f1(o.progress_end)}%`} label={t('per.pEnd') + (o.planned_end != null ? ` · ${t('per.planned')} ${f1(o.planned_end)}%` : '')} />
            <Kpi value={`+${f1(o.progress_end - o.progress_start)}%`} color="green"
              label={t('per.pDelta') + (o.planned_end != null && o.planned_start != null ? ` · ${t('per.planned')} +${f1(o.planned_end - o.planned_start)}%` : '')} />
            <Kpi value={o.spi != null ? String(o.spi) : '—'} color={o.spi != null && o.spi < 0.95 ? 'red' : undefined} label={o.spi != null ? 'SPI' : t('per.noPrg')} />
            <Kpi value={`${o.reports} / ${o.working_days}`} color={o.missing.length ? 'red' : undefined} label={t('per.reports')} />
          </SimpleGrid>
          {o.missing.length > 0 && <Alert color="red" py="xs">{t('per.missing', { n: o.missing.length })}: {dates(o.missing)}</Alert>}
          {o.pending > 0 && <Alert color="yellow" py="xs">{t('per.pending', { n: o.pending })}</Alert>}
          {(o.stopped.length > 0 || o.partial.length > 0 || Object.keys(o.weather).length > 0) && (
            <Group gap="lg">
              {o.stopped.length > 0 && <Text size="sm">{t('per.stopped')}: <b>{o.stopped.length}</b> ({dates(o.stopped)})</Text>}
              {o.partial.length > 0 && <Text size="sm">{t('per.partial')}: <b>{o.partial.length}</b></Text>}
              {Object.keys(o.weather).length > 0 && <Text size="sm">{t('daily.weather')}: {Object.entries(o.weather).sort((a, b) => b[1] - a[1])
                .map(([k, n]) => `${t(`daily.v.${k}`)} ${n}`).join(' · ')}</Text>}
            </Group>
          )}

          <Section title={t('per.progress')}>
            {o.stages.length === 0 ? <Text size="sm" c="dimmed">{t('per.none')}</Text> : (
              <Table striped withTableBorder fz="sm" miw={760}>
                <Table.Thead><Table.Tr>
                  <Table.Th>{t('per.stage')}</Table.Th><Table.Th ta="center">{t('per.pStart')}</Table.Th><Table.Th ta="center">{t('per.pEnd')}</Table.Th>
                  {o.planned_end != null && <Table.Th ta="center">{t('per.planned')}</Table.Th>}
                  <Table.Th w={160} /><Table.Th>{t('per.where')}</Table.Th><Table.Th>{t('per.qty')}</Table.Th>
                </Table.Tr></Table.Thead>
                <Table.Tbody>
                  {o.stages.map((s) => (
                    <Table.Tr key={s.stage_id}>
                      <Table.Td>{pick(s, 'name')} <Text span size="xs" c="dimmed">({s.weight}%)</Text></Table.Td>
                      <Table.Td ta="center">{f1(s.start)}%</Table.Td>
                      <Table.Td ta="center">{f1(s.end)}%{s.end > s.start && <Text span c="green" fw={600} size="xs"> +{f1(s.end - s.start)}</Text>}</Table.Td>
                      {o.planned_end != null && <Table.Td ta="center" c={s.planned != null && s.end + 10 < s.planned ? 'red' : undefined}>{s.planned != null ? `${f1(s.planned)}%` : ''}</Table.Td>}
                      <Table.Td>
                        <Tooltip label={`${f1(s.start)}% → ${f1(s.end)}%`}>
                          <Progress.Root size="md"><Progress.Section value={s.start} color="blue" /><Progress.Section value={Math.max(0, s.end - s.start)} color="green" /></Progress.Root>
                        </Tooltip>
                      </Table.Td>
                      <Table.Td fz="xs">{(lang === 'en' ? s.locations_en : s.locations_ar).join(lang === 'en' ? ', ' : '، ')}</Table.Td>
                      <Table.Td fz="xs" dir="ltr" ta="start">{s.qty.map((x) => `${x.qty} ${x.unit}`.trim()).join(' · ')}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Section>

          {o.late.length > 0 && (
            <Section title={t('per.late', { n: o.late.length })}>
              <Table striped withTableBorder fz="sm" miw={560}>
                <Table.Thead><Table.Tr><Table.Th>{t('per.stage')}</Table.Th><Table.Th>{t('per.location')}</Table.Th>
                  <Table.Th ta="center">{t('per.planned')}</Table.Th><Table.Th ta="center">{t('per.actual')}</Table.Th><Table.Th ta="center">{t('per.finish')}</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>{o.late.map((r, i) => (
                  <Table.Tr key={i}><Table.Td>{lang === 'en' ? r.stage_en : r.stage_ar}</Table.Td><Table.Td>{lang === 'en' ? r.where_en : r.where_ar}</Table.Td>
                    <Table.Td ta="center">{f1(r.planned)}%</Table.Td><Table.Td ta="center" c="red" fw={600}>{f1(r.actual)}%</Table.Td>
                    <Table.Td ta="center">{fmtDate(r.plan_finish)}</Table.Td></Table.Tr>
                ))}</Table.Tbody>
              </Table>
            </Section>
          )}

          <SimpleGrid cols={{ base: 1, md: 2 }}>
            <Section title={t('per.crew')}>
              <Table withTableBorder fz="sm">
                <Table.Thead><Table.Tr><Table.Th /><Table.Th ta="center">{t('per.manDays')}</Table.Th><Table.Th ta="center">{t('per.avg')}</Table.Th><Table.Th ta="center">{t('per.peak')}</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>{GROUPS.map((g) => o.crew_totals[g] && (
                  <Table.Tr key={g}><Table.Td fw={600}>{t(`daily.g.${g}`)}</Table.Td><Table.Td ta="center">{o.crew_totals[g].man_days}</Table.Td>
                    <Table.Td ta="center">{o.crew_totals[g].avg}</Table.Td><Table.Td ta="center">{o.crew_totals[g].peak}</Table.Td></Table.Tr>
                ))}</Table.Tbody>
              </Table>
              {o.crew.length > 0 && (
                <Table striped withTableBorder fz="xs" mt="xs">
                  <Table.Thead><Table.Tr><Table.Th /><Table.Th>{t('per.sub')}</Table.Th><Table.Th>{t('per.name')}</Table.Th>
                    <Table.Th ta="center">{t('per.manDays')}</Table.Th><Table.Th ta="center">{t('per.days')}</Table.Th><Table.Th ta="center">{t('per.peak')}</Table.Th></Table.Tr></Table.Thead>
                  <Table.Tbody>{o.crew.map((r, i) => (
                    <Table.Tr key={i}><Table.Td>{t(`daily.g.${r.group}`)}</Table.Td><Table.Td>{r.sub ?? ''}</Table.Td>
                      <Table.Td>{lang === 'en' ? r.name_en || r.name : r.name}</Table.Td><Table.Td ta="center">{r.man_days}</Table.Td>
                      <Table.Td ta="center">{r.days}</Table.Td><Table.Td ta="center">{r.peak}</Table.Td></Table.Tr>
                  ))}</Table.Tbody>
                </Table>
              )}
            </Section>
            <Stack>
              {o.equipment.length > 0 && (
                <Section title={t('daily.equipment')}>
                  <Table striped withTableBorder fz="sm">
                    <Table.Thead><Table.Tr><Table.Th>{t('per.name')}</Table.Th><Table.Th ta="center">{t('per.unitDays')}</Table.Th>
                      <Table.Th ta="center">{t('daily.hours')}</Table.Th><Table.Th ta="center">{t('daily.idle')}</Table.Th></Table.Tr></Table.Thead>
                    <Table.Tbody>{o.equipment.map((r) => (
                      <Table.Tr key={r.name}><Table.Td>{r.name}</Table.Td><Table.Td ta="center">{r.unit_days}</Table.Td>
                        <Table.Td ta="center">{r.hours}</Table.Td><Table.Td ta="center" c={r.idle_hours ? 'red' : undefined}>{r.idle_hours}</Table.Td></Table.Tr>
                    ))}</Table.Tbody>
                  </Table>
                </Section>
              )}
              <Section title={t('daily.hse')}>
                <Group gap="xl">
                  <Text size="sm">{t('daily.incidents')}: <Text span fw={700} c={o.hse.incidents ? 'red' : undefined}>{o.hse.incidents}</Text></Text>
                  <Text size="sm">{t('daily.near_misses')}: <b>{o.hse.near_misses}</b></Text>
                  <Text size="sm">{t('daily.toolbox')}: <b>{o.hse.toolbox}</b></Text>
                </Group>
              </Section>
              {o.delays.length > 0 && (
                <Section title={t('daily.delays')}>
                  <Table withTableBorder fz="sm">
                    <Table.Tbody>{o.delays.map((r) => (
                      <Table.Tr key={r.cause}><Table.Td>{t(`daily.cause.${r.cause}`)}</Table.Td><Table.Td ta="center">{t('per.times', { n: r.count })}</Table.Td>
                        <Table.Td ta="center">{r.hours} {t('per.h')}</Table.Td></Table.Tr>
                    ))}</Table.Tbody>
                  </Table>
                  <Stack gap={2} mt="xs">{o.delay_items.filter((x) => x.description).map((x, i) => (
                    <Text key={i} size="xs"><b>{fmtDate(x.day)}</b> · {t(`daily.cause.${x.cause}`)}: {x.description}</Text>
                  ))}</Stack>
                </Section>
              )}
            </Stack>
          </SimpleGrid>

          <Section title={t('per.requests')}>
            {o.requests.length === 0 ? <Text size="sm" c="dimmed">{t('per.none')}</Text> : (
              <Table striped withTableBorder fz="sm" miw={600}>
                <Table.Thead><Table.Tr><Table.Th>{t('per.type')}</Table.Th>
                  {(['submitted', 'answered', 'approved', 'returned', 'open', 'overdue'] as const).map((k) => <Table.Th key={k} ta="center">{t(`per.r.${k}`)}</Table.Th>)}
                </Table.Tr></Table.Thead>
                <Table.Tbody>{o.requests.map((r) => (
                  <Table.Tr key={r.code}><Table.Td>{pick(r, 'name')}</Table.Td><Table.Td ta="center">{r.submitted}</Table.Td><Table.Td ta="center">{r.answered}</Table.Td>
                    <Table.Td ta="center">{r.approved}</Table.Td><Table.Td ta="center">{r.returned}</Table.Td><Table.Td ta="center">{r.open}</Table.Td>
                    <Table.Td ta="center">{r.overdue ? <Badge color="red">{r.overdue}</Badge> : 0}</Table.Td></Table.Tr>
                ))}</Table.Tbody>
              </Table>
            )}
            {o.overdue.length > 0 && (
              <Table withTableBorder fz="xs" mt="xs" highlightOnHover>
                <Table.Thead><Table.Tr><Table.Th>{t('per.number')}</Table.Th><Table.Th>{t('per.title')}</Table.Th>
                  <Table.Th ta="center">{t('per.due')}</Table.Th><Table.Th ta="center">{t('per.lateBy')}</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>{o.overdue.map((r) => (
                  <Table.Tr key={r.id} style={{ cursor: 'pointer' }} onClick={() => nav(`/records/${r.id}`)}>
                    <Table.Td dir="ltr" ta="start">{r.number}</Table.Td><Table.Td>{r.title}</Table.Td>
                    <Table.Td ta="center">{fmtDate(r.due_at)}</Table.Td><Table.Td ta="center" c="red" fw={600}>{r.days}</Table.Td></Table.Tr>
                ))}</Table.Tbody>
              </Table>
            )}
          </Section>

          {o.materials.length > 0 && (
            <Section title={t('per.materials')}>
              <Table striped withTableBorder fz="sm" miw={560}>
                <Table.Thead><Table.Tr><Table.Th>{t('per.date')}</Table.Th><Table.Th>{t('daily.material')}</Table.Th><Table.Th ta="center">{t('daily.qty')}</Table.Th>
                  <Table.Th>{t('daily.supplier')}</Table.Th><Table.Th>{t('daily.dn')}</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>{o.materials.map((r, i) => (
                  <Table.Tr key={i}><Table.Td>{fmtDate(r.day)}</Table.Td><Table.Td>{r.material}</Table.Td>
                    <Table.Td ta="center">{r.qty ?? ''} {r.unit ?? ''}</Table.Td><Table.Td>{r.supplier ?? ''}</Table.Td><Table.Td>{r.delivery_note ?? ''}</Table.Td></Table.Tr>
                ))}</Table.Tbody>
              </Table>
            </Section>
          )}
        </>
      )}
    </Stack>
  );
}
