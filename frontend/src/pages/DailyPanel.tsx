import {
  ActionIcon, Alert, Anchor, Autocomplete, Badge, Button, Card, Checkbox, Group, MultiSelect, NumberInput, ScrollArea, Select, SimpleGrid, Stack, Table, Tabs,
  Text, Textarea, TextInput, Title,
} from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { api, ApiError, type LinkedRef, type RecordDetail } from '../api';
import {
  blankWork, CAUSES, GROUPS, WEATHER, type CrewLine, type DailyData, type DailyOut, type DailySettings, type DelayLine, type EquipLine,
  type Group as CrewGroup, type MaterialLine, type WorkLine,
} from '../daily';
import i18n, { pick } from '../i18n';
import { locationOptions, useStructure } from './Structure';

const errText = (e: unknown) => i18n.t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, { defaultValue: i18n.t('errors.generic') });
const num = (v: string | number) => (v === '' || v === null || v === undefined ? null : Number(v));
const Del = ({ onClick }: { onClick: () => void }) => <ActionIcon size="sm" variant="subtle" color="red" aria-label="remove" onClick={onClick}>×</ActionIcon>;

/** Work lines: stage → topic → where, what, quantity, crew and the cumulative % of the cell(s). */
function WorksTable({ lines, onChange, editable, projectId, current, withProgress }: {
  lines: WorkLine[]; onChange: (l: WorkLine[]) => void; editable: boolean; projectId: string; current: Record<string, number>; withProgress: boolean;
}) {
  const { t } = useTranslation();
  const s = useStructure(projectId).data;
  if (!s) return null;
  const set = (i: number, p: Partial<WorkLine>) => onChange(lines.map((x, j) => (j === i ? { ...x, ...p } : x)));
  const stages = s.stages.filter((x) => x.is_active).map((x) => ({ value: x.id!, label: pick(x, 'name') }));
  const locs = locationOptions(s);
  const unitIds = (w: WorkLine) => {
    if (w.all_locations) return s.locations.flatMap((g) => g.units.map((u) => u.id!));
    return s.locations.flatMap((g) => (w.location_ids.includes(g.id!) ? g.units.map((u) => u.id!) : g.units.filter((u) => w.location_ids.includes(u.id!)).map((u) => u.id!)));
  };
  const was = (w: WorkLine) => {
    const st = s.stages.find((x) => x.id === w.stage_id);
    if (!st) return null;
    const vals = st.scope === 'whole' ? [current[`${st.id}:`] ?? 0] : unitIds(w).map((u) => current[`${st.id}:${u}`] ?? 0);
    if (!vals.length) return null;
    const lo = Math.min(...vals), hi = Math.max(...vals);
    return lo === hi ? `${lo}%` : `${lo}–${hi}%`;
  };
  return (
    <Stack gap={6}>
      {lines.map((w, i) => {
        const st = s.stages.find((x) => x.id === w.stage_id);
        const whole = st?.scope === 'whole';
        return (
          <Card key={i} withBorder p="xs">
            <SimpleGrid cols={{ base: 1, sm: 4 }} spacing="xs">
              <Select size="xs" label={t('structure.stage')} data={stages} value={w.stage_id} disabled={!editable} searchable clearable
                onChange={(v) => set(i, { stage_id: v, topic_id: null })} />
              <Select size="xs" label={t('structure.topic')} disabled={!editable || !st} clearable searchable value={w.topic_id}
                data={(st?.topics ?? []).filter((x) => x.id && x.is_active !== false).map((x) => ({ value: x.id!, label: pick(x, 'name') }))}
                onChange={(v) => set(i, { topic_id: v })} />
              {whole ? <Text size="xs" c="dimmed" pt={24}>{t('daily.wholeStage')}</Text> : (
                <Stack gap={2} style={{ gridColumn: 'span 2' }}>
                  <MultiSelect size="xs" label={t('structure.location')} searchable clearable data={locs as never} value={w.location_ids}
                    disabled={!editable || w.all_locations} onChange={(v) => set(i, { location_ids: v })} />
                  <Checkbox size="xs" label={t('structure.wholeProject')} checked={w.all_locations} disabled={!editable}
                    onChange={(e) => set(i, { all_locations: e.currentTarget.checked, location_ids: [] })} />
                </Stack>
              )}
            </SimpleGrid>
            <Group gap="xs" mt={6} align="flex-end" wrap="nowrap">
              <TextInput size="xs" style={{ flex: 1 }} label={t('daily.desc')} value={w.description ?? ''} disabled={!editable}
                onChange={(e) => set(i, { description: e.currentTarget.value || null })} />
              <NumberInput size="xs" w={80} hideControls label={t('daily.qty')} value={w.qty ?? ''} disabled={!editable} onChange={(v) => set(i, { qty: num(v) })} />
              <TextInput size="xs" w={70} label={t('daily.unit')} dir="ltr" value={w.unit ?? ''} disabled={!editable} onChange={(e) => set(i, { unit: e.currentTarget.value || null })} />
              <NumberInput size="xs" w={70} hideControls label={t('daily.crewN')} value={w.crew ?? ''} disabled={!editable} onChange={(v) => set(i, { crew: num(v) })} />
              {withProgress && (
                <NumberInput size="xs" w={110} label={t('daily.progress')} description={st ? `${t('daily.was')}: ${was(w) ?? '0%'}` : undefined}
                  min={0} max={100} suffix="%" value={w.progress ?? ''} disabled={!editable || !st} onChange={(v) => set(i, { progress: num(v) })} />
              )}
              {editable && <Del onClick={() => onChange(lines.filter((_, j) => j !== i))} />}
            </Group>
          </Card>
        );
      })}
      {editable && <Group><Button size="compact-xs" variant="subtle" onClick={() => onChange([...lines, blankWork()])}>+ {t('daily.addWork')}</Button></Group>}
    </Stack>
  );
}

