import { Accordion, ActionIcon, Alert, Badge, Button, Group, NumberInput, Select, SimpleGrid, Stack, Switch, Table, Text, TextInput } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../api';
import { pick } from '../i18n';
import { blankLine, MATERIALS, type LabLine, type LabTemplate } from '../lab';

/** The organization's laboratory test templates: parameters, units, test methods and acceptance limits. */
export default function LabTemplates({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['orgLabTemplates', orgId], queryFn: () => api<LabTemplate[]>(`/orgs/${orgId}/lab-templates`) });
  const [rows, setRows] = useState<LabTemplate[]>([]);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => { if (q.data) setRows(q.data); }, [q.data]);
  const save = useMutation({
    mutationFn: () => api<LabTemplate[]>(`/orgs/${orgId}/lab-templates`, { method: 'PUT', body: JSON.stringify(rows) }),
    onSuccess: (d) => { qc.setQueryData(['orgLabTemplates', orgId], d); setMsg({ ok: true, text: t('settings.saved') }); },
    onError: (e) => setMsg({ ok: false, text: t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic')) }),
  });
  const set = (i: number, p: Partial<LabTemplate>) => setRows(rows.map((x, j) => (j === i ? { ...x, ...p } : x)));
  const setLine = (i: number, k: number, p: Partial<LabLine>) => set(i, { lines: rows[i].lines.map((l, j) => (j === k ? { ...l, ...p } : l)) });
  const n = (v: string | number) => (v === '' ? null : Number(v));
  return (
    <Stack maw={1100}>
      <Text size="sm" c="dimmed">{t('labt.hint')}</Text>
      <Accordion variant="separated" multiple>
        {rows.map((x, i) => (
          <Accordion.Item key={x.id ?? `n${i}`} value={x.id ?? `n${i}`}>
            <Accordion.Control>
              <Group gap="xs">
                <Text fw={600} size="sm">{pick(x, 'name') || t('labt.new')}</Text>
                <Badge size="xs" variant="light" tt="none">{t(`labt.m.${x.material}`)}</Badge>
                <Text size="xs" c="dimmed">{x.acceptance === 'concrete' ? t('labt.concrete') : t('labt.params', { count: x.lines.length })}</Text>
                {!x.is_active && <Badge size="xs" color="gray">{t('labt.off')}</Badge>}
              </Group>
            </Accordion.Control>
            <Accordion.Panel>
              <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="xs">
                <TextInput size="xs" label={t('structure.nameAr')} value={x.name_ar} onChange={(e) => set(i, { name_ar: e.currentTarget.value })} />
                <TextInput size="xs" label={t('structure.nameEn')} dir="ltr" value={x.name_en} onChange={(e) => set(i, { name_en: e.currentTarget.value })} />
                <Select size="xs" label={t('labt.material')} allowDeselect={false} value={x.material}
                  data={MATERIALS.map((m) => ({ value: m, label: t(`labt.m.${m}`) }))} onChange={(v) => set(i, { material: v ?? 'OTH' })} />
                <TextInput size="xs" label={t('labt.standard')} dir="ltr" value={x.standard ?? ''} onChange={(e) => set(i, { standard: e.currentTarget.value || null })} />
                <Select size="xs" label={t('labt.acceptance')} allowDeselect={false} value={x.acceptance}
                  data={[{ value: 'all', label: t('labt.all') }, { value: 'concrete', label: t('labt.concrete') }]}
                  onChange={(v) => set(i, { acceptance: (v as LabTemplate['acceptance']) ?? 'all' })} />
                <TextInput size="xs" label={t('labt.samples')} description={t('labt.samplesHint')} dir="ltr" value={x.samples ?? ''}
                  onChange={(e) => set(i, { samples: e.currentTarget.value || null })} />
              </SimpleGrid>
              {x.acceptance === 'concrete' ? <Text size="sm" c="dimmed" mt="sm">{t('labt.concreteHint')}</Text> : (
                <Table mt="sm" withTableBorder verticalSpacing={2} horizontalSpacing={4} fz="sm">
                  <Table.Thead>
                    <Table.Tr><Table.Th w={110}>{t('lab.sample')}</Table.Th><Table.Th>{t('lab.parameter')}</Table.Th><Table.Th w={80}>{t('lab.unit')}</Table.Th>
                      <Table.Th w={120}>{t('labt.method')}</Table.Th><Table.Th w={100}>{t('labt.kind')}</Table.Th><Table.Th w={80}>{t('lab.min')}</Table.Th>
                      <Table.Th w={80}>{t('lab.max')}</Table.Th><Table.Th w={30} /></Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {x.lines.map((l, k) => (
                      <Table.Tr key={k}>
                        <Table.Td><TextInput size="xs" dir="ltr" value={l.sample ?? ''} onChange={(e) => setLine(i, k, { sample: e.currentTarget.value || null })} /></Table.Td>
                        <Table.Td><TextInput size="xs" dir="ltr" value={l.parameter} onChange={(e) => setLine(i, k, { parameter: e.currentTarget.value })} /></Table.Td>
                        <Table.Td><TextInput size="xs" dir="ltr" value={l.unit ?? ''} onChange={(e) => setLine(i, k, { unit: e.currentTarget.value || null })} /></Table.Td>
                        <Table.Td><TextInput size="xs" dir="ltr" value={l.method ?? ''} onChange={(e) => setLine(i, k, { method: e.currentTarget.value || null })} /></Table.Td>
                        <Table.Td><Select size="xs" allowDeselect={false} value={l.kind} data={[{ value: 'number', label: t('labt.number') }, { value: 'okng', label: 'OK / NOK' }]}
                          onChange={(v) => setLine(i, k, { kind: (v as LabLine['kind']) ?? 'number' })} /></Table.Td>
                        <Table.Td><NumberInput size="xs" hideControls disabled={l.kind === 'okng'} value={l.min ?? ''} onChange={(v) => setLine(i, k, { min: n(v) })} /></Table.Td>
                        <Table.Td><NumberInput size="xs" hideControls disabled={l.kind === 'okng'} value={l.max ?? ''} onChange={(v) => setLine(i, k, { max: n(v) })} /></Table.Td>
                        <Table.Td><ActionIcon size="sm" variant="subtle" color="red" aria-label="remove" onClick={() => set(i, { lines: x.lines.filter((_, j) => j !== k) })}>×</ActionIcon></Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
              <Group justify="space-between" mt="xs">
                {x.acceptance !== 'concrete' ? <Button size="compact-xs" variant="subtle" onClick={() => set(i, { lines: [...x.lines, blankLine()] })}>+ {t('lab.addLine')}</Button> : <span />}
                <Group gap="md">
                  <Switch size="xs" label={t('labt.active')} checked={x.is_active} onChange={(e) => set(i, { is_active: e.currentTarget.checked })} />
                  <Button size="compact-xs" variant="subtle" color="red" onClick={() => setRows(rows.filter((_, j) => j !== i))}>{t('labt.remove')}</Button>
                </Group>
              </Group>
            </Accordion.Panel>
          </Accordion.Item>
        ))}
      </Accordion>
      <Group>
        <Button size="xs" variant="light" onClick={() => setRows([...rows, { id: null, code: null, name_ar: '', name_en: '', material: 'OTH', standard: null,
          acceptance: 'all', samples: null, lines: [blankLine()], is_active: true }])}>+ {t('labt.add')}</Button>
      </Group>
      {msg && <Alert color={msg.ok ? 'green' : 'red'}>{msg.text}</Alert>}
      <Group><Button loading={save.isPending} onClick={() => save.mutate()}>{t('rec.save')}</Button></Group>
    </Stack>
  );
}
