import { ActionIcon, Alert, Button, Card, Group, SegmentedControl, SimpleGrid, Switch, Table, Tabs, Text, TextInput, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../api';
import { crewList, GROUPS, OTHER_LISTS, type DailySettings, type ListItem } from '../daily';


/** How the daily report records staff (names or trade + count) and the lists it suggests, in Arabic and English. */
export default function DailySettingsCard({ projectId, editable }: { projectId: string; editable: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['dailySettings', projectId], queryFn: () => api<DailySettings>(`/projects/${projectId}/daily-settings`) });
  const [s, setS] = useState<DailySettings | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => { if (q.data) setS(q.data); }, [q.data]);
  const save = useMutation({
    mutationFn: () => api<DailySettings>(`/projects/${projectId}/daily-settings`, { method: 'PUT', body: JSON.stringify(s) }),
    onSuccess: (d) => { qc.setQueryData(['dailySettings', projectId], d); setS(d); setMsg({ ok: true, text: t('settings.saved') }); },
    onError: (e) => setMsg({ ok: false, text: t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic')) }),
  });
  if (!s) return null;
  const rows = (k: string) => s.lists[k] ?? [];
  const setRows = (k: string, v: ListItem[]) => setS({ ...s, lists: { ...s.lists, [k]: v } });
  const setRow = (k: string, i: number, p: Partial<ListItem>) => setRows(k, rows(k).map((x, j) => (j === i ? { ...x, ...p } : x)));
  return (
    <Card withBorder>
      <Title order={5}>{t('dset.title')}</Title>
      <Text size="sm" c="dimmed" mb="md">{t('dset.hint')}</Text>
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        {GROUPS.map((g) => (
          <div key={g}>
            <Text size="sm" fw={600} mb={4}>{t(`daily.g.${g}`)}</Text>
            <SegmentedControl size="xs" fullWidth disabled={!editable} value={s.crew[g] ?? 'counts'}
              data={[{ value: 'names', label: t('dset.names') }, { value: 'counts', label: t('dset.counts') }]}
              onChange={(v) => setS({ ...s, crew: { ...s.crew, [g]: v as 'names' | 'counts' } })} />
          </div>
        ))}
      </SimpleGrid>
      <Tabs defaultValue="supervision" mt="lg" keepMounted={false}>
        <Tabs.List>
          {GROUPS.map((g) => <Tabs.Tab key={g} value={g}>{t(`daily.g.${g}`)} — {t(s.crew[g] === 'names' ? 'dset.names' : 'dset.counts')} ({rows(crewList(s, g)).length})</Tabs.Tab>)}
          {OTHER_LISTS.map((k) => <Tabs.Tab key={k} value={k}>{t(`dset.list.${k}`)} ({rows(k).length})</Tabs.Tab>)}
        </Tabs.List>
        {[...GROUPS.map((g) => [g, crewList(s, g)]), ...OTHER_LISTS.map((k) => [k, k])].map(([tab, k]) => {
          const people = k.endsWith('_names');
          return (
            <Tabs.Panel key={tab} value={tab} pt="sm">
              <Text size="xs" c="dimmed" mb={6}>{t(`dset.listHint.${k}`)}</Text>
              {rows(k).length > 0 && (
                <Table withRowBorders={false} verticalSpacing={3} horizontalSpacing={4}>
                  <Table.Thead><Table.Tr>
                    <Table.Th>{t(people ? 'dset.nameAr' : 'dset.descAr')}</Table.Th><Table.Th>{t(people ? 'dset.nameEn' : 'dset.descEn')}</Table.Th>
                    {people && <><Table.Th>{t('dset.roleAr')}</Table.Th><Table.Th>{t('dset.roleEn')}</Table.Th></>}
                    <Table.Th w={70}>{t('dset.active')}</Table.Th>{editable && <Table.Th w={30} />}
                  </Table.Tr></Table.Thead>
                  <Table.Tbody>
                    {rows(k).map((x, i) => (
                      <Table.Tr key={i} opacity={x.active ? 1 : 0.55}>
                        <Table.Td><TextInput size="xs" disabled={!editable} value={x.ar} onChange={(e) => setRow(k, i, { ar: e.currentTarget.value })} /></Table.Td>
                        <Table.Td><TextInput size="xs" dir="ltr" disabled={!editable} value={x.en} onChange={(e) => setRow(k, i, { en: e.currentTarget.value })} /></Table.Td>
                        {people && <>
                          <Table.Td><TextInput size="xs" disabled={!editable} value={x.role_ar ?? ''} onChange={(e) => setRow(k, i, { role_ar: e.currentTarget.value || null })} /></Table.Td>
                          <Table.Td><TextInput size="xs" dir="ltr" disabled={!editable} value={x.role_en ?? ''} onChange={(e) => setRow(k, i, { role_en: e.currentTarget.value || null })} /></Table.Td>
                        </>}
                        <Table.Td><Switch size="xs" disabled={!editable} checked={x.active} onChange={(e) => setRow(k, i, { active: e.currentTarget.checked })} /></Table.Td>
                        {editable && <Table.Td><ActionIcon size="sm" variant="subtle" color="red" aria-label="remove" onClick={() => setRows(k, rows(k).filter((_, j) => j !== i))}>×</ActionIcon></Table.Td>}
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
              {editable && <Button mt={4} size="compact-xs" variant="subtle" onClick={() => setRows(k, [...rows(k), { ar: '', en: '', role_ar: null, role_en: null, active: true }])}>
                + {t(`dset.add.${people ? 'person' : k.endsWith('_desc') ? 'desc' : k}`)}</Button>}
            </Tabs.Panel>
          );
        })}
      </Tabs>
      <Switch mt="lg" label={t('dset.linkMaterials')} description={t('dset.linkMaterialsHint')} disabled={!editable} checked={s.link_materials}
        onChange={(e) => setS({ ...s, link_materials: e.currentTarget.checked })} />
      {msg && <Alert mt="sm" color={msg.ok ? 'green' : 'red'}>{msg.text}</Alert>}
      {editable && <Group mt="md"><Button variant="light" loading={save.isPending} onClick={() => save.mutate()}>{t('rec.save')}</Button></Group>}
    </Card>
  );
}
