import { Alert, Badge, Button, Card, Group, Select, SimpleGrid, Skeleton, Stack, Table, Text, TextInput, Title, Tooltip } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { api, openProtected, type RecordMeta } from '../api';
import { pick } from '../i18n';

export interface Kpi {
  code: string; section: string; unit: 'pct' | 'days' | 'count' | 'ratio'; direction: 'higher' | 'lower' | 'info';
  value: number | null; green: number | null; amber: number | null; qmp_ref: string | null; status: 'green' | 'amber' | 'red' | null;
  name_ar: string; name_en: string; formula_ar: string; formula_en: string;
}
interface DiscRow { code: string; name_ar: string; name_en: string; [k: string]: number | string | null }
interface KpiData {
  kpis: Kpi[]; ncr_close_days: number;
  submittal: Record<string, number | null> & { by_discipline: DiscRow[] };
  inspection: Record<string, number | null> & { by_discipline: DiscRow[] };
  ncr: Record<string, number | null> & { by_discipline: DiscRow[] };
  rfi: Record<string, number | null> & { by_discipline: DiscRow[] };
  test: Record<string, number | null> & {
    by_material: { material: string; tests: number; with_result: number; pass: number; fail: number; pass_rate: number | null }[];
    by_class: { grade: string; fck: number; reports: number; failed: number; specimens: number; below: number }[];
    open_failed_list: { id: string; number: string; rev_no: number; title: string }[];
  };
}

const SECTIONS = ['submittal', 'inspection', 'test', 'ncr', 'rfi'] as const;
const COLOR = { green: 'green', amber: 'yellow', red: 'red' } as const;

export function useFmt() {
  const { t } = useTranslation();
  const num = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(v < 10 ? 2 : 1).replace(/\.?0+$/, ''));
  const value = (k: Pick<Kpi, 'unit'>, v: number | null) => {
    if (v === null || v === undefined) return '—';
    if (k.unit === 'pct') return `${num(v)}%`;
    if (k.unit === 'days') return t('kpi.days', { n: num(v) });
    return num(v);
  };
  // the sign in its own left-to-right run: in Arabic text a bare ≥ is mirrored and reads as ≤
  const target = (k: Kpi) => {
    if (k.direction === 'info' || k.green === null) return t('kpi.info');
    return <><span dir="ltr">{k.direction === 'higher' ? '≥' : '≤'}</span>{' '}<bdi>{value(k, k.green)}</bdi></>;
  };
  return { value, target };
}