/** Staff and labour: names or trade + count per group, as the project settings say. */
function CrewTable({ lines, onChange, editable, settings }: { lines: CrewLine[]; onChange: (l: CrewLine[]) => void; editable: boolean; settings: DailySettings }) {
  const { t } = useTranslation();
  const subs = settings.lists.subcontractors ?? [];
  return (
    <Stack gap="sm">
      {GROUPS.map((g: CrewGroup) => {
        const rows = lines.map((x, i) => ({ x, i })).filter((r) => r.x.group === g);
        const names = settings.crew[g] === 'names';
        const opts = settings.lists[g] ?? [];
        const set = (i: number, p: Partial<CrewLine>) => onChange(lines.map((x, j) => (j === i ? { ...x, ...p } : x)));
        const total = rows.reduce((a, r) => a + (r.x.count || 0), 0);
        return (
          <div key={g}>
            <Text size="sm" fw={600}>{t(`daily.g.${g}`)} <Badge size="sm" variant="light">{total}</Badge></Text>
            {rows.map(({ x, i }) => (
              <Group key={i} gap="xs" mt={4} wrap="nowrap">
                <Autocomplete size="xs" style={{ flex: 1 }} placeholder={t(names ? 'daily.person' : 'daily.trade')} disabled={!editable} value={x.name}
                  data={opts} onChange={(v) => set(i, { name: v })} />
                {g !== 'supervision' && subs.length > 0 && (
                  <Select size="xs" w={170} placeholder={t('daily.sub')} clearable disabled={!editable} value={x.sub} data={subs} onChange={(v) => set(i, { sub: v })} />
                )}
                {!names && <NumberInput size="xs" w={80} min={0} disabled={!editable} value={x.count} onChange={(v) => set(i, { count: Number(v) || 0 })} />}
                <NumberInput size="xs" w={80} hideControls placeholder={t('daily.hours')} disabled={!editable} value={x.hours ?? ''} onChange={(v) => set(i, { hours: num(v) })} />
                {editable && <Del onClick={() => onChange(lines.filter((_, j) => j !== i))} />}
              </Group>
            ))}
            {editable && <Button mt={2} size="compact-xs" variant="subtle" onClick={() => onChange([...lines, { group: g, sub: null, name: '', count: 1, hours: 8 }])}>+ {t('daily.add')}</Button>}
          </div>
        );
      })}
      <Text size="xs" c="dimmed">{t('daily.crewHint')}</Text>
    </Stack>
  );
}

