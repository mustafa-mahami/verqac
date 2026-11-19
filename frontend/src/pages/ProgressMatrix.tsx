import { Badge, Button, Card, Group, RingProgress, ScrollArea, SegmentedControl, SimpleGrid, Stack, Table, Text, Title, Tooltip } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Fragment, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { api, type ProjectSettings } from '../api';
import type { CellStatus, ProgressCell, ProgressOut } from '../daily';
import { fmtDate } from '../format';
import { pick } from '../i18n';
import { cellKey, cpm, type ProgrammeOut, type ProgrammeSummary } from '../programme';
import { useStructure } from './Structure';
import Gantt, { type GanttItem } from './Gantt';

const shade = (p: number) => (p >= 100 ? 'var(--mantine-color-green-6)' : p > 0 ? `color-mix(in srgb, var(--mantine-color-green-6) ${Math.max(15, p)}%, white)` : 'transparent');
const STATUS: Record<CellStatus, string> = {
  done: 'var(--mantine-color-green-6)', on_track: 'color-mix(in srgb, var(--mantine-color-green-6) 35%, white)',
  ahead: 'color-mix(in srgb, var(--mantine-color-blue-6) 35%, white)', late: 'color-mix(in srgb, var(--mantine-color-red-6) 40%, white)',
  not_started: 'transparent',
};

type Pt = { day: string; v: number };
/** S-curve: actual (solid), current programme (dashed) and baseline (dotted, when it differs). */
function Curve({ actual, plan, base }: { actual: Pt[]; plan: Pt[]; base: Pt[] }) {
  const all = [...actual, ...plan, ...base];
  if (all.length < 2) return null;
  const w = 600, h = 170, pad = 24;
  const ts = all.map((p) => new Date(p.day).getTime());
  const t0 = Math.min(...ts), t1 = Math.max(...ts);
  const x = (d: string) => pad + ((new Date(d).getTime() - t0) / (t1 - t0 || 1)) * (w - 2 * pad);
  const y = (v: number) => h - pad - (v / 100) * (h - 2 * pad);
  const line = (ps: Pt[]) => ps.map((p) => `${x(p.day)},${y(p.v)}`).join(' ');
  const today = new Date().toISOString().slice(0, 10);
  const tt = new Date(today).getTime();
  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: '100%', maxWidth: w, direction: 'ltr' }}>
      {[0, 25, 50, 75, 100].map((v) => <g key={v}><line x1={pad} x2={w - pad} y1={y(v)} y2={y(v)} stroke="#e3e6ea" /><text x={2} y={y(v) + 4} fontSize="9" fill="#888">{v}</text></g>)}
      {tt >= t0 && tt <= t1 && <line x1={x(today)} x2={x(today)} y1={pad / 2} y2={h - pad} stroke="#d9480f" strokeDasharray="3 2" />}
      {base.length > 1 && <polyline points={line(base)} fill="none" stroke="#adb5bd" strokeDasharray="1 3" strokeWidth="2" />}
      {plan.length > 1 && <polyline points={line(plan)} fill="none" stroke="#868e96" strokeDasharray="5 3" strokeWidth="2" />}
      {actual.length > 1 && <polyline points={line(actual)} fill="none" stroke="var(--mantine-color-verqac-6)" strokeWidth="2.5" />}
      {actual.length === 1 && <circle cx={x(actual[0].day)} cy={y(actual[0].v)} r={3} fill="var(--mantine-color-verqac-6)" />}
    </svg>
  );
}

/** The programme: its approved revisions, and creating or updating it. */
function ProgrammeCard({ projectId, p }: { projectId: string; p: ProgressOut }) {
  const { t } = useTranslation();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ['programmeSummary', projectId], queryFn: () => api<ProgrammeSummary>(`/projects/${projectId}/programme`) });
  const create = useMutation({
    mutationFn: () => api<{ id: string }>(`/projects/${projectId}/programme`, { method: 'POST' }),
    onSuccess: (r) => nav(`/records/${r.id}`),
  });
  const s = q.data;
  if (!s) return null;
  const latest = s.revisions[0];
  const pending = latest && latest.id !== s.current_id ? latest : null;
  const cur = s.revisions.find((r) => r.id === s.current_id);
  return (
    <Card withBorder>
      <Group justify="space-between" align="flex-start">
        <div>
          <Title order={5}>{t('prg.title')}</Title>
          <Text size="sm" c="dimmed">
            {cur ? t('prg.current', { rev: cur.rev_no, from: fmtDate(p.plan_start), to: fmtDate(p.plan_finish) }) : t('prg.none')}
          </Text>
          {p.baseline_finish && p.baseline_finish !== p.plan_finish && (
            <Text size="xs" c={p.plan_finish && p.plan_finish > p.baseline_finish ? 'red' : 'dimmed'}>
              {t('prg.baselineFinish', { date: fmtDate(p.baseline_finish) })}
            </Text>
          )}
        </div>
        <Group gap="xs">
          {pending && <Button size="xs" variant="light" onClick={() => nav(`/records/${pending.id}`)}>
            {t('prg.openPending', { rev: pending.rev_no })} <Badge ms={6} size="xs" variant="white">{pick(pending, 'state_name')}</Badge></Button>}
          {cur && <Button size="xs" variant="subtle" onClick={() => nav(`/records/${cur.id}`)}>{t('prg.openCurrent')}</Button>}
          {s.can_create && <Button size="xs" loading={create.isPending} onClick={() => create.mutate()}>{t('prg.create')}</Button>}
        </Group>
      </Group>
    </Card>
  );
}