export default function KpiPanel({ projectId }: { projectId: string }) {
  const { t, i18n } = useTranslation();
  const ar = i18n.language === 'ar';
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [disc, setDisc] = useState<string | null>(null);
  const qs = new URLSearchParams();
  if (from) qs.set('from', from);
  if (to) qs.set('to', to);
  if (disc) qs.set('discipline', disc);
  const q = useQuery({ queryKey: ['kpi', projectId, from, to, disc], queryFn: () => api<KpiData>(`/projects/${projectId}/kpi?${qs}`) });
  const meta = useQuery({ queryKey: ['recMeta', projectId, 'submittal'], queryFn: () => api<RecordMeta>(`/projects/${projectId}/records/meta?type=submittal`) });
  const { value, target } = useFmt();
  const [busy, setBusy] = useState<string | null>(null);
  const download = async (fmt: 'pdf' | 'xlsx', lang: string) => {
    setBusy(fmt + lang);
    try {
      await openProtected(`/projects/${projectId}/kpi/${fmt}?${qs}&lang=${lang}`, `QA-KPIs.${fmt}`, fmt === 'pdf');
    } finally {
      setBusy(null);
    }
  };
  const d = q.data;
  const counts = { green: 0, amber: 0, red: 0 };
  d?.kpis.forEach((k) => { if (k.status) counts[k.status] += 1; });

  const discTable = (rows: DiscRow[], cols: [string, string, 'pct' | 'days' | 'count'][]) => rows.length > 0 && (
    <Table.ScrollContainer minWidth={560}>
      <Table striped withTableBorder fz="sm" verticalSpacing={4}>
        <Table.Thead><Table.Tr><Table.Th>{t('rec.discipline')}</Table.Th>{cols.map(([k, label]) => <Table.Th key={k} ta="end">{label}</Table.Th>)}</Table.Tr></Table.Thead>
        <Table.Tbody>
          {rows.map((r) => (
            <Table.Tr key={r.code}>
              <Table.Td>{ar ? r.name_ar : r.name_en}</Table.Td>
              {cols.map(([k, , unit]) => <Table.Td key={k} ta="end">{value({ unit }, r[k] as number | null)}</Table.Td>)}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );

  return (
    <Stack>
      <Group justify="space-between" align="flex-end">
        <Group align="flex-end">
          <TextInput type="date" label={t('kpi.from')} value={from} max={to || undefined} onChange={(e) => setFrom(e.currentTarget.value)} w={160} />
          <TextInput type="date" label={t('kpi.to')} value={to} min={from || undefined} onChange={(e) => setTo(e.currentTarget.value)} w={160} />
          <Select label={t('rec.discipline')} placeholder={t('kpi.allDisc')} clearable value={disc} onChange={setDisc} w={180}
            data={(meta.data?.disciplines ?? []).map((x) => ({ value: x.code, label: pick(x, 'name') }))} />
          {(from || to || disc) && <Button variant="subtle" onClick={() => { setFrom(''); setTo(''); setDisc(null); }}>{t('stats.clear')}</Button>}
        </Group>
        <Group gap="xs">
          <Button size="xs" variant="light" loading={busy === 'pdfar'} onClick={() => download('pdf', 'ar')}>PDF عربي</Button>
          <Button size="xs" variant="light" loading={busy === 'pdfen'} onClick={() => download('pdf', 'en')}>PDF English</Button>
          <Button size="xs" variant="light" color="teal" loading={busy === 'xlsx' + i18n.language} onClick={() => download('xlsx', i18n.language)}>Excel</Button>
        </Group>
      </Group>
      <Group justify="flex-end">
        {d && (
          <Group gap="xs">
            <Badge color="green" size="lg" variant="light">{t('kpi.onTarget')}: {counts.green}</Badge>
            <Badge color="yellow" size="lg" variant="light">{t('kpi.watch')}: {counts.amber}</Badge>
            <Badge color="red" size="lg" variant="light">{t('kpi.offTarget')}: {counts.red}</Badge>
          </Group>
        )}
      </Group>
      <Text size="xs" c="dimmed">{t('kpi.hint')}</Text>
      {q.isError && <Alert color="red">{t('errors.generic')}</Alert>}
      {!d ? <Skeleton h={400} /> : SECTIONS.map((s) => {
        const rows = d.kpis.filter((k) => k.section === s);
        if (!rows.length) return null;
        return (
          <Card withBorder key={s}>
            <Group justify="space-between" mb="xs">
              <Title order={5}>{t(`kpi.sec.${s}`)}</Title>
              <Text size="sm" c="dimmed">
                {s === 'submittal' || s === 'inspection' ? t('kpi.uniqueOf', { n: d[s].unique ?? 0, r: d[s].records ?? 0 })
                  : s === 'test' ? t('kpi.tests', { n: d.test.records ?? 0 })
                    : t('kpi.issued', { n: d[s].issued ?? 0 })}
              </Text>
            </Group>
            <Table.ScrollContainer minWidth={640}>
              <Table verticalSpacing={6} fz="sm">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t('kpi.kpi')}</Table.Th><Table.Th ta="end" w={110}>{t('kpi.actual')}</Table.Th>
                    <Table.Th ta="end" w={110}>{t('kpi.target')}</Table.Th><Table.Th w={100}>{t('kpi.status')}</Table.Th><Table.Th w={120}>QMP</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {rows.map((k) => (
                    <Table.Tr key={k.code}>
                      <Table.Td>
                        <Tooltip label={ar ? k.formula_ar : k.formula_en} multiline w={360} withArrow position="top-start">
                          <Text size="sm" style={{ cursor: 'help', textDecoration: 'underline dotted', textUnderlineOffset: 3 }}>{ar ? k.name_ar : k.name_en}</Text>
                        </Tooltip>
                      </Table.Td>
                      <Table.Td ta="end" fw={600}><bdi>{value(k, k.value)}</bdi></Table.Td>
                      <Table.Td ta="end" c="dimmed">{target(k)}</Table.Td>
                      <Table.Td>{k.status ? <Badge color={COLOR[k.status]} variant="filled" tt="none">{t(`kpi.st.${k.status}`)}</Badge> : <Text size="sm" c="dimmed">—</Text>}</Table.Td>
                      <Table.Td><Text size="xs" c="dimmed" dir="ltr">{k.qmp_ref}</Text></Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
            {(s === 'submittal' || s === 'inspection') && d[s].by_discipline.length > 1 && (
              <Stack gap={4} mt="sm">
                <Text size="sm" fw={500}>{t('kpi.byDisc')}</Text>
                {discTable(d[s].by_discipline, [
                  ['unique', t('kpi.c.unique'), 'count'], ['records', t('kpi.c.records'), 'count'], ['first_pass', t('kpi.c.firstPass'), 'pct'], ['returned0', t('kpi.c.returned0'), 'count'],
                  ['approved', t('kpi.c.approved'), 'count'], ['outstanding_n', t('kpi.c.returned'), 'count'], ['pending', t('kpi.c.pending'), 'count'],
                  ['review_days', t('kpi.c.supDays'), 'days'], ['contractor_days', t('kpi.c.conDays'), 'days']])}
              </Stack>
            )}
            {s === 'ncr' && d.ncr.by_discipline.length > 1 && (
              <Stack gap={4} mt="sm">
                <Text size="sm" fw={500}>{t('kpi.byDisc')}</Text>
                {discTable(d.ncr.by_discipline, [['issued', t('kpi.c.issued'), 'count'], ['open', t('kpi.c.open'), 'count'],
                  ['close_days', t('kpi.c.closeDays'), 'days'], ['contractor_days', t('kpi.c.conDays'), 'days'], ['supervision_days', t('kpi.c.supDays'), 'days']])}
              </Stack>
            )}
            {s === 'rfi' && d.rfi.by_discipline.length > 1 && (
              <Stack gap={4} mt="sm">
                <Text size="sm" fw={500}>{t('kpi.byDisc')}</Text>
                {discTable(d.rfi.by_discipline, [['issued', t('kpi.c.issued'), 'count'], ['open', t('kpi.c.open'), 'count'], ['response_days', t('kpi.c.respDays'), 'days']])}
              </Stack>
            )}
            {s === 'test' && (
              <SimpleGrid cols={{ base: 1, md: 2 }} mt="sm">
                {d.test.by_material.length > 0 && (
                  <Stack gap={4}>
                    <Text size="sm" fw={500}>{t('kpi.byMaterial')}</Text>
                    <Table striped withTableBorder fz="sm" verticalSpacing={4}>
                      <Table.Thead><Table.Tr><Table.Th>{t('kpi.c.material')}</Table.Th><Table.Th ta="end">{t('kpi.c.tests')}</Table.Th>
                        <Table.Th ta="end">{t('kpi.c.pass')}</Table.Th><Table.Th ta="end">{t('kpi.c.fail')}</Table.Th><Table.Th ta="end">{t('kpi.c.passPct')}</Table.Th></Table.Tr></Table.Thead>
                      <Table.Tbody>
                        {d.test.by_material.map((m) => (
                          <Table.Tr key={m.material}><Table.Td>{m.material === 'other' ? t('kpi.c.other') : t(`labt.m.${m.material}`, m.material)}</Table.Td><Table.Td ta="end">{m.tests}</Table.Td>
                            <Table.Td ta="end">{m.pass}</Table.Td><Table.Td ta="end" c={m.fail ? 'red' : undefined}>{m.fail}</Table.Td>
                            <Table.Td ta="end">{value({ unit: 'pct' }, m.pass_rate)}</Table.Td></Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Stack>
                )}
                {d.test.by_class.length > 0 && (
                  <Stack gap={4}>
                    <Text size="sm" fw={500}>{t('kpi.byClass')}</Text>
                    <Table striped withTableBorder fz="sm" verticalSpacing={4}>
                      <Table.Thead><Table.Tr><Table.Th>{t('kpi.c.class')}</Table.Th><Table.Th ta="end">fck</Table.Th><Table.Th ta="end">{t('kpi.c.reports')}</Table.Th>
                        <Table.Th ta="end">{t('kpi.c.failed')}</Table.Th><Table.Th ta="end">{t('kpi.c.below')}</Table.Th></Table.Tr></Table.Thead>
                      <Table.Tbody>
                        {d.test.by_class.map((c) => (
                          <Table.Tr key={c.grade}><Table.Td dir="ltr">{c.grade}</Table.Td><Table.Td ta="end">{c.fck}</Table.Td><Table.Td ta="end">{c.reports}</Table.Td>
                            <Table.Td ta="end" c={c.failed ? 'red' : undefined}>{c.failed}</Table.Td>
                            <Table.Td ta="end"><span dir="ltr">{c.below} / {c.specimens}</span></Table.Td></Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Stack>
                )}
                {d.test.open_failed_list.length > 0 && (
                  <Stack gap={4}>
                    <Text size="sm" fw={500}>{t('kpi.openFailed')}</Text>
                    {d.test.open_failed_list.map((r) => (
                      <Text key={r.id} size="sm" component={Link} to={`/records/${r.id}`} c="red" dir="ltr" ta="start">{r.number} R{r.rev_no} · {r.title}</Text>
                    ))}
                  </Stack>
                )}
              </SimpleGrid>
            )}
          </Card>
        );
      })}
    </Stack>
  );
}