export default function DailyPanel({ rec }: { rec: RecordDetail }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['daily', rec.id], queryFn: () => api<DailyOut>(`/records/${rec.id}/daily`) });
  const settings = useQuery({ queryKey: ['dailySettings', rec.project_id], queryFn: () => api<DailySettings>(`/projects/${rec.project_id}/daily-settings`) });
  const subs = useQuery({ queryKey: ['linkCandidates', rec.project_id, 'all'], enabled: !!settings.data?.link_materials,
    queryFn: () => api<LinkedRef[]>(`/projects/${rec.project_id}/link-candidates`) });
  const [d, setD] = useState<DailyData | null>(null);
  const [dirty, setDirty] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => { if (q.data && !dirty) setD(q.data); }, [q.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = useMutation({
    mutationFn: () => api<DailyOut>(`/records/${rec.id}/daily`, { method: 'PUT', body: JSON.stringify(d) }),
    onSuccess: (x) => { qc.setQueryData(['daily', rec.id], x); setD(x); setDirty(false); setMsg({ ok: true, text: t('settings.saved') }); },
    onError: (e) => setMsg({ ok: false, text: errText(e) }),
  });
  const mir = useMutation({
    mutationFn: async (i: number) => {
      const m = d!.materials[i];
      const r = await api<{ id: string }>(`/projects/${rec.project_id}/records`, { method: 'POST', body: JSON.stringify({
        record_type: 'material', title: m.material, details: { supplier: m.supplier, quantity: m.qty, unit: m.unit, item: m.material },
        custom: { delivery_note: m.delivery_note }, linked_ids: m.submittal_id ? [m.submittal_id] : [] }) });
      return { i, id: r.id };
    },
    onSuccess: ({ i, id }) => { setD({ ...d!, materials: d!.materials.map((x, j) => (j === i ? { ...x, mir_id: id } : x)) }); setDirty(true); setMsg({ ok: true, text: t('daily.mirCreated') }); },
    onError: (e) => setMsg({ ok: false, text: errText(e) }),
  });
  const out = q.data;
  if (!out || !d || !settings.data) return null;
  const ed = out.can_edit;
  const set = (p: Partial<DailyData>) => { setD({ ...d, ...p }); setDirty(true); };
  const S = settings.data;
  const opt = (k: string, list: string[]) => list.map((v) => ({ value: v, label: t(`daily.${k}.${v}`) }));
  const equipOpts = S.lists.equipment ?? [];

  return (
    <Card withBorder style={{ borderColor: 'var(--mantine-color-verqac-3)' }}>
      <Group justify="space-between" mb="xs">
        <Title order={5}>{t('daily.title')} · {out.report_date}</Title>
        <Group gap="xs">
          {GROUPS.map((g) => <Badge key={g} variant="light" tt="none">{t(`daily.g.${g}`)}: {d.crew.filter((x) => x.group === g).reduce((a, x) => a + (x.count || 0), 0)}</Badge>)}
          <Badge variant="light" tt="none" color="gray">{t('daily.equipment')}: {d.equipment.reduce((a, x) => a + (x.count || 0), 0)}</Badge>
        </Group>
      </Group>
      {msg && <Alert mb="sm" color={msg.ok ? 'green' : 'red'} withCloseButton onClose={() => setMsg(null)}>{msg.text}</Alert>}
      <Tabs defaultValue="day" keepMounted={false}>
        <Tabs.List mb="sm">
          <Tabs.Tab value="day">{t('daily.tabs.day')}</Tabs.Tab>
          <Tabs.Tab value="crew">{t('daily.tabs.crew')}</Tabs.Tab>
          <Tabs.Tab value="works">{t('daily.tabs.works')} ({d.works.length})</Tabs.Tab>
          <Tabs.Tab value="materials">{t('daily.tabs.materials')}</Tabs.Tab>
          <Tabs.Tab value="planned">{t('daily.tabs.planned')}</Tabs.Tab>
          <Tabs.Tab value="issues">{t('daily.tabs.issues')}</Tabs.Tab>
          <Tabs.Tab value="qa">{t('daily.tabs.qa')}</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="day">
          <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="xs">
            <Select size="xs" label={t('daily.shift')} allowDeselect={false} disabled={!ed} value={d.shift} data={opt('v', ['day', 'night', 'both'])} onChange={(v) => set({ shift: v as DailyData['shift'] })} />
            <Select size="xs" label={t('daily.status')} allowDeselect={false} disabled={!ed} value={d.work_status} data={opt('v', ['normal', 'partial', 'stopped'])} onChange={(v) => set({ work_status: v as DailyData['work_status'] })} />
            <TextInput size="xs" type="time" label={t('daily.from')} disabled={!ed} value={d.hours_from ?? ''} onChange={(e) => set({ hours_from: e.currentTarget.value || null })} />
            <TextInput size="xs" type="time" label={t('daily.to')} disabled={!ed} value={d.hours_to ?? ''} onChange={(e) => set({ hours_to: e.currentTarget.value || null })} />
            <Select size="xs" label={t('daily.weather')} clearable disabled={!ed} value={d.weather} data={opt('v', WEATHER)} onChange={(v) => set({ weather: v })} />
            <NumberInput size="xs" label={t('daily.tmin')} suffix="°" disabled={!ed} value={d.temp_min ?? ''} onChange={(v) => set({ temp_min: num(v) })} />
            <NumberInput size="xs" label={t('daily.tmax')} suffix="°" disabled={!ed} value={d.temp_max ?? ''} onChange={(v) => set({ temp_max: num(v) })} />
            <Select size="xs" label={t('daily.wind')} clearable disabled={!ed} value={d.wind} data={opt('v', ['calm', 'moderate', 'strong'])} onChange={(v) => set({ wind: v })} />
          </SimpleGrid>
          {d.work_status !== 'normal' && <TextInput mt="xs" size="xs" label={t('daily.stopReason')} disabled={!ed} value={d.stop_reason ?? ''} onChange={(e) => set({ stop_reason: e.currentTarget.value || null })} />}
          <Text fw={600} size="sm" mt="md">{t('daily.equipment')}</Text>
          {d.equipment.map((x: EquipLine, i) => (
            <Group key={i} gap="xs" mt={4} wrap="nowrap">
              <Autocomplete size="xs" style={{ flex: 1 }} disabled={!ed} value={x.name} data={equipOpts}
                onChange={(v) => set({ equipment: d.equipment.map((y, j) => (j === i ? { ...y, name: v } : y)) })} />
              <NumberInput size="xs" w={70} min={0} disabled={!ed} value={x.count} onChange={(v) => set({ equipment: d.equipment.map((y, j) => (j === i ? { ...y, count: Number(v) || 0 } : y)) })} />
              <NumberInput size="xs" w={80} hideControls placeholder={t('daily.hours')} disabled={!ed} value={x.hours ?? ''} onChange={(v) => set({ equipment: d.equipment.map((y, j) => (j === i ? { ...y, hours: num(v) } : y)) })} />
              <NumberInput size="xs" w={80} hideControls placeholder={t('daily.idle')} disabled={!ed} value={x.idle_hours ?? ''} onChange={(v) => set({ equipment: d.equipment.map((y, j) => (j === i ? { ...y, idle_hours: num(v) } : y)) })} />
              {ed && <Del onClick={() => set({ equipment: d.equipment.filter((_, j) => j !== i) })} />}
            </Group>
          ))}
          {ed && <Button mt={2} size="compact-xs" variant="subtle" onClick={() => set({ equipment: [...d.equipment, { name: '', count: 1, hours: 8, idle_hours: null, note: null }] })}>+ {t('daily.add')}</Button>}
        </Tabs.Panel>

        <Tabs.Panel value="crew"><CrewTable lines={d.crew} onChange={(l) => set({ crew: l })} editable={ed} settings={S} /></Tabs.Panel>

        <Tabs.Panel value="works">
          <Text size="xs" c="dimmed" mb={6}>{t('daily.worksHint')}</Text>
          <WorksTable lines={d.works} onChange={(l) => set({ works: l })} editable={ed} projectId={rec.project_id} current={out.current} withProgress />
        </Tabs.Panel>

        <Tabs.Panel value="materials">
          <ScrollArea>
            <Table withTableBorder verticalSpacing={2} horizontalSpacing={4} fz="sm" miw={760}>
              <Table.Thead><Table.Tr>
                <Table.Th>{t('daily.material')}</Table.Th><Table.Th w={80}>{t('daily.qty')}</Table.Th><Table.Th w={70}>{t('daily.unit')}</Table.Th>
                <Table.Th w={150}>{t('daily.supplier')}</Table.Th><Table.Th w={110}>{t('daily.dn')}</Table.Th>
                {S.link_materials && <Table.Th w={200}>{t('daily.submittal')}</Table.Th>}{ed && <Table.Th w={30} />}
              </Table.Tr></Table.Thead>
              <Table.Tbody>
                {d.materials.map((m: MaterialLine, i) => {
                  const setM = (p: Partial<MaterialLine>) => set({ materials: d.materials.map((y, j) => (j === i ? { ...y, ...p } : y)) });
                  return (
                    <Table.Tr key={i}>
                      <Table.Td><TextInput size="xs" disabled={!ed} value={m.material} onChange={(e) => setM({ material: e.currentTarget.value })} /></Table.Td>
                      <Table.Td><NumberInput size="xs" hideControls disabled={!ed} value={m.qty ?? ''} onChange={(v) => setM({ qty: num(v) })} /></Table.Td>
                      <Table.Td><TextInput size="xs" dir="ltr" disabled={!ed} value={m.unit ?? ''} onChange={(e) => setM({ unit: e.currentTarget.value || null })} /></Table.Td>
                      <Table.Td><TextInput size="xs" disabled={!ed} value={m.supplier ?? ''} onChange={(e) => setM({ supplier: e.currentTarget.value || null })} /></Table.Td>
                      <Table.Td><TextInput size="xs" dir="ltr" disabled={!ed} value={m.delivery_note ?? ''} onChange={(e) => setM({ delivery_note: e.currentTarget.value || null })} /></Table.Td>
                      {S.link_materials && (
                        <Table.Td>
                          <Select size="xs" clearable searchable disabled={!ed} value={m.submittal_id}
                            data={(subs.data ?? []).map((x) => ({ value: x.id, label: `${x.number} · ${x.title}${['approved', 'approved_as_noted'].includes(x.state.category) ? ' ✓' : ''}` }))}
                            onChange={(v) => setM({ submittal_id: v })} />
                          {m.mir_id ? <Anchor component={Link} to={`/records/${m.mir_id}`} size="xs">{t('daily.mirOpen')}</Anchor>
                            : ed && m.material && <Button size="compact-xs" variant="subtle" loading={mir.isPending} onClick={() => mir.mutate(i)}>{t('daily.mirCreate')}</Button>}
                        </Table.Td>
                      )}
                      {ed && <Table.Td><Del onClick={() => set({ materials: d.materials.filter((_, j) => j !== i) })} /></Table.Td>}
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          </ScrollArea>
          {ed && <Button mt={4} size="compact-xs" variant="subtle" onClick={() => set({ materials: [...d.materials, { material: '', qty: null, unit: null, supplier: null, delivery_note: null, submittal_id: null, mir_id: null }] })}>+ {t('daily.add')}</Button>}
        </Tabs.Panel>

        <Tabs.Panel value="planned">
          <Text size="xs" c="dimmed" mb={6}>{t('daily.plannedHint')}</Text>
          <WorksTable lines={d.planned} onChange={(l) => set({ planned: l })} editable={ed} projectId={rec.project_id} current={out.current} withProgress={false} />
        </Tabs.Panel>

        <Tabs.Panel value="issues">
          <Text fw={600} size="sm">{t('daily.delays')}</Text>
          {d.delays.map((x: DelayLine, i) => (
            <Group key={i} gap="xs" mt={4} wrap="nowrap">
              <Select size="xs" w={190} allowDeselect={false} disabled={!ed} value={x.cause} data={opt('cause', CAUSES)}
                onChange={(v) => set({ delays: d.delays.map((y, j) => (j === i ? { ...y, cause: v ?? 'other' } : y)) })} />
              <TextInput size="xs" style={{ flex: 1 }} disabled={!ed} value={x.description ?? ''} onChange={(e) => set({ delays: d.delays.map((y, j) => (j === i ? { ...y, description: e.currentTarget.value || null } : y)) })} />
              <NumberInput size="xs" w={90} hideControls placeholder={t('daily.lostHours')} disabled={!ed} value={x.hours ?? ''} onChange={(v) => set({ delays: d.delays.map((y, j) => (j === i ? { ...y, hours: num(v) } : y)) })} />
              {ed && <Del onClick={() => set({ delays: d.delays.filter((_, j) => j !== i) })} />}
            </Group>
          ))}
          {ed && <Button mt={2} size="compact-xs" variant="subtle" onClick={() => set({ delays: [...d.delays, { cause: 'other', hours: null, description: null, link_id: null }] })}>+ {t('daily.add')}</Button>}
          <Text fw={600} size="sm" mt="md">{t('daily.hse')}</Text>
          <SimpleGrid cols={3} spacing="xs">
            {(['incidents', 'near_misses', 'toolbox'] as const).map((k) => (
              <NumberInput key={k} size="xs" min={0} label={t(`daily.${k}`)} disabled={!ed} value={d.hse[k]} onChange={(v) => set({ hse: { ...d.hse, [k]: Number(v) || 0 } })} />
            ))}
          </SimpleGrid>
          <Textarea mt="xs" size="xs" autosize minRows={1} label={t('daily.hseNotes')} disabled={!ed} value={d.hse.notes ?? ''} onChange={(e) => set({ hse: { ...d.hse, notes: e.currentTarget.value || null } })} />
          <Textarea mt="xs" size="xs" autosize minRows={1} label={t('daily.visitors')} disabled={!ed} value={d.visitors ?? ''} onChange={(e) => set({ visitors: e.currentTarget.value || null })} />
          <Textarea mt="xs" size="xs" autosize minRows={2} label={t('daily.notes')} disabled={!ed} value={d.notes ?? ''} onChange={(e) => set({ notes: e.currentTarget.value || null })} />
        </Tabs.Panel>

        <Tabs.Panel value="qa">
          <Text size="xs" c="dimmed" mb={6}>{t('daily.qaHint')}</Text>
          {out.qa.length === 0 ? <Text size="sm" c="dimmed">{t('daily.qaNone')}</Text> : (
            <Table withTableBorder fz="sm"><Table.Tbody>
              {out.qa.map((x) => <Table.Tr key={x.code}><Table.Td>{pick(x, 'name')}</Table.Td><Table.Td>{t('daily.submitted')}: {x.submitted}</Table.Td><Table.Td>{t('daily.answered')}: {x.answered}</Table.Td></Table.Tr>)}
            </Table.Tbody></Table>
          )}
        </Tabs.Panel>
      </Tabs>
      {ed && <Group mt="md"><Button loading={save.isPending} disabled={!dirty} onClick={() => save.mutate()}>{t('daily.save')}</Button>
        {dirty && <Text size="xs" c="orange.8">{t('daily.unsaved')}</Text>}</Group>}
    </Card>
  );
}
