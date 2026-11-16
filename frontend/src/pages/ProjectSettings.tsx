import { Alert, Button, Card, Group, NumberInput, Stack, Switch, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError, type ProjectSettings as Settings, type RecordType } from '../api';
import { pick } from '../i18n';

export default function ProjectSettings({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ['settings', projectId], queryFn: () => api<Settings>(`/projects/${projectId}/settings`) });
  const types = useQuery({ queryKey: ['recordTypes'], queryFn: () => api<RecordType[]>('/record-types') });
  const [days, setDays] = useState<Record<string, number>>({});
  const [notify, setNotify] = useState({ email: false, mahami: false });
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => {
    if (settings.data) { setDays(settings.data.review_days); setNotify(settings.data.notify); }
  }, [settings.data]);
  const save = useMutation({
    mutationFn: () => api<Settings>(`/projects/${projectId}/settings`, { method: 'PUT', body: JSON.stringify({ review_days: days, notify }) }),
    onSuccess: (s) => { qc.setQueryData(['settings', projectId], s); setMsg({ ok: true, text: t('settings.saved') }); },
    onError: (e) => setMsg({ ok: false, text: t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic')) }),
  });
  if (!settings.data || !types.data) return null;
  const editable = settings.data.can_edit;

  return (
    <Stack maw={640}>
      <Card withBorder>
        <Title order={5}>{t('settings.reviewTitle')}</Title>
        <Text size="sm" c="dimmed" mb="md">{t('settings.reviewHint')}</Text>
        <Stack gap="sm">
          {types.data.map((rt) => (
            <Group key={rt.code} justify="space-between">
              <Text size="sm">{pick(rt, 'name')}</Text>
              <NumberInput w={140} min={1} max={365} disabled={!editable} rightSection={<Text size="xs" c="dimmed" pe={8}>{t('settings.days')}</Text>}
                rightSectionWidth={44} value={days[rt.code] ?? rt.review_days}
                onChange={(v) => setDays({ ...days, [rt.code]: Number(v) || 1 })} />
            </Group>
          ))}
        </Stack>
        {msg && <Alert mt="md" color={msg.ok ? 'green' : 'red'}>{msg.text}</Alert>}
        {editable ? <Button mt="md" loading={save.isPending} onClick={() => save.mutate()}>{t('rec.save')}</Button>
          : <Text size="xs" c="dimmed" mt="md">{t('settings.readOnly')}</Text>}
      </Card>
      <Card withBorder>
        <Title order={5}>{t('settings.notifyTitle')}</Title>
        <Text size="sm" c="dimmed" mb="md">{t('settings.notifyHint')}</Text>
        <Stack gap="sm">
          {(['email', 'mahami'] as const).map((k) => {
            const available = k === 'email' ? settings.data!.email_available : settings.data!.mahami_available;
            return (
              <Switch key={k} label={t(`settings.${k}`)} checked={notify[k]} disabled={!editable}
                description={available ? undefined : t('settings.notOnServer')}
                onChange={(e) => setNotify({ ...notify, [k]: e.currentTarget.checked })} />
            );
          })}
        </Stack>
        {editable && <Button mt="md" variant="light" loading={save.isPending} onClick={() => save.mutate()}>{t('rec.save')}</Button>}
      </Card>
    </Stack>
  );
}
