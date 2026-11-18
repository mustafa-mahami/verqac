import { Alert, Button, Card, Group, SegmentedControl, SimpleGrid, Switch, Text, Textarea, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../api';
import { GROUPS, type DailySettings } from '../daily';

/** How the daily report records staff (names or trade + count) and the lists it offers. */
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
  const list = (k: string) => (
    <Textarea key={k} size="xs" autosize minRows={3} maxRows={10} label={t(`dset.list.${k}`)} disabled={!editable}
      value={(s.lists[k] ?? []).join('\n')} onChange={(e) => setS({ ...s, lists: { ...s.lists, [k]: e.currentTarget.value.split('\n') } })} />
  );
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
      <SimpleGrid cols={{ base: 1, sm: 3 }} mt="md">
        {list('supervision')}{list('contractor')}{list('labour')}{list('subcontractors')}{list('equipment')}
      </SimpleGrid>
      <Switch mt="md" label={t('dset.linkMaterials')} description={t('dset.linkMaterialsHint')} disabled={!editable} checked={s.link_materials}
        onChange={(e) => setS({ ...s, link_materials: e.currentTarget.checked })} />
      {msg && <Alert mt="sm" color={msg.ok ? 'green' : 'red'}>{msg.text}</Alert>}
      {editable && <Group mt="md"><Button variant="light" loading={save.isPending} onClick={() => save.mutate()}>{t('rec.save')}</Button></Group>}
    </Card>
  );
}
