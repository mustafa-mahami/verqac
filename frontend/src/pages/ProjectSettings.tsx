import { ActionIcon, Alert, Button, Card, Group, NumberInput, Stack, Switch, Text, TextInput, Title, Tooltip } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError, type ProjectSettings as Settings, type RecordType, type SubmittalKind } from '../api';
import { pick } from '../i18n';
import ProjectHeader from './ProjectHeader';
import ProjectStructure from './ProjectStructure';

export default function ProjectSettings({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ['settings', projectId], queryFn: () => api<Settings>(`/projects/${projectId}/settings`) });
  const types = useQuery({ queryKey: ['recordTypes'], queryFn: () => api<RecordType[]>('/record-types') });
  const [days, setDays] = useState<Record<string, number>>({});
  const [redays, setRedays] = useState<Record<string, number>>({});
  const [notify, setNotify] = useState({ email: false, mahami: false });
  const [kinds, setKinds] = useState<SubmittalKind[]>([]);
  const [msg, setMsg] = useState<{ ok: boolean; text: string; at: string } | null>(null);
  useEffect(() => {
    if (settings.data) { setDays(settings.data.review_days); setRedays(settings.data.resubmit_days); setNotify(settings.data.notify); setKinds(settings.data.submittal_kinds); }
  }, [settings.data]);
  const save = useMutation({
    mutationFn: (_at: string) =>
      api<Settings>(`/projects/${projectId}/settings`, { method: 'PUT', body: JSON.stringify({ review_days: days, resubmit_days: redays, notify, submittal_kinds: kinds }) }),
    onSuccess: (s, at) => {
      qc.setQueryData(['settings', projectId], s);
      qc.invalidateQueries({ queryKey: ['recMeta', projectId] });
      setMsg({ ok: true, text: t('settings.saved'), at });
    },
    onError: (e, at) => setMsg({ ok: false, text: t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic')), at }),
  });
  const note = (at: string) => msg && msg.at === at && <Alert mt="md" color={msg.ok ? 'green' : 'red'}>{msg.text}</Alert>;
  const setKind = (i: number, patch: Partial<SubmittalKind>) => setKinds(kinds.map((k, j) => (j === i ? { ...k, ...patch } : k)));
  const move = (i: number, d: number) => {
    const next = [...kinds];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    setKinds(next);
  };
  if (!settings.data || !types.data) return null;
  const editable = settings.data.can_edit;

  return (
    <Stack maw={900}>
      <ProjectHeader projectId={projectId} settings={settings.data} />
      <ProjectStructure projectId={projectId} />
      <Card withBorder>
        <Title order={5}>{t('settings.reviewTitle')}</Title>
        <Text size="sm" c="dimmed" mb="md">{t('settings.reviewHint')}</Text>
        <Stack gap="sm">
          <Group justify="space-between" wrap="nowrap">
            <span />
            <Group gap="md" wrap="nowrap">
              <Text size="xs" c="dimmed" w={140} ta="center">{t('settings.replyDays')}</Text>
              <Text size="xs" c="dimmed" w={140} ta="center">{t('settings.resubmitDays')}</Text>
            </Group>
          </Group>
          {types.data.map((rt) => (
            <Group key={rt.code} justify="space-between" wrap="nowrap">
              <Text size="sm">{pick(rt, 'name')}</Text>
              <Group gap="md" wrap="nowrap">
                <NumberInput w={140} min={1} max={365} disabled={!editable} rightSection={<Text size="xs" c="dimmed" pe={8}>{t('settings.days')}</Text>}
                  rightSectionWidth={44} value={days[rt.code] ?? rt.review_days} aria-label={t('settings.replyDays')}
                  onChange={(v) => setDays({ ...days, [rt.code]: Number(v) || 1 })} />
                <NumberInput w={140} min={1} max={365} disabled={!editable} rightSection={<Text size="xs" c="dimmed" pe={8}>{t('settings.days')}</Text>}
                  rightSectionWidth={44} value={redays[rt.code] ?? 7} aria-label={t('settings.resubmitDays')}
                  onChange={(v) => setRedays({ ...redays, [rt.code]: Number(v) || 1 })} />
              </Group>
            </Group>
          ))}
        </Stack>
        {note('days')}
        {editable ? <Button mt="md" loading={save.isPending} onClick={() => save.mutate('days')}>{t('rec.save')}</Button>
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
        {note('notify')}
        {editable && <Button mt="md" variant="light" loading={save.isPending} onClick={() => save.mutate('notify')}>{t('rec.save')}</Button>}
      </Card>
      <Card withBorder>
        <Title order={5}>{t('settings.kindsTitle')}</Title>
        <Text size="sm" c="dimmed" mb="md">{t('settings.kindsHint')}</Text>
        <Stack gap="xs">
          {kinds.map((k, i) => (
            <Group key={k.code ?? `new-${i}`} gap="xs" wrap="nowrap" align="center" opacity={k.active ? 1 : 0.55}>
              <TextInput flex={1} size="sm" placeholder={t('settings.kindAr')} aria-label={t('settings.kindAr')} disabled={!editable}
                value={k.name_ar} onChange={(e) => setKind(i, { name_ar: e.currentTarget.value })} />
              <TextInput flex={1} size="sm" dir="ltr" placeholder={t('settings.kindEn')} aria-label={t('settings.kindEn')} disabled={!editable}
                value={k.name_en} onChange={(e) => setKind(i, { name_en: e.currentTarget.value })} />
              <Tooltip label={t(k.active ? 'settings.kindActive' : 'settings.kindInactive')}>
                <Switch size="sm" checked={k.active} disabled={!editable} aria-label={t('settings.kindActive')}
                  onChange={(e) => setKind(i, { active: e.currentTarget.checked })} />
              </Tooltip>
              {editable && (
                <>
                  <ActionIcon variant="subtle" color="gray" disabled={i === 0} aria-label="up" onClick={() => move(i, -1)}>↑</ActionIcon>
                  <ActionIcon variant="subtle" color="gray" disabled={i === kinds.length - 1} aria-label="down" onClick={() => move(i, 1)}>↓</ActionIcon>
                  <ActionIcon variant="subtle" color="red" aria-label="remove" onClick={() => setKinds(kinds.filter((_, j) => j !== i))}>×</ActionIcon>
                </>
              )}
            </Group>
          ))}
        </Stack>
        {editable && (
          <Button mt="sm" size="xs" variant="subtle" onClick={() => setKinds([...kinds, { code: null, name_ar: '', name_en: '', active: true }])}>
            + {t('settings.kindAdd')}
          </Button>
        )}
        {note('kinds')}
        {editable && <Button mt="md" variant="light" loading={save.isPending} onClick={() => save.mutate('kinds')}>{t('rec.save')}</Button>}
      </Card>
    </Stack>
  );
}
