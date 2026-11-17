import { ActionIcon, Alert, Button, Card, Checkbox, Group, Stack, Table, Text, TextInput, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../api';
import { fmtDate } from '../format';

export interface Holiday { from: string; to: string | null; name: string }
export interface OrgCalendarT { weekend: number[]; holidays: Holiday[] }

const DAYS = [0, 1, 2, 3, 4, 5, 6]; // Sunday ... Saturday

export function WeekendPicker({ value, onChange, disabled }: { value: number[]; onChange: (v: number[]) => void; disabled?: boolean }) {
  const { t } = useTranslation();
  return (
    <Group gap="md">
      {DAYS.map((d) => (
        <Checkbox key={d} label={t(`cal.day.${d}`)} disabled={disabled} checked={value.includes(d)}
          onChange={(e) => onChange(e.currentTarget.checked ? [...value, d].sort() : value.filter((x) => x !== d))} />
      ))}
    </Group>
  );
}

const days = (h: Holiday) => {
  if (!h.from) return 0;
  const a = new Date(h.from), b = new Date(h.to || h.from);
  return Math.round((b.getTime() - a.getTime()) / 86400000) + 1;
};

export function HolidaysEditor({ value, onChange, editable }: { value: Holiday[]; onChange: (v: Holiday[]) => void; editable: boolean }) {
  const { t } = useTranslation();
  const set = (i: number, patch: Partial<Holiday>) => onChange(value.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  return (
    <Stack gap="xs">
      {value.length === 0 && <Text size="sm" c="dimmed">{t('cal.noHolidays')}</Text>}
      {value.length > 0 && (
        <Table withRowBorders={false} verticalSpacing={4}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('cal.name')}</Table.Th><Table.Th w={170}>{t('cal.from')}</Table.Th>
              <Table.Th w={170}>{t('cal.to')}</Table.Th><Table.Th w={70}>{t('cal.days')}</Table.Th>{editable && <Table.Th w={40} />}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {value.map((h, i) => (
              <Table.Tr key={i}>
                <Table.Td><TextInput size="xs" disabled={!editable} value={h.name} placeholder={t('cal.namePh')}
                  onChange={(e) => set(i, { name: e.currentTarget.value })} /></Table.Td>
                <Table.Td><TextInput size="xs" type="date" disabled={!editable} value={h.from}
                  onChange={(e) => set(i, { from: e.currentTarget.value })} /></Table.Td>
                <Table.Td><TextInput size="xs" type="date" disabled={!editable} value={h.to ?? ''} min={h.from}
                  onChange={(e) => set(i, { to: e.currentTarget.value || null })} /></Table.Td>
                <Table.Td><Text size="sm">{days(h) || ''}</Text></Table.Td>
                {editable && <Table.Td><ActionIcon size="sm" variant="subtle" color="red" aria-label="remove"
                  onClick={() => onChange(value.filter((_, j) => j !== i))}>×</ActionIcon></Table.Td>}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      {editable && <Group><Button size="compact-xs" variant="subtle" onClick={() => onChange([...value, { from: '', to: null, name: '' }])}>+ {t('cal.addHoliday')}</Button></Group>}
    </Stack>
  );
}

export const cleanHolidays = (v: Holiday[]) => v.filter((h) => h.from).map((h) => ({ ...h, to: h.to || h.from }));

export const holidayText = (h: Holiday) =>
  `${h.name || ''} ${fmtDate(h.from)}${h.to && h.to !== h.from ? ` – ${fmtDate(h.to)}` : ''}`.trim();

/** The organization's calendar: weekly days off and official holidays, used by all its projects. */
export default function OrgCalendar({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['orgCalendar', orgId], queryFn: () => api<OrgCalendarT>(`/orgs/${orgId}/calendar`) });
  const [weekend, setWeekend] = useState<number[]>([5]);
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => { if (q.data) { setWeekend(q.data.weekend); setHolidays(q.data.holidays); } }, [q.data]);
  const save = useMutation({
    mutationFn: () => api<OrgCalendarT>(`/orgs/${orgId}/calendar`, { method: 'PUT', body: JSON.stringify({ weekend, holidays: cleanHolidays(holidays) }) }),
    onSuccess: (d) => { qc.setQueryData(['orgCalendar', orgId], d); setMsg({ ok: true, text: t('settings.saved') }); },
    onError: (e) => setMsg({ ok: false, text: t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic')) }),
  });
  if (!q.data) return null;
  return (
    <Card withBorder maw={900}>
      <Title order={5}>{t('cal.orgTitle')}</Title>
      <Text size="sm" c="dimmed" mb="md">{t('cal.orgHint')}</Text>
      <Text fw={600} size="sm" mb={6}>{t('cal.weekend')}</Text>
      <WeekendPicker value={weekend} onChange={setWeekend} />
      <Text fw={600} size="sm" mt="lg" mb={6}>{t('cal.holidays')}</Text>
      <HolidaysEditor value={holidays} onChange={setHolidays} editable />
      {msg && <Alert mt="md" color={msg.ok ? 'green' : 'red'}>{msg.text}</Alert>}
      <Button mt="md" loading={save.isPending} onClick={() => save.mutate()}>{t('rec.save')}</Button>
    </Card>
  );
}
