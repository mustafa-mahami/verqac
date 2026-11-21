import { Alert, Badge, Card, Group, ScrollArea, Skeleton, Stack, Table, Text, TextInput, Title, Tooltip } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { Fragment, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { useFmt, type Kpi } from './KpiPanel';

interface Def { code: string; section: string; unit: Kpi['unit']; direction: Kpi['direction']; name_ar: string; name_en: string }
interface Row {
  id: string; code: string; name_ar: string; name_en: string;
  kpis: Record<string, { value: number | null; status: Kpi['status'] }>;
  score: { green: number; amber: number; red: number }; counts: Record<string, number | null>;
}
const BG = { green: 'var(--mantine-color-green-1)', amber: 'var(--mantine-color-yellow-1)', red: 'var(--mantine-color-red-1)' } as const;
const SECTIONS = ['submittal', 'inspection', 'test', 'ncr', 'rfi'];

/** Every project's QA scorecard side by side, each against its own targets. */
export default function Portfolio() {
  const { t, i18n } = useTranslation();
  const ar = i18n.language === 'ar';
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const qs = new URLSearchParams();
  if (from) qs.set('from', from);
  if (to) qs.set('to', to);
  const q = useQuery({ queryKey: ['portfolio', from, to], queryFn: () => api<{ projects: Row[]; defs: Def[] }>(`/kpi/portfolio?${qs}`) });
  const { value } = useFmt();
  const defs = q.data?.defs ?? [];
  const rows = q.data?.projects ?? [];
  const total = rows.reduce((a, r) => ({ green: a.green + r.score.green, amber: a.amber + r.score.amber, red: a.red + r.score.red }),
    { green: 0, amber: 0, red: 0 });

  return (
    <Stack>
      <Group justify="space-between" align="end">
        <Title order={3}>{t('portfolio.title')}</Title>
        <Group>
          <TextInput type="date" label={t('kpi.from')} value={from} onChange={(e) => setFrom(e.currentTarget.value)} />
          <TextInput type="date" label={t('kpi.to')} value={to} onChange={(e) => setTo(e.currentTarget.value)} />
        </Group>
      </Group>
      <Text size="sm" c="dimmed">{t('portfolio.hint')}</Text>
      {q.isLoading && <Skeleton h={300} />}
      {q.isError && <Alert color="red">{t('errors.generic')}</Alert>}
      {q.data && !rows.length && <Alert>{t('portfolio.empty')}</Alert>}
      {!!rows.length && (
        <>
          <Group>
            <Card withBorder p="sm"><Text size="xs" c="dimmed">{t('portfolio.projects')}</Text><Text fw={700} size="xl">{rows.length}</Text></Card>
            <Card withBorder p="sm" bg={BG.green}><Text size="xs">{t('kpi.onTarget')}</Text><Text fw={700} size="xl">{total.green}</Text></Card>
            <Card withBorder p="sm" bg={BG.amber}><Text size="xs">{t('kpi.watch')}</Text><Text fw={700} size="xl">{total.amber}</Text></Card>
            <Card withBorder p="sm" bg={BG.red}><Text size="xs">{t('kpi.offTarget')}</Text><Text fw={700} size="xl">{total.red}</Text></Card>
          </Group>
          <ScrollArea type="auto">
            <Table withTableBorder withColumnBorders striped={false} style={{ minWidth: 300 + rows.length * 130 }}>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('portfolio.kpi')}</Table.Th>
                  {rows.map((r) => (
                    <Table.Th key={r.id} ta="center">
                      <Text component={Link} to={`/projects/${r.id}?tab=kpi`} fw={700} size="sm" c="verqac.7">{r.code}</Text>
                      <Text size="xs" c="dimmed" lineClamp={1}>{ar ? r.name_ar : r.name_en}</Text>
                      <Group gap={4} justify="center" mt={4}>
                        <Badge size="xs" color="green">{r.score.green}</Badge>
                        <Badge size="xs" color="yellow">{r.score.amber}</Badge>
                        <Badge size="xs" color="red">{r.score.red}</Badge>
                      </Group>
                    </Table.Th>
                  ))}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {SECTIONS.map((s) => {
                  const ds = defs.filter((d) => d.section === s);
                  if (!ds.length) return null;
                  return (
                    <Fragment key={s}>
                      <Table.Tr bg="var(--mantine-color-gray-1)">
                        <Table.Td fw={700}>{t(`kpi.sec.${s}`)}</Table.Td>
                        {rows.map((r) => <Table.Td key={r.id} ta="center"><Text size="xs" c="dimmed">{t('portfolio.records', { n: r.counts[s] ?? 0 })}</Text></Table.Td>)}
                      </Table.Tr>
                      {ds.map((d) => (
                        <Table.Tr key={d.code}>
                          <Table.Td><Text size="sm">{ar ? d.name_ar : d.name_en}</Text></Table.Td>
                          {rows.map((r) => {
                            const k = r.kpis[d.code];
                            return (
                              <Table.Td key={r.id} ta="center" bg={k?.status ? BG[k.status] : undefined}>
                                <Tooltip label={k?.status ? t(`kpi.st.${k.status}`) : t('kpi.info')} disabled={!k}>
                                  <Text size="sm" fw={k?.status === 'red' ? 700 : 400}>{k ? <bdi>{value(d, k.value)}</bdi> : '—'}</Text>
                                </Tooltip>
                              </Table.Td>
                            );
                          })}
                        </Table.Tr>
                      ))}
                    </Fragment>
                  );
                })}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        </>
      )}
    </Stack>
  );
}
