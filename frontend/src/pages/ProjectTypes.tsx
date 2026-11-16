import { Accordion, ActionIcon, Alert, Badge, Button, Group, SimpleGrid, Stack, Switch, Text, TextInput, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError, type ProjectTypeT, type TemplateStage } from '../api';
import { pick } from '../i18n';
import { move, StagesEditor, weightTotal } from './Structure';

const blankStage: TemplateStage = { name_ar: '', name_en: '', scope: 'per_location', weight: 0 };

/** Organization settings: kinds of project and the stage / location templates new projects start from. */
export default function ProjectTypes({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['projectTypes', orgId], queryFn: () => api<ProjectTypeT[]>(`/orgs/${orgId}/project-types`) });
  const [types, setTypes] = useState<ProjectTypeT[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => { if (q.data) setTypes(q.data); }, [q.data]);
  const save = useMutation({
    mutationFn: () => api<ProjectTypeT[]>(`/orgs/${orgId}/project-types`, { method: 'PUT', body: JSON.stringify(types) }),
    onSuccess: (x) => { qc.setQueryData(['projectTypes', orgId], x); setMsg({ ok: true, text: t('settings.saved') }); },
    onError: (e) => setMsg({ ok: false, text: t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic')) }),
  });
  const set = (i: number, patch: Partial<ProjectTypeT>) => setTypes(types.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const add = () => {
    setTypes([...types, { id: null, name_ar: '', name_en: '', group_label_ar: 'منطقة', group_label_en: 'Zone',
      unit_label_ar: 'قسم', unit_label_en: 'Part', stages: [], units: [], is_active: true }]);
    setOpen(`i${types.length}`);
  };

  return (
    <Stack maw={1000}>
      <div>
        <Title order={4}>{t('structure.typesTitle')}</Title>
        <Text size="sm" c="dimmed">{t('structure.typesHint')}</Text>
      </div>
      <Accordion variant="separated" value={open} onChange={setOpen}>
        {types.map((x, i) => {
          const total = weightTotal(x.stages);
          return (
            <Accordion.Item key={x.id ?? `new-${i}`} value={`i${i}`} opacity={x.is_active ? 1 : 0.6}>
              <Accordion.Control>
                <Group justify="space-between" pe="md">
                  <Text fw={600}>{pick(x, 'name') || t('structure.newType')}</Text>
                  <Group gap="xs">
                    <Badge variant="light" tt="none" color="gray">{t('structure.stagesCount', { count: x.stages.length })}</Badge>
                    {x.stages.length > 0 && Math.abs(total - 100) >= 0.01 && <Badge color="red" tt="none" variant="light">{total}%</Badge>}
                  </Group>
                </Group>
              </Accordion.Control>
              <Accordion.Panel>
                <Stack>
                  <SimpleGrid cols={{ base: 1, sm: 2 }}>
                    <TextInput label={t('structure.nameAr')} value={x.name_ar} onChange={(e) => set(i, { name_ar: e.currentTarget.value })} />
                    <TextInput label={t('structure.nameEn')} dir="ltr" value={x.name_en} onChange={(e) => set(i, { name_en: e.currentTarget.value })} />
                  </SimpleGrid>
                  <SimpleGrid cols={{ base: 2, sm: 4 }}>
                    <TextInput label={t('structure.groupLabelAr')} description={t('structure.groupLabelHint')} value={x.group_label_ar}
                      onChange={(e) => set(i, { group_label_ar: e.currentTarget.value })} />
                    <TextInput label={t('structure.groupLabelEn')} description="Building / Zone" dir="ltr" value={x.group_label_en}
                      onChange={(e) => set(i, { group_label_en: e.currentTarget.value })} />
                    <TextInput label={t('structure.unitLabelAr')} description={t('structure.unitLabelHint')} value={x.unit_label_ar}
                      onChange={(e) => set(i, { unit_label_ar: e.currentTarget.value })} />
                    <TextInput label={t('structure.unitLabelEn')} description="Floor / Section" dir="ltr" value={x.unit_label_en}
                      onChange={(e) => set(i, { unit_label_en: e.currentTarget.value })} />
                  </SimpleGrid>
                  <Text fw={600} size="sm">{t('structure.templateStages')}</Text>
                  <StagesEditor stages={x.stages} onChange={(st) => set(i, { stages: st })} editable blank={blankStage} />
                  <Text fw={600} size="sm">{t('structure.templateUnits', { unit: pick({ l_ar: x.unit_label_ar, l_en: x.unit_label_en }, 'l') })}</Text>
                  <Stack gap={4}>
                    {x.units.map((u, j) => (
                      <Group key={j} gap={6} wrap="nowrap">
                        <TextInput size="xs" flex={1} aria-label={t('structure.nameAr')} value={u.name_ar}
                          onChange={(e) => set(i, { units: x.units.map((y, k) => (k === j ? { ...y, name_ar: e.currentTarget.value } : y)) })} />
                        <TextInput size="xs" flex={1} dir="ltr" aria-label={t('structure.nameEn')} value={u.name_en}
                          onChange={(e) => set(i, { units: x.units.map((y, k) => (k === j ? { ...y, name_en: e.currentTarget.value } : y)) })} />
                        <ActionIcon size="sm" variant="subtle" color="gray" disabled={j === 0} aria-label="up" onClick={() => set(i, { units: move(x.units, j, -1) })}>↑</ActionIcon>
                        <ActionIcon size="sm" variant="subtle" color="gray" disabled={j === x.units.length - 1} aria-label="down" onClick={() => set(i, { units: move(x.units, j, 1) })}>↓</ActionIcon>
                        <ActionIcon size="sm" variant="subtle" color="red" aria-label="remove" onClick={() => set(i, { units: x.units.filter((_, k) => k !== j) })}>×</ActionIcon>
                      </Group>
                    ))}
                    <Group>
                      <Button size="compact-xs" variant="subtle" onClick={() => set(i, { units: [...x.units, { name_ar: '', name_en: '' }] })}>
                        + {t('structure.addUnit', { unit: pick({ l_ar: x.unit_label_ar, l_en: x.unit_label_en }, 'l') })}
                      </Button>
                    </Group>
                  </Stack>
                  <Group justify="space-between">
                    <Switch label={t('settings.kindActive')} checked={x.is_active} onChange={(e) => set(i, { is_active: e.currentTarget.checked })} />
                    <Button size="xs" variant="subtle" color="red" onClick={() => setTypes(types.filter((_, j) => j !== i))}>{t('structure.deleteType')}</Button>
                  </Group>
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          );
        })}
      </Accordion>
      <Group><Button size="xs" variant="subtle" onClick={add}>+ {t('structure.addType')}</Button></Group>
      {msg && <Alert color={msg.ok ? 'green' : 'red'}>{msg.text}</Alert>}
      <Group><Button loading={save.isPending} onClick={() => save.mutate()}>{t('rec.save')}</Button></Group>
    </Stack>
  );
}
