import { ActionIcon, Alert, Badge, Button, Card, Group, NumberInput, Select, SimpleGrid, Stack, Table, Text, TextInput, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { api, ApiError } from '../api';
import { money } from '../recordTypes';

export interface Point { day: string; value: number }
export interface Receipt { id: string; day: string; amount: number; kind: 'advance' | 'payment' | 'other'; record_id: string | null; note: string | null }
export interface FinanceT {
  contract_value: number | null; currency: string; can_edit: boolean; can_pay: boolean; receipts: Receipt[];
  applications: { id: string; number: string; rev_no: number; state: string; payable: number; certified: number; claimed: number; paid: number; remaining: number }[];
  planned: Point[]; baseline: Point[]; earned: Point[]; certified: Point[]; payable: Point[]; paid: Point[];
  months: { month: string; planned: number | null; earned: number | null; certified: number; payable: number; paid: number }[];
  totals: Record<string, number | null>;
}
export const CURRENCIES = ['ILS', 'USD', 'JOD', 'EUR'];

export const useFinance = (projectId: string) => useQuery({
  queryKey: ['finance', projectId], retry: false,
  queryFn: async () => {
    try {
      return await api<FinanceT>(`/projects/${projectId}/finance`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null; // money is not for this user
      throw e;
    }
  },
});

const SERIES = [
  { key: 'planned', color: '#868e96', dash: '6 4' },
  { key: 'baseline', color: '#ced4da', dash: '2 4' },
  { key: 'earned', color: '#2f9e44', dash: '' },
  { key: 'certified', color: '#1c7ed6', dash: '' },
  { key: 'payable', color: '#7048e8', dash: '' },
  { key: 'paid', color: '#e8590c', dash: '' },
] as const;

/** Cumulative curves: lines as steps between points, time on the x axis. */
function Curves({ f }: { f: FinanceT }) {
  const { t } = useTranslation();
  const W = 900, H = 320, L = 70, R = 16, T = 12, B = 34;
  // what has happened so far stays at its last value until today (a single report still draws a line)
  const todayIso = new Date().toISOString().slice(0, 10);
  const upTo = (pts: Point[]) => (pts.length && pts[pts.length - 1].day < todayIso ? [...pts, { day: todayIso, value: pts[pts.length - 1].value }] : pts);
  const data: Record<string, Point[]> = Object.fromEntries(SERIES.map((s) => [s.key, s.key === 'planned' || s.key === 'baseline' ? f[s.key] : upTo(f[s.key])]));
  const all = SERIES.flatMap((s) => data[s.key]);
  if (!all.length) return <Text c="dimmed" size="sm">{t('cash.noData')}</Text>;
  const ts = all.map((p) => Date.parse(p.day));
  const today = Date.now();
  const x0 = Math.min(...ts), x1 = Math.max(...ts, Math.min(today, Math.max(...ts) + 1));
  const ymax = Math.max(f.contract_value ?? 0, ...all.map((p) => p.value)) || 1;
  const X = (d: number) => L + ((d - x0) / Math.max(1, x1 - x0)) * (W - L - R);
  const Y = (v: number) => H - B - (v / ymax) * (H - T - B);
  const path = (pts: Point[], step: boolean) => pts.map((p, i) => {
    const x = X(Date.parse(p.day)), y = Y(p.value);
    if (i === 0) return `M${x},${y}`;
    return step ? `H${x}V${y}` : `L${x},${y}`;
  }).join('');
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((k) => k * ymax);
  const months: number[] = [];
  const d = new Date(x0); d.setDate(1);
  const span = (x1 - x0) / (86400000 * 30);
  const every = span > 36 ? 6 : span > 18 ? 3 : 1;
  while (d.getTime() <= x1) { if (d.getTime() >= x0 && d.getMonth() % every === 0) months.push(d.getTime()); d.setMonth(d.getMonth() + 1); }
  const short = (v: number) => (v >= 1e6 ? `${(v / 1e6).toFixed(v >= 1e7 ? 0 : 1)}M` : v >= 1e3 ? `${Math.round(v / 1e3)}K` : `${Math.round(v)}`);
  return (
    <div dir="ltr">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={t('cash.title')}>
        {ticks.map((v) => <g key={v}><line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} stroke="#e9ecef" />
          <text x={L - 6} y={Y(v) + 4} fontSize="11" textAnchor="end" fill="#868e96">{short(v)}</text></g>)}
        {months.map((m) => <text key={m} x={X(m)} y={H - 12} fontSize="10" textAnchor="middle" fill="#868e96">
          {`${String(new Date(m).getFullYear()).slice(2)}/${String(new Date(m).getMonth() + 1).padStart(2, '0')}`}</text>)}
        {today > x0 && today < x1 && <line x1={X(today)} x2={X(today)} y1={T} y2={H - B} stroke="#fa5252" strokeDasharray="3 3" />}
        {f.contract_value ? <line x1={L} x2={W - R} y1={Y(f.contract_value)} y2={Y(f.contract_value)} stroke="#adb5bd" strokeDasharray="1 3" /> : null}
        {SERIES.map((s) => data[s.key].length > 0 && (
          <g key={s.key}>
            <path d={path(data[s.key], s.key === 'certified' || s.key === 'payable' || s.key === 'paid')} fill="none" stroke={s.color}
              strokeWidth={s.key === 'baseline' ? 1.5 : 2.2} strokeDasharray={s.dash} />
            {s.key !== 'planned' && s.key !== 'baseline' && f[s.key].length > 0 && (() => {
              const p = f[s.key][f[s.key].length - 1];
              return <circle cx={X(Date.parse(p.day))} cy={Y(p.value)} r={3.5} fill={s.color}><title>{`${p.day}: ${money(p.value)}`}</title></circle>;
            })()}
          </g>
        ))}
      </svg>
      <Group gap="md" justify="center" mt={4}>
        {SERIES.filter((s) => f[s.key].length > 0).map((s) => (
          <Group key={s.key} gap={6}><svg width="22" height="8"><line x1="0" x2="22" y1="4" y2="4" stroke={s.color} strokeWidth="2.5" strokeDasharray={s.dash} /></svg>
            <Text size="xs">{t(`cash.s.${s.key}`)}</Text></Group>
        ))}
      </Group>
    </div>
  );
}

export default function CashflowPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useFinance(projectId);
  const [err, setErr] = useState<string | null>(null);
  const [rc, setRc] = useState<{ day: string; amount: number | ''; kind: Receipt['kind']; record_id: string | null; note: string }>(
    { day: new Date().toISOString().slice(0, 10), amount: '', kind: 'payment', record_id: null, note: '' });
  const done = (f: FinanceT) => { qc.setQueryData(['finance', projectId], f); setErr(null); };
  const onErr = (e: unknown) => setErr(t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic')));
  const add = useMutation({
    mutationFn: () => api<FinanceT>(`/projects/${projectId}/finance/receipts`, { method: 'POST',
      body: JSON.stringify({ ...rc, amount: Number(rc.amount), note: rc.note || null, record_id: rc.kind === 'payment' ? rc.record_id : null }) }),
    onSuccess: (f) => { done(f); setRc({ ...rc, amount: '', note: '', record_id: null }); }, onError: onErr,
  });
  const del = useMutation({
    mutationFn: (id: string) => api<FinanceT>(`/projects/${projectId}/finance/receipts/${id}`, { method: 'DELETE' }),
    onSuccess: done, onError: onErr,
  });
  const f = q.data;
  if (!f) return null;
  const tt = f.totals;
  const cur = f.currency;
  const m = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${money(v)} ${cur}`);
  // certified applications not fully paid yet (what is left of each)
  const apps = f.applications.filter((x) => x.state === 'approved' && x.remaining > 0);
  const appLabel = (id: string | null) => { const a = f.applications.find((x) => x.id === id); return a ? `${a.number} R${a.rev_no}` : ''; };
  const pct = (v: number | null | undefined) => (v != null && f.contract_value ? ` · ${(100 * v / f.contract_value).toFixed(1)}%` : '');
  return (
    <Stack>
      {!f.contract_value && <Alert color="yellow">{t('cash.noContract')}</Alert>}
      <SimpleGrid cols={{ base: 2, md: 6 }}>
        {([['contract', tt.contract], ['planned', tt.planned], ['earned', tt.earned], ['certified', tt.certified], ['payable', tt.payable], ['paid', tt.paid]] as [string, number | null][]).map(([k, v]) => (
          <Card key={k} withBorder p="sm">
            <Text size="xs" c="dimmed">{t(`cash.s.${k}`)}</Text>
            <Text fw={700} dir="ltr" ta="start">{m(v)}</Text>
            {k !== 'contract' && <Text size="xs" c="dimmed" dir="ltr" ta="start">{pct(v).replace(' · ', '')}</Text>}
          </Card>
        ))}
      </SimpleGrid>
      <Group gap="xs">
        <Badge variant="light" color="orange" tt="none">{t('cash.unpaid')}: {m(tt.unpaid)}</Badge>
        <Badge variant="light" color="grape" tt="none">{t('cash.advance')}: {m(tt.advance)}</Badge>
        {!!tt.claimed_pending && <Badge variant="light" color="gray" tt="none">{t('cash.pending')}: {m(tt.claimed_pending)}</Badge>}
        {tt.earned != null && tt.planned != null && (
          <Badge variant="light" color={tt.earned >= tt.planned ? 'green' : 'red'} tt="none">{t('cash.vsPlan')}: {m(tt.earned - tt.planned)}</Badge>
        )}
      </Group>
      <Card withBorder>
        <Title order={5} mb="xs">{t('cash.title')}</Title>
        <Curves f={f} />
        <Text size="xs" c="dimmed" mt="xs">{t('cash.hint')}</Text>
      </Card>

      <Card withBorder>
        <Title order={5} mb="xs">{t('cash.receipts')}</Title>
        {err && <Alert color="red" mb="sm">{err}</Alert>}
        {f.can_pay && (
          <Group align="flex-end" mb="sm" wrap="wrap">
            <TextInput type="date" label={t('cash.day')} w={160} value={rc.day} onChange={(e) => setRc({ ...rc, day: e.currentTarget.value })} />
            <Select label={t('cash.kind')} w={170} value={rc.kind} allowDeselect={false} onChange={(v) => setRc({ ...rc, kind: (v ?? 'payment') as Receipt['kind'] })}
              data={(['payment', 'advance', 'other'] as const).map((k) => ({ value: k, label: t(`cash.k.${k}`) }))} />
            {rc.kind === 'payment' && (
              <Select label={t('cash.application')} w={230} clearable value={rc.record_id} placeholder={apps.length ? undefined : t('cash.noneToPay')}
                onChange={(v) => setRc({ ...rc, record_id: v, amount: v ? (apps.find((a) => a.id === v)?.remaining ?? rc.amount) : rc.amount })}
                data={apps.map((a) => ({ value: a.id, label: `${a.number} R${a.rev_no} · ${t('cash.left')} ${money(a.remaining)}` }))}
                nothingFoundMessage={t('cash.noneToPay')} />
            )}
            <NumberInput label={`${t('cash.amount')} (${cur})`} w={170} min={0} thousandSeparator="," hideControls value={rc.amount}
              onChange={(v) => setRc({ ...rc, amount: v === '' ? '' : Number(v) })} />
            <TextInput label={t('cash.note')} style={{ flex: 1, minWidth: 160 }} value={rc.note} onChange={(e) => setRc({ ...rc, note: e.currentTarget.value })} />
            <Button loading={add.isPending} disabled={!rc.amount || !rc.day} onClick={() => add.mutate()}>{t('cash.add')}</Button>
          </Group>
        )}
        {f.receipts.length === 0 ? <Text size="sm" c="dimmed">{t('cash.noReceipts')}</Text> : (
          <Table striped withTableBorder fz="sm">
            <Table.Thead><Table.Tr><Table.Th>{t('cash.day')}</Table.Th><Table.Th>{t('cash.kind')}</Table.Th><Table.Th>{t('cash.application')}</Table.Th>
              <Table.Th ta="end">{t('cash.amount')}</Table.Th><Table.Th>{t('cash.note')}</Table.Th>{f.can_pay && <Table.Th w={30} />}</Table.Tr></Table.Thead>
            <Table.Tbody>
              {f.receipts.map((x) => (
                <Table.Tr key={x.id}>
                  <Table.Td dir="ltr" ta="start">{x.day}</Table.Td><Table.Td>{t(`cash.k.${x.kind}`)}</Table.Td>
                  <Table.Td dir="ltr" ta="start">{x.record_id ? <Link to={`/records/${x.record_id}`}>{appLabel(x.record_id)}</Link> : ''}</Table.Td>
                  <Table.Td ta="end" dir="ltr">{money(x.amount)}</Table.Td><Table.Td>{x.note}</Table.Td>
                  {f.can_pay && <Table.Td><ActionIcon size="sm" variant="subtle" color="red" aria-label="remove"
                    onClick={() => { if (window.confirm(t('cash.removeConfirm'))) del.mutate(x.id); }}>×</ActionIcon></Table.Td>}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Card>

      {f.months.length > 0 && (
        <Card withBorder>
          <Title order={5} mb="xs">{t('cash.monthly')}</Title>
          <Table.ScrollContainer minWidth={640}>
            <Table striped withTableBorder fz="sm">
              <Table.Thead><Table.Tr><Table.Th style={{ textAlign: 'center' }}>{t('cash.month')}</Table.Th>
                {(['planned', 'earned', 'certified', 'payable', 'paid'] as const).map((k) => <Table.Th key={k} style={{ textAlign: 'center' }}>{t(`cash.s.${k}`)}</Table.Th>)}</Table.Tr></Table.Thead>
              <Table.Tbody>
                {f.months.map((r) => (
                  <Table.Tr key={r.month}><Table.Td dir="ltr" style={{ textAlign: 'center' }}>{r.month}</Table.Td>
                    {(['planned', 'earned', 'certified', 'payable', 'paid'] as const).map((k) => <Table.Td key={k} style={{ textAlign: 'center' }} dir="ltr">{r[k] == null ? '—' : money(r[k])}</Table.Td>)}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Text size="xs" c="dimmed" mt={4}>{t('cash.monthlyHint')}</Text>
        </Card>
      )}
    </Stack>
  );
}

/** Contract amount and currency, next to the stages (their value = weight x contract). */
export function ContractSettings({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useFinance(projectId);
  const [v, setV] = useState<{ contract_value: number | ''; currency: string } | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const save = useMutation({
    mutationFn: () => api<FinanceT>(`/projects/${projectId}/finance/settings`, { method: 'PUT',
      body: JSON.stringify({ contract_value: v?.contract_value === '' ? null : v?.contract_value, currency: v?.currency }) }),
    onSuccess: (f) => { qc.setQueryData(['finance', projectId], f); setMsg({ ok: true, text: t('settings.saved') }); setV(null); },
    onError: (e) => setMsg({ ok: false, text: t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic')) }),
  });
  const f = q.data;
  if (!f) return null;
  const cur = v ?? { contract_value: f.contract_value ?? '', currency: f.currency };
  return (
    <Group align="flex-end" mb="md" wrap="wrap">
      <NumberInput label={t('cash.contract')} description={t('cash.contractHint')} w={260} min={0} thousandSeparator="," hideControls
        disabled={!f.can_edit} value={cur.contract_value} onChange={(x) => { setMsg(null); setV({ ...cur, contract_value: x === '' ? '' : Number(x) }); }} />
      <Select label={t('cash.currency')} w={120} disabled={!f.can_edit} allowDeselect={false} value={cur.currency}
        data={CURRENCIES} onChange={(x) => { setMsg(null); setV({ ...cur, currency: x ?? 'ILS' }); }} />
      {f.can_edit && <Button variant="light" disabled={!v} loading={save.isPending} onClick={() => save.mutate()}>{t('rec.save')}</Button>}
      {msg && <Text size="sm" c={msg.ok ? 'green' : 'red'}>{msg.text}</Text>}
    </Group>
  );
}
