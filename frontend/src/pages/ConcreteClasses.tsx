import { ActionIcon, Alert, Button, Card, Group, MultiSelect, NumberInput, Select, Stack, Table, Text, TextInput, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../api';
import { pick } from '../i18n';
import type { ConcreteClass } from '../lab';
import { useStructure } from './Structure';

/** The project's concrete grades and how their cube results are accepted (project specification / QMP). */
export default function ConcreteClasses({ projectId, editable }: { projectId: string; editable: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['concreteClasses', projectId], queryFn: () => api<ConcreteClass[]>(`/projects/${projectId}/concrete-classes`) });
  const structure = useStructure(projectId);
  const [rows, setRows] = useState<ConcreteClass[]>([]);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => { if (q.data) setRows(q.data); }, [q.data]);
  const save = useMutation({
    mutationFn: () => api<ConcreteClass[]>(`/projects/${projectId}/concrete-classes`, { method: 'PUT', body: JSON.stringify(rows) }),
    onSuccess: (d) => { qc.setQueryData(['concreteClasses', projectId], d); setMsg({ ok: true, text: t('settings.saved') }); },
    onError: (e) => setMsg({ ok: false, text: t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic')) }),
  });
  const set = (i: number, p: Partial<ConcreteClass>) => setRows(rows.map((x, j) => (j === i ? { ...x, ...p } : x)));
  const topics = (structure.data?.stages ?? []).flatMap((s) => (s.topics ?? []).filter((x) => x.id).map((x) => ({ value: x.id!, label: `${pick(s, 'name')} › ${pick(x, 'name')}` })));
  const n = (v: string | number) => (v === '' ? 0 : Number(v));
  return (
    <Card withBorder>
      <Title order={5}>{t('cc.title')}</Title>
      <Text size="sm" c="dimmed" mb="md">{t('cc.hint')}</Text>
      {rows.length === 0 && <Text size="sm" c="dimmed">{t('cc.none')}</Text>}
      {rows.length > 0 && (
        <Table withRowBorders={false} verticalSpacing={4} horizontalSpacing={4}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={90}>{t('cc.grade')}</Table.Th><Table.Th w={80}>{t('cc.fck')}</Table.Th><Table.Th w={80}>{t('cc.mean')}</Table.Th>
              <Table.Th w={150}>{t('cc.rule')}</Table.Th><Table.Th w={80}>{t('cc.margin')}</Table.Th>
              <Table.Th>{t('cc.topics')}</Table.Th>{editable && <Table.Th w={30} />}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((x, i) => (
              <Table.Tr key={x.id ?? `n${i}`}>
                <Table.Td><TextInput size="xs" dir="ltr" disabled={!editable} value={x.grade} onChange={(e) => set(i, { grade: e.currentTarget.value })} /></Table.Td>
                <Table.Td><NumberInput size="xs" hideControls disabled={!editable} value={x.fck} onChange={(v) => set(i, { fck: n(v) })} /></Table.Td>
                <Table.Td><NumberInput size="xs" hideControls disabled={!editable} value={x.mean_margin} onChange={(v) => set(i, { mean_margin: n(v) })} /></Table.Td>
                <Table.Td><Select size="xs" disabled={!editable} allowDeselect={false} value={x.individual_rule}
                  data={[{ value: 'minus', label: t('cc.minus') }, { value: 'percent', label: t('cc.percent') }]}
                  onChange={(v) => set(i, { individual_rule: (v as ConcreteClass['individual_rule']) ?? 'minus', individual_margin: v === 'percent' ? 90 : 4 })} /></Table.Td>
                <Table.Td><NumberInput size="xs" hideControls disabled={!editable} value={x.individual_margin} onChange={(v) => set(i, { individual_margin: n(v) })} /></Table.Td>
                <Table.Td><MultiSelect size="xs" disabled={!editable} searchable data={topics} value={x.topic_ids} placeholder={t('cc.topicsPh')}
                  onChange={(v) => set(i, { topic_ids: v })} /></Table.Td>
                {editable && <Table.Td><ActionIcon size="sm" variant="subtle" color="red" disabled={!!x.tests} aria-label="remove"
                  onClick={() => setRows(rows.filter((_, j) => j !== i))}>×</ActionIcon></Table.Td>}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      {rows.length > 0 && (
        <Stack gap={2} mt={4}>
          {rows.map((x, i) => (
            <Text key={i} size="xs" c="dimmed" dir="ltr" ta="start">
              {x.grade}: {t('cc.rule_text', { mean: (Number(x.fck) + Number(x.mean_margin)).toFixed(1),
                each: (x.individual_rule === 'percent' ? Number(x.fck) * Number(x.individual_margin) / 100 : Number(x.fck) - Number(x.individual_margin)).toFixed(1) })}
            </Text>
          ))}
        </Stack>
      )}
      {editable && (
        <Group mt="xs">
          <Button size="compact-xs" variant="subtle" onClick={() => setRows([...rows, { id: null, grade: '', name: null, aliases: null, specimen: 'cube', fck: 30,
            mean_margin: 0, individual_rule: 'minus', individual_margin: 4, elements: null, topic_ids: [], ref: null, is_active: true }])}>+ {t('cc.add')}</Button>
        </Group>
      )}
      {msg && <Alert mt="sm" color={msg.ok ? 'green' : 'red'}>{msg.text}</Alert>}
      {editable && <Button mt="md" variant="light" loading={save.isPending} onClick={() => save.mutate()}>{t('rec.save')}</Button>}
    </Card>
  );
}