/** Progress of every stage at every floor, the project %, against the approved programme. Only approved daily reports count. */
export default function ProgressMatrix({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ['progress', projectId], queryFn: () => api<ProgressOut>(`/projects/${projectId}/progress`) });
  const s = useStructure(projectId).data;
  const qc = useQueryClient();
  const prg = useQuery({ queryKey: ['programme', q.data?.programme_id], enabled: !!q.data?.programme_id,
    queryFn: () => api<ProgrammeOut>(`/records/${q.data!.programme_id}/programme`) });
  const [view, setView] = useState<'actual' | 'status' | 'gantt'>('actual');
  const settings = useQuery({ queryKey: ['settings', projectId], queryFn: () => api<ProjectSettings>(`/projects/${projectId}/settings`) });
  const rebuild = useMutation({
    mutationFn: () => api<ProgressOut>(`/projects/${projectId}/progress/rebuild`, { method: 'POST' }),
    onSuccess: (d) => qc.setQueryData(['progress', projectId], d),
  });
  if (!q.data || !s) return null;
  const p = q.data;
  const stages = s.stages.filter((x) => x.is_active);
  const groups = s.locations.filter((g) => g.is_active).map((g) => ({ g, units: g.units.filter((u) => u.is_active) }));
  const units = groups.flatMap((x) => x.units);
  const cell = (sid: string, lid: string | null) => p.cells.find((c) => c.stage_id === sid && c.location_id === lid);
  const hasPlan = p.planned !== null;
  const byStatus = view === 'status' && hasPlan;
  if (!stages.length) return <Text c="dimmed">{t('progress.noStages')}</Text>;
  const tip = (c: ProgressCell | undefined) => {
    if (!c) return '';
    const parts = [`${t('progress.actual')}: ${c.progress}%`];
    if (c.planned !== null) parts.push(`${t('progress.plannedNow')}: ${c.planned}%`, `${t('prg.start')}: ${fmtDate(c.plan_start)} · ${t('prg.finish')}: ${fmtDate(c.plan_finish)}`);
    if (c.status) parts.push(t(`progress.status.${c.status}`));
    if (c.progress_on) parts.push(`${t('progress.updated')}: ${fmtDate(c.progress_on)}`);
    return parts.join(' — ');
  };
  const td = (c: ProgressCell | undefined, span?: number) => {
    const worked = !!c && (c.progress > 0 || !!c.started_on);
    const bg = byStatus ? STATUS[c?.status ?? 'not_started'] : shade(c?.progress ?? 0);
    const dark = !byStatus && (c?.progress ?? 0) >= 60;
    const label = byStatus && c?.planned !== null && c?.planned !== undefined
      ? (worked || c.planned > 0 ? `${c.progress}/${c.planned}` : '') : worked ? `${c!.progress}%` : '';
    return (
      <Tooltip disabled={!c || (!worked && c.planned === null)} label={tip(c)} multiline w={260}>
        <Table.Td colSpan={span} ta="center" style={{ background: bg, color: dark ? 'white' : undefined }}>{label}</Table.Td>
      </Tooltip>
    );
  };
  const now = new Date().toISOString().slice(0, 10);
  const wholeSet = new Set(stages.filter((x) => x.scope === 'whole' || !units.length).map((x) => x.id!));
  const floats = prg.data?.cycles.length ? cpm(prg.data.lines, prg.data.cycles, units.map((u) => u.id!), wholeSet) : null;
  const ganttItems: GanttItem[] = p.cells.filter((c) => stages.some((x) => x.id === c.stage_id)).map((c) => {
    const st = stages.find((x) => x.id === c.stage_id)!;
    const started = c.progress > 0 || !!c.started_on;
    const status: NonNullable<GanttItem['actual']>['status'] = started ? (c.status ?? 'on_track') : c.plan_start && c.plan_start <= now ? 'late_start' : 'not_due';
    return {
      stageId: c.stage_id, stageName: pick(st, 'name'), locId: c.location_id, weight: Number(st.weight),
      locName: c.location_id ? pick(units.find((u) => u.id === c.location_id) ?? { name_ar: '', name_en: '' }, 'name') : null,
      plan: c.plan_start && c.plan_finish ? { start: c.plan_start, finish: c.plan_finish } : null,
      base: c.base_start && c.base_finish ? { start: c.base_start, finish: c.base_finish } : null,
      actual: { start: c.started_on, finish: c.finished_on, pct: c.progress, status },
      float: floats ? floats.get(cellKey(c.stage_id, c.location_id)) ?? null : null,
      unlinked: !!prg.data && !prg.data.cycles.find((x) => x.stage_id === c.stage_id && x.pred),
    };
  }).sort((a, b) => stages.findIndex((x) => x.id === a.stageId) - stages.findIndex((x) => x.id === b.stageId)
    || units.findIndex((u) => u.id === a.locId) - units.findIndex((u) => u.id === b.locId));
  const stageName = (id: string) => pick(stages.find((x) => x.id === id) ?? { name_ar: '', name_en: '' }, 'name');
  const unitName = (id: string | null) => (id ? pick(units.find((u) => u.id === id) ?? { name_ar: '', name_en: '' }, 'name') : t('structure.whole'));
  return (
    <Stack>
      <ProgrammeCard projectId={projectId} p={p} />
      <Card withBorder>
        <Group align="center" gap="xl">
          <RingProgress size={130} thickness={12} roundCaps
            sections={[{ value: p.project, color: 'verqac' }]}
            label={<Text ta="center" fw={700} size="xl">{p.project}%</Text>} />
          <div>
            <Title order={4}>{t('progress.project')}</Title>
            <Text size="sm" c="dimmed">{p.as_of ? t('progress.asOf', { date: fmtDate(p.as_of) }) : t('progress.none')}</Text>
            {hasPlan && (
              <SimpleGrid cols={3} mt="xs" spacing="lg">
                <div><Text size="xs" c="dimmed">{t('progress.plannedNow')}</Text><Text fw={700}>{p.planned}%</Text></div>
                <div><Text size="xs" c="dimmed">{t('progress.variance')}</Text>
                  <Text fw={700} c={p.project - (p.planned ?? 0) < 0 ? 'red' : 'green'}>{(p.project - (p.planned ?? 0)).toFixed(1)}%</Text></div>
                <div><Tooltip label={t('progress.spiHint')} multiline w={260}><Text size="xs" c="dimmed">SPI</Text></Tooltip>
                  <Text fw={700} c={p.spi !== null && p.spi < 0.9 ? 'red' : p.spi !== null && p.spi >= 1 ? 'green' : undefined}>{p.spi ?? '—'}</Text></div>
              </SimpleGrid>
            )}
            {p.planned_baseline !== null && <Text size="xs" c="dimmed" mt={4}>{t('progress.plannedBaseline', { v: p.planned_baseline })}</Text>}
            <Text size="xs" c="dimmed" mt={4}>{t('progress.hint')}</Text>
          </div>
          <div style={{ flex: 1, minWidth: 260 }}>
            <Curve actual={p.snapshots.map((x) => ({ day: x.day, v: x.actual }))}
              plan={p.plan_curve.map((x) => ({ day: x.day, v: x.planned }))} base={p.baseline_curve.map((x) => ({ day: x.day, v: x.planned }))} />
            {hasPlan && (
              <Group gap="md" justify="center">
                <Text size="xs"><span style={{ color: 'var(--mantine-color-verqac-6)' }}>━</span> {t('progress.actual')}</Text>
                <Text size="xs"><span style={{ color: '#868e96' }}>╍</span> {t('progress.planned')}</Text>
                {p.baseline_curve.length > 0 && <Text size="xs"><span style={{ color: '#adb5bd' }}>┈</span> {t('progress.baseline')}</Text>}
              </Group>
            )}
          </div>
        </Group>
        {settings.data?.can_edit && (
          <Group justify="flex-end" mt="xs">
            <Tooltip label={t('progress.rebuildHint')} multiline w={300}>
              <Button size="xs" variant="subtle" loading={rebuild.isPending}
                onClick={() => window.confirm(t('progress.rebuildConfirm')) && rebuild.mutate()}>{t('progress.rebuild')}</Button>
            </Tooltip>
          </Group>
        )}
      </Card>
      {(
        <Group justify="space-between">
          <SegmentedControl size="xs" value={view} onChange={(v) => setView(v as 'actual' | 'status' | 'gantt')}
            data={[{ value: 'actual', label: t('progress.viewActual') }, ...(hasPlan ? [{ value: 'status', label: t('progress.viewStatus') }] : []), { value: 'gantt', label: t('progress.viewGantt') }]} />
          {byStatus && (
            <Group gap="sm">
              {(['late', 'on_track', 'ahead', 'done'] as CellStatus[]).map((k) => (
                <Group key={k} gap={4}><span style={{ width: 12, height: 12, background: STATUS[k], border: '1px solid #ddd', display: 'inline-block' }} />
                  <Text size="xs">{t(`progress.status.${k}`)}</Text></Group>
              ))}
            </Group>
          )}
        </Group>
      )}
      {view === 'gantt' ? (
        <Card withBorder><Gantt items={ganttItems} showActual /></Card>
      ) : (
      <Card withBorder p={0}>
        <ScrollArea>
          <Table withColumnBorders withTableBorder fz="xs" miw={300 + units.length * 70} verticalSpacing={4}>
            <Table.Thead>
              {groups.length > 1 && (
                <Table.Tr>
                  <Table.Th colSpan={hasPlan ? 4 : 3} />
                  {groups.map(({ g, units: us }) => <Table.Th key={g.id} colSpan={us.length} ta="center">{pick(g, 'name')}</Table.Th>)}
                </Table.Tr>
              )}
              <Table.Tr>
                <Table.Th miw={170}>{t('structure.stage')}</Table.Th><Table.Th w={60}>{t('progress.weight')}</Table.Th><Table.Th miw={80}>{t('progress.stage')}</Table.Th>
                {hasPlan && <Table.Th miw={70}>{t('progress.planned')}</Table.Th>}
                {units.map((u) => <Table.Th key={u.id} ta="center" miw={64}>{pick(u, 'name')}</Table.Th>)}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {stages.map((st) => {
                const a = p.stages[st.id!] ?? 0, pl = p.planned_stages[st.id!];
                return (
                  <Table.Tr key={st.id}>
                    <Table.Td fw={600}>{pick(st, 'name')}</Table.Td>
                    <Table.Td ta="center">{Number(st.weight)}%</Table.Td>
                    <Table.Td ta="center" style={{ whiteSpace: 'nowrap' }}>
                      <Text size="xs" fw={700} c={hasPlan && pl !== undefined && a + 10 < pl ? 'red' : undefined}>{a}%</Text>
                    </Table.Td>
                    {hasPlan && <Table.Td ta="center"><Text size="xs" c="dimmed">{pl !== undefined ? `${pl}%` : ''}</Text></Table.Td>}
                    {st.scope === 'whole' || !units.length ? td(cell(st.id!, null), units.length || 1) : units.map((u) => <Fragment key={u.id}>{td(cell(st.id!, u.id!))}</Fragment>)}
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      </Card>
      )}
      {p.late.length > 0 && (
        <Card withBorder>
          <Title order={5} mb="xs">{t('progress.lateTitle', { n: p.late.length })}</Title>
          <Table verticalSpacing={4} fz="sm">
            <Table.Thead><Table.Tr>
              <Table.Th>{t('structure.stage')}</Table.Th><Table.Th>{t('prg.location')}</Table.Th>
              <Table.Th>{t('progress.actual')}</Table.Th><Table.Th>{t('progress.plannedNow')}</Table.Th><Table.Th>{t('progress.gap')}</Table.Th>
              <Table.Th>{t('prg.finish')}</Table.Th>
            </Table.Tr></Table.Thead>
            <Table.Tbody>
              {p.late.map((c) => (
                <Table.Tr key={`${c.stage_id}${c.location_id}`}>
                  <Table.Td>{stageName(c.stage_id)} {floats && (floats.get(cellKey(c.stage_id, c.location_id)) ?? 1) <= 0 && <Badge size="xs" color="red" variant="light">{t('gantt.criticalPath')}</Badge>}</Table.Td><Table.Td>{unitName(c.location_id)}</Table.Td>
                  <Table.Td>{c.progress}%</Table.Td><Table.Td>{c.planned}%</Table.Td>
                  <Table.Td><Text size="sm" c="red" fw={600}>{(c.progress - (c.planned ?? 0)).toFixed(0)}%</Text></Table.Td>
                  <Table.Td>{fmtDate(c.plan_finish)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Card>
      )}
    </Stack>
  );
}

