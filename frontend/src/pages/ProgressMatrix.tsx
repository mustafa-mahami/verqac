import { Button, Card, Group, RingProgress, ScrollArea, Stack, Table, Text, Title, Tooltip } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api, type ProjectSettings } from '../api';
import type { ProgressOut } from '../daily';
import { fmtDate } from '../format';
import { pick } from '../i18n';
import { useStructure } from './Structure';

const shade = (p: number) => (p >= 100 ? 'var(--mantine-color-green-6)' : p > 0 ? `color-mix(in srgb, var(--mantine-color-green-6) ${Math.max(15, p)}%, white)` : 'transparent');

/** Simple S-curve of the daily snapshots (actual %, planned when the programme exists). */
function Curve({ points }: { points: ProgressOut['snapshots'] }) {
  if (points.length < 2) return null;
  const w = 600, h = 160, pad = 24;
  const t0 = new Date(points[0].day).getTime(), t1 = new Date(points[points.length - 1].day).getTime() || t0 + 1;
  const x = (d: string) => pad + ((new Date(d).getTime() - t0) / (t1 - t0 || 1)) * (w - 2 * pad);
  const y = (v: number) => h - pad - (v / 100) * (h - 2 * pad);
  const line = (k: 'actual' | 'planned') => points.filter((p) => p[k] !== null).map((p) => `${x(p.day)},${y(p[k] as number)}`).join(' ');
  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: '100%', maxWidth: w, direction: 'ltr' }}>
      {[0, 25, 50, 75, 100].map((v) => <g key={v}><line x1={pad} x2={w - pad} y1={y(v)} y2={y(v)} stroke="#e3e6ea" /><text x={2} y={y(v) + 4} fontSize="9" fill="#888">{v}</text></g>)}
      <polyline points={line('planned')} fill="none" stroke="#9aa5b1" strokeDasharray="4 3" strokeWidth="2" />
      <polyline points={line('actual')} fill="none" stroke="var(--mantine-color-verqac-6)" strokeWidth="2.5" />
    </svg>
  );
}

/** Progress of every stage at every floor, the project %, and its curve. Only approved daily reports count. */
export default function ProgressMatrix({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ['progress', projectId], queryFn: () => api<ProgressOut>(`/projects/${projectId}/progress`) });
  const s = useStructure(projectId).data;
  const qc = useQueryClient();
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
  if (!stages.length) return <Text c="dimmed">{t('progress.noStages')}</Text>;
  return (
    <Stack>
      <Card withBorder>
        <Group align="center" gap="xl">
          <RingProgress size={130} thickness={12} roundCaps sections={[{ value: p.project, color: 'verqac' }]}
            label={<Text ta="center" fw={700} size="xl">{p.project}%</Text>} />
          <div>
            <Title order={4}>{t('progress.project')}</Title>
            <Text size="sm" c="dimmed">{p.as_of ? t('progress.asOf', { date: fmtDate(p.as_of) }) : t('progress.none')}</Text>
            <Text size="xs" c="dimmed" mt={4}>{t('progress.hint')}</Text>
          </div>
          <div style={{ flex: 1, minWidth: 260 }}><Curve points={p.snapshots} /></div>
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
      <Card withBorder p={0}>
        <ScrollArea>
          <Table withColumnBorders withTableBorder fz="xs" miw={300 + units.length * 70} verticalSpacing={4}>
            <Table.Thead>
              {groups.length > 1 && (
                <Table.Tr>
                  <Table.Th colSpan={3} />
                  {groups.map(({ g, units: us }) => <Table.Th key={g.id} colSpan={us.length} ta="center">{pick(g, 'name')}</Table.Th>)}
                </Table.Tr>
              )}
              <Table.Tr>
                <Table.Th miw={170}>{t('structure.stage')}</Table.Th><Table.Th w={60}>{t('progress.weight')}</Table.Th><Table.Th miw={90}>{t('progress.stage')}</Table.Th>
                {units.map((u) => <Table.Th key={u.id} ta="center" miw={64}>{pick(u, 'name')}</Table.Th>)}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {stages.map((st) => (
                <Table.Tr key={st.id}>
                  <Table.Td fw={600}>{pick(st, 'name')}</Table.Td>
                  <Table.Td ta="center">{Number(st.weight)}%</Table.Td>
                  <Table.Td ta="center" style={{ whiteSpace: 'nowrap' }}><Text size="xs" fw={700}>{p.stages[st.id!] ?? 0}%</Text></Table.Td>
                  {st.scope === 'whole' ? (() => {
                    const c = cell(st.id!, null);
                    return <Table.Td colSpan={units.length || 1} ta="center" style={{ background: shade(c?.progress ?? 0) }}>{c ? `${c.progress}%` : ''}</Table.Td>;
                  })() : units.map((u) => {
                    const c = cell(st.id!, u.id!);
                    return (
                      <Tooltip key={u.id} disabled={!c} label={c ? `${t('progress.updated')}: ${fmtDate(c.progress_on ?? c.started_on)}` : ''}>
                        <Table.Td ta="center" style={{ background: shade(c?.progress ?? 0), color: (c?.progress ?? 0) >= 60 ? 'white' : undefined }}>
                          {c ? `${c.progress}%` : ''}
                        </Table.Td>
                      </Tooltip>
                    );
                  })}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      </Card>
    </Stack>
  );
}
