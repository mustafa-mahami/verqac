import { Alert, Button, Card, Group, NumberInput, Switch, Table, Text, TextInput, Title, Tooltip } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../api';

interface Target { green: number | null; amber: number | null; qmp_ref: string | null; active: boolean }
interface Def {
  code: string; section: string; unit: string; direction: 'higher' | 'lower' | 'info'; name_ar: string; name_en: string;
  formula_ar: string; formula_en: string; default_green: number | null; default_amber: number | null; default_qmp: string;
}
interface KpiSettings { targets: Record<string, Target>; ncr_close_days: number; defs: Def[]; can_edit: boolean }

const SECTIONS = ['submittal', 'inspection', 'test', 'ncr', 'rfi'];

/** Project settings > KPIs: each indicator's target (green / amber), its QMP reference, on or off. */
export default function KpiSettingsCard({ projectId }: { projectId: string }) {
  const { t, i18n } = useTranslation();
  const ar = i18n.language === 'ar';
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['kpiSettings', projectId], queryFn: () => api<KpiSettings>(`/projects/${projectId}/kpi-settings`) });
  const [targets, setTargets] = useState<Record<string, Target>>({});
  const [closeDays, setCloseDays] = useState(14);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => {
    if (q.data) { setTargets(q.data.targets); setCloseDays(q.data.ncr_close_days); }
  }, [q.data]);
  const save = useMutation({
    mutationFn: () => api<KpiSettings>(`/projects/${projectId}/kpi-settings`, { method: 'PUT', body: JSON.stringify({ targets, ncr_close_days: closeDays }) }),
    onSuccess: (s) => {
      qc.setQueryData(['kpiSettings', projectId], s);
      qc.invalidateQueries({ queryKey: ['kpi', projectId] });
      setMsg({ ok: true, text: t('settings.saved') });
    },
    onError: (e) => setMsg({ ok: false, text: t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic')) }),
  });
  if (!q.data) return null;
  const edit = q.data.can_edit;
  const set = (code: string, patch: Partial<Target>) => { setMsg(null); setTargets({ ...targets, [code]: { ...targets[code], ...patch } }); };
  const reset = () => {
    const next: Record<string, Target> = {};
    q.data.defs.forEach((d) => { next[d.code] = { green: d.default_green, amber: d.default_amber, qmp_ref: d.default_qmp, active: true }; });
    setTargets(next);
    setMsg(null);
  };
  const unit = (d: Def) => (d.unit === 'pct' ? '%' : d.unit === 'days' ? t('kpi.dayUnit') : '');

  return (
    <Card withBorder>
      <Title order={5}>{t('kpi.settingsTitle')}</Title>
      <Text size="sm" c="dimmed" mb="sm">{t('kpi.settingsHint')}</Text>
      <Group mb="sm">
        <NumberInput label={t('kpi.ncrCloseDays')} description={t('kpi.ncrCloseHint')} value={closeDays} min={1} max={365} w={260}
          disabled={!edit} onChange={(v) => { setMsg(null); setCloseDays(Number(v) || 14); }} />
      </Group>
      <Table.ScrollContainer minWidth={760}>
        <Table verticalSpacing={4} fz="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={60}>{t('kpi.on')}</Table.Th><Table.Th>{t('kpi.kpi')}</Table.Th>
              <Table.Th w={140}>{t('kpi.green')}</Table.Th><Table.Th w={140}>{t('kpi.amber')}</Table.Th><Table.Th w={150}>{t('kpi.qmp')}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {SECTIONS.map((s) => [
              <Table.Tr key={s}><Table.Td colSpan={5} bg="gray.0"><Text fw={600} size="sm">{t(`kpi.sec.${s}`)}</Text></Table.Td></Table.Tr>,
              ...q.data.defs.filter((d) => d.section === s).map((d) => {
                const x = targets[d.code];
                if (!x) return null;
                const info = d.direction === 'info';
                return (
                  <Table.Tr key={d.code} style={{ opacity: x.active ? 1 : 0.5 }}>
                    <Table.Td><Switch size="xs" checked={x.active} disabled={!edit} onChange={(e) => set(d.code, { active: e.currentTarget.checked })} /></Table.Td>
                    <Table.Td>
                      <Tooltip label={ar ? d.formula_ar : d.formula_en} multiline w={360} withArrow position="top-start">
                        <Text size="sm" style={{ cursor: 'help' }}>{ar ? d.name_ar : d.name_en}</Text>
                      </Tooltip>
                      <Text size="xs" c="dimmed">{info ? t('kpi.info') : t(d.direction === 'higher' ? 'kpi.higher' : 'kpi.lower')}</Text>
                    </Table.Td>
                    {info ? <Table.Td colSpan={2}><Text size="xs" c="dimmed">{t('kpi.noTarget')}</Text></Table.Td> : <>
                      <Table.Td>
                        <NumberInput size="xs" value={x.green ?? ''} min={0} decimalScale={2} disabled={!edit}
                          leftSection={<Text size="xs" dir="ltr">{d.direction === 'higher' ? '≥' : '≤'}</Text>} rightSection={<Text size="xs" c="dimmed">{unit(d)}</Text>}
                          onChange={(v) => set(d.code, { green: v === '' ? null : Number(v) })} />
                      </Table.Td>
                      <Table.Td>
                        <NumberInput size="xs" value={x.amber ?? ''} min={0} decimalScale={2} disabled={!edit}
                          leftSection={<Text size="xs" dir="ltr">{d.direction === 'higher' ? '≥' : '≤'}</Text>} rightSection={<Text size="xs" c="dimmed">{unit(d)}</Text>}
                          onChange={(v) => set(d.code, { amber: v === '' ? null : Number(v) })} />
                      </Table.Td>
                    </>}
                    <Table.Td><TextInput size="xs" dir="ltr" value={x.qmp_ref ?? ''} maxLength={60} disabled={!edit} onChange={(e) => set(d.code, { qmp_ref: e.currentTarget.value || null })} /></Table.Td>
                  </Table.Tr>
                );
              }),
            ])}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <Text size="xs" c="dimmed" mt="xs">{t('kpi.legend')}</Text>
      {msg && <Alert mt="md" color={msg.ok ? 'green' : 'red'}>{msg.text}</Alert>}
      {edit && (
        <Group mt="md">
          <Button variant="light" loading={save.isPending} onClick={() => save.mutate()}>{t('rec.save')}</Button>
          <Button variant="subtle" color="gray" onClick={reset}>{t('kpi.resetDefaults')}</Button>
        </Group>
      )}
    </Card>
  );
}
