import { ActionIcon, Alert, Button, Card, Group, NumberInput, Select, Stack, Switch, Text, TextInput, Title, Tooltip } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError, type ProjectSettings as Settings, type ProjectCalendarT, type RecordType, type Routing, type SubmittalKind } from '../api';
import { pick } from '../i18n';
import ProjectHeader from './ProjectHeader';
import ConcreteClasses from './ConcreteClasses';
import { TYPE_TABS } from '../recordTypes';
import { cleanHolidays, HolidaysEditor, holidayText, WeekendPicker } from './Calendar';
import ProjectStructure from './ProjectStructure';

/** A period as days + hours (stored in hours). */
function Period({ hours, onChange, disabled, label }: { hours: number; onChange: (h: number) => void; disabled: boolean; label: string }) {
  const { t } = useTranslation();
  const d = Math.floor(hours / 24), h = hours % 24;
  const set = (nd: number, nh: number) => onChange(Math.max(1, nd * 24 + nh));
  return (
    <Group gap={6} wrap="nowrap" w={190}>
      <NumberInput w={92} min={0} max={365} disabled={disabled} aria-label={`${label} — ${t('settings.days')}`} value={d}
        rightSection={<Text size="xs" c="dimmed" pe={6}>{t('settings.days')}</Text>} rightSectionWidth={40}
        onChange={(v) => set(Number(v) || 0, h)} />
      <NumberInput w={92} min={0} max={23} disabled={disabled} aria-label={`${label} — ${t('settings.hours')}`} value={h}
        rightSection={<Text size="xs" c="dimmed" pe={6}>{t('settings.hours')}</Text>} rightSectionWidth={40}
        onChange={(v) => set(d, Math.min(23, Number(v) || 0))} />
    </Group>
  );
}

export default function ProjectSettings({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ['settings', projectId], queryFn: () => api<Settings>(`/projects/${projectId}/settings`) });
  const types = useQuery({ queryKey: ['recordTypes'], queryFn: () => api<RecordType[]>('/record-types') });
  const [reply, setReply] = useState<Record<string, number>>({});
  const [resub, setResub] = useState<Record<string, number>>({});
  const [links, setLinks] = useState(false);
  const [checks, setChecks] = useState(false);
  const [remind, setRemind] = useState(true);
  const [enabled, setEnabled] = useState<string[]>([]);
  const [cal, setCal] = useState<ProjectCalendarT>({ weekend: null, holidays: [], work_start: null, work_end: null });
  const [route, setRoute] = useState<Record<string, Routing>>({});
  const [notify, setNotify] = useState({ email: false, mahami: false });
  const [kinds, setKinds] = useState<SubmittalKind[]>([]);
  const [msg, setMsg] = useState<{ ok: boolean; text: string; at: string } | null>(null);
  useEffect(() => {
    if (settings.data) { setReply(settings.data.reply_hours); setResub(settings.data.resubmit_hours); setLinks(settings.data.link_submittals); setChecks(settings.data.checklists); setRemind(settings.data.reminders); setEnabled(settings.data.types); setCal(settings.data.calendar); setRoute(settings.data.routing); setNotify(settings.data.notify); setKinds(settings.data.submittal_kinds); }
  }, [settings.data]);
  const save = useMutation({
    mutationFn: (_at: string) =>
      api<Settings>(`/projects/${projectId}/settings`, { method: 'PUT', body: JSON.stringify({ reply_hours: reply, resubmit_hours: resub, link_submittals: links, checklists: checks, reminders: remind, routing: route, types: enabled,
        calendar: { ...cal, holidays: cleanHolidays(cal.holidays) }, notify, submittal_kinds: kinds }) }),
    onSuccess: (s, at) => {
      qc.setQueryData(['settings', projectId], s);
      qc.invalidateQueries({ queryKey: ['recMeta', projectId] });
      qc.invalidateQueries({ queryKey: ['structure', projectId] });
      qc.invalidateQueries({ queryKey: ['settings', projectId] });
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
      <Card withBorder>
        <Title order={5}>{t('settings.typesTitle')}</Title>
        <Text size="sm" c="dimmed" mb="md">{t('settings.typesHint')}</Text>
        <Group gap="lg">
          {TYPE_TABS.map(([code, tab]) => (
            <Switch key={code} label={t(`project.tabs.${tab}`)} disabled={!editable} checked={enabled.includes(code)}
              onChange={(e) => setEnabled(e.currentTarget.checked ? [...enabled, code] : enabled.filter((x) => x !== code))} />
          ))}
        </Group>
        {note('types')}
        {editable && <Button mt="md" variant="light" loading={save.isPending} disabled={!enabled.length} onClick={() => save.mutate('types')}>{t('rec.save')}</Button>}
      </Card>
      <ProjectStructure projectId={projectId} />
      {enabled.includes('test') && <ConcreteClasses projectId={projectId} editable={editable} />}
      <Card withBorder>
        <Title order={5}>{t('settings.reviewTitle')}</Title>
        <Text size="sm" c="dimmed" mb="md">{t('settings.reviewHint')}</Text>
        <Stack gap="sm">
          <Group justify="space-between" wrap="nowrap">
            <span />
            <Group gap="lg" wrap="nowrap">
              <Text size="xs" c="dimmed" w={190} ta="center">{t('settings.replyDays')}</Text>
              <Text size="xs" c="dimmed" w={190} ta="center">{t('settings.resubmitDays')}</Text>
            </Group>
          </Group>
          {types.data.map((rt) => (
            <Group key={rt.code} justify="space-between" wrap="nowrap">
              <Text size="sm">{pick(rt, 'name')}</Text>
              <Group gap="lg" wrap="nowrap">
                <Period hours={reply[rt.code] ?? 0} disabled={!editable} label={t('settings.replyDays')}
                  onChange={(h) => setReply({ ...reply, [rt.code]: h })} />
                <Period hours={resub[rt.code] ?? 0} disabled={!editable} label={t('settings.resubmitDays')}
                  onChange={(h) => setResub({ ...resub, [rt.code]: h })} />
              </Group>
            </Group>
          ))}
          <Title order={6} mt="sm">{t('settings.routingTitle')}</Title>
          <Text size="xs" c="dimmed">{t('settings.routingHint')}</Text>
          {types.data.map((rt) => (
            <Group key={rt.code} justify="space-between" wrap="nowrap">
              <Text size="sm">{pick(rt, 'name')}</Text>
              <Select w={400} allowDeselect={false} disabled={!editable} value={route[rt.code] ?? 'discipline'}
                onChange={(v) => v && setRoute({ ...route, [rt.code]: v as Routing })}
                data={(['discipline', 'manager', 'choose'] as const).map((m) => ({ value: m, label: t(`settings.routing.${m}`) }))} />
            </Group>
          ))}
          <Switch mt="xs" label={t('settings.reminders')} description={t('settings.remindersHint')} checked={remind}
            disabled={!editable} onChange={(e) => setRemind(e.currentTarget.checked)} />
          <Switch mt="xs" label={t('settings.checklists')} description={t('settings.checklistsHint')} checked={checks}
            disabled={!editable} onChange={(e) => setChecks(e.currentTarget.checked)} />
          <Switch mt="xs" label={t('settings.linkSubmittals')} description={t('settings.linkSubmittalsHint')} checked={links}
            disabled={!editable} onChange={(e) => setLinks(e.currentTarget.checked)} />
        </Stack>
        {note('days')}
        {editable ? <Button mt="md" loading={save.isPending} onClick={() => save.mutate('days')}>{t('rec.save')}</Button>
          : <Text size="xs" c="dimmed" mt="md">{t('settings.readOnly')}</Text>}
      </Card>
      <Card withBorder>
        <Title order={5}>{t('cal.projectTitle')}</Title>
        <Text size="sm" c="dimmed" mb="md">{t('cal.projectHint')}</Text>
        <Text fw={600} size="sm" mb={6}>{t('cal.weekend')}</Text>
        <Switch mb="xs" disabled={!editable} checked={cal.weekend === null}
          label={t('cal.useOrgWeekend', { days: settings.data.org_calendar.weekend.map((d) => t(`cal.day.${d}`)).join('، ') || t('cal.none') })}
          onChange={(e) => setCal({ ...cal, weekend: e.currentTarget.checked ? null : [...settings.data!.org_calendar.weekend] })} />
        {cal.weekend !== null && <WeekendPicker value={cal.weekend} disabled={!editable} onChange={(w) => setCal({ ...cal, weekend: w })} />}
        <Text fw={600} size="sm" mt="lg" mb={6}>{t('cal.workHours')}</Text>
        <Switch mb="xs" disabled={!editable} checked={cal.work_start !== null} label={t('cal.workHoursOn')} description={t('cal.workHoursHint')}
          onChange={(e) => setCal({ ...cal, ...(e.currentTarget.checked ? { work_start: '07:00', work_end: '15:00' } : { work_start: null, work_end: null }) })} />
        {cal.work_start !== null && (
          <Group>
            <TextInput type="time" w={140} label={t('cal.from')} disabled={!editable} value={cal.work_start ?? ''}
              onChange={(e) => setCal({ ...cal, work_start: e.currentTarget.value })} />
            <TextInput type="time" w={140} label={t('cal.to')} disabled={!editable} value={cal.work_end ?? ''}
              onChange={(e) => setCal({ ...cal, work_end: e.currentTarget.value })} />
          </Group>
        )}
        <Text fw={600} size="sm" mt="lg" mb={6}>{t('cal.orgHolidays')}</Text>
        {settings.data.org_calendar.holidays.length
          ? <Text size="sm">{settings.data.org_calendar.holidays.map(holidayText).join(' · ')}</Text>
          : <Text size="sm" c="dimmed">{t('cal.noOrgHolidays')}</Text>}
        <Text fw={600} size="sm" mt="lg" mb={6}>{t('cal.projectHolidays')}</Text>
        <HolidaysEditor value={cal.holidays} editable={editable} onChange={(h) => setCal({ ...cal, holidays: h })} />
        {note('calendar')}
        {editable && <Button mt="md" variant="light" loading={save.isPending} onClick={() => save.mutate('calendar')}>{t('rec.save')}</Button>}
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
