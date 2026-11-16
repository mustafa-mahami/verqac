import { ActionIcon, Alert, Button, Card, Group, Select, Stack, Switch, Text, TextInput, Title, Tooltip } from '@mantine/core';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError, type GroupT, type StageT, type Structure, type UnitT } from '../api';
import { pick } from '../i18n';
import { groupLabel, move, StagesEditor, unitLabel, useStructure } from './Structure';

const blankStage: StageT = { id: null, name_ar: '', name_en: '', scope: 'per_location', weight: 0, is_active: true, used: false, topics: [] };
const blankUnit = (): UnitT => ({ id: null, name_ar: '', name_en: '', is_active: true, used: false });

function UnitRow({ u, onChange, onMove, onRemove, first, last, editable }: {
  u: UnitT; onChange: (u: UnitT) => void; onMove: (d: number) => void; onRemove: () => void;
  first: boolean; last: boolean; editable: boolean;
}) {
  const { t } = useTranslation();
  return (
    <Group gap={6} wrap="nowrap" opacity={u.is_active ? 1 : 0.55}>
      <TextInput size="xs" flex={1} placeholder={t('structure.nameAr')} aria-label={t('structure.nameAr')} disabled={!editable}
        value={u.name_ar} onChange={(e) => onChange({ ...u, name_ar: e.currentTarget.value })} />
      <TextInput size="xs" flex={1} dir="ltr" placeholder={t('structure.nameEn')} aria-label={t('structure.nameEn')} disabled={!editable}
        value={u.name_en} onChange={(e) => onChange({ ...u, name_en: e.currentTarget.value })} />
      <Switch size="xs" checked={u.is_active} disabled={!editable} aria-label={t('settings.kindActive')}
        onChange={(e) => onChange({ ...u, is_active: e.currentTarget.checked })} />
      {editable && (
        <Group gap={2} wrap="nowrap">
          <ActionIcon size="sm" variant="subtle" color="gray" disabled={first} aria-label="up" onClick={() => onMove(-1)}>↑</ActionIcon>
          <ActionIcon size="sm" variant="subtle" color="gray" disabled={last} aria-label="down" onClick={() => onMove(1)}>↓</ActionIcon>
          <Tooltip label={t('structure.usedHint')} disabled={!u.used}>
            <ActionIcon size="sm" variant="subtle" color="red" disabled={u.used} aria-label="remove" onClick={onRemove}>×</ActionIcon>
          </Tooltip>
        </Group>
      )}
    </Group>
  );
}

/** Project settings: project type, weighted stages, buildings / zones and their floors / sections. */
export default function ProjectStructure({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useStructure(projectId);
  const [stages, setStages] = useState<StageT[]>([]);
  const [groups, setGroups] = useState<GroupT[]>([]);
  const [typeId, setTypeId] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string; at: string } | null>(null);
  useEffect(() => { if (q.data) { setStages(q.data.stages); setGroups(q.data.locations); } }, [q.data]);

  const err = (e: unknown) => t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic'));
  const done = (s: Structure) => { qc.setQueryData(['structure', projectId], s); qc.invalidateQueries({ queryKey: ['records', projectId] }); };
  const save = useMutation({
    mutationFn: ({ path, body }: { at: string; path: string; body: unknown }) =>
      api<Structure>(`/projects/${projectId}/${path}`, { method: path === 'apply-type' ? 'POST' : 'PUT', body: JSON.stringify(body) }),
    onSuccess: (s, v) => { done(s); setMsg({ ok: true, text: t('settings.saved'), at: v.at }); },
    onError: (e, v) => setMsg({ ok: false, text: err(e), at: v.at }),
  });
  const note = (at: string) => msg?.at === at && <Alert mt="sm" color={msg.ok ? 'green' : 'red'}>{msg.text}</Alert>;
  if (!q.data) return null;
  const s = q.data;
  const editable = s.can_edit;
  const setGroup = (i: number, g: GroupT) => setGroups(groups.map((x, j) => (j === i ? g : x)));
  const addGroup = () => {
    // a new building starts with the same floors as the first one (names only)
    const units = (groups[0]?.units ?? []).map((u) => ({ ...blankUnit(), name_ar: u.name_ar, name_en: u.name_en }));
    const n = groups.length + 1;
    setGroups([...groups, { ...blankUnit(), name_ar: `${s.labels.group_ar} ${n}`, name_en: `${s.labels.group_en} ${n}`, units }]);
  };

  return (
    <>
      {editable && !s.project_type && (
        <Card withBorder>
          <Title order={5}>{t('structure.typeTitle')}</Title>
          <Text size="sm" c="dimmed" mb="md">{t('structure.applyHint')}</Text>
          <Group align="flex-end">
            <Select w={260} label={t('structure.projectType')} value={typeId} onChange={setTypeId}
              data={s.types.map((x) => ({ value: x.id, label: pick(x, 'name') }))} />
            <Button disabled={!typeId} loading={save.isPending}
              onClick={() => save.mutate({ at: 'type', path: 'apply-type', body: { project_type_id: typeId } })}>{t('structure.apply')}</Button>
          </Group>
          {note('type')}
        </Card>
      )}

      <Card withBorder>
        <Group justify="space-between" align="flex-start">
          <div>
            <Title order={5}>{t('structure.stagesTitle')}</Title>
            <Text size="sm" c="dimmed" mb="md">{t('structure.stagesHint')}</Text>
          </div>
          {s.project_type && <Text size="sm" c="dimmed">{t('structure.projectType')}: {pick(s.project_type, 'name')}</Text>}
        </Group>
        <StagesEditor stages={stages} onChange={setStages} editable={editable} blank={blankStage} />
        {note('stages')}
        {editable && <Button mt="md" variant="light" loading={save.isPending}
          onClick={() => save.mutate({ at: 'stages', path: 'stages', body: stages })}>{t('rec.save')}</Button>}
      </Card>

      <Card withBorder>
        <Title order={5}>{t('structure.locationsTitle', { group: groupLabel(s), unit: unitLabel(s) })}</Title>
        <Text size="sm" c="dimmed" mb="md">{t('structure.locationsHint')}</Text>
        <Stack>
          {groups.map((g, i) => (
            <Card key={g.id ?? `new-${i}`} withBorder p="sm" bg="gray.0" opacity={g.is_active ? 1 : 0.6}>
              <Group gap={6} wrap="nowrap" mb="xs">
                <TextInput size="sm" fw={600} flex={1} aria-label={t('structure.nameAr')} disabled={!editable} value={g.name_ar}
                  onChange={(e) => setGroup(i, { ...g, name_ar: e.currentTarget.value })} />
                <TextInput size="sm" flex={1} dir="ltr" aria-label={t('structure.nameEn')} disabled={!editable} value={g.name_en}
                  onChange={(e) => setGroup(i, { ...g, name_en: e.currentTarget.value })} />
                <Switch size="xs" checked={g.is_active} disabled={!editable} aria-label={t('settings.kindActive')}
                  onChange={(e) => setGroup(i, { ...g, is_active: e.currentTarget.checked })} />
                {editable && (
                  <Tooltip label={t('structure.usedHint')} disabled={!g.used}>
                    <ActionIcon variant="subtle" color="red" disabled={g.used} aria-label="remove"
                      onClick={() => setGroups(groups.filter((_, j) => j !== i))}>×</ActionIcon>
                  </Tooltip>
                )}
              </Group>
              <Stack gap={4} ps="md">
                {g.units.map((u, j) => (
                  <UnitRow key={u.id ?? `n-${j}`} u={u} editable={editable} first={j === 0} last={j === g.units.length - 1}
                    onChange={(x) => setGroup(i, { ...g, units: g.units.map((y, k) => (k === j ? x : y)) })}
                    onMove={(d) => setGroup(i, { ...g, units: move(g.units, j, d) })}
                    onRemove={() => setGroup(i, { ...g, units: g.units.filter((_, k) => k !== j) })} />
                ))}
                {editable && (
                  <Group>
                    <Button size="compact-xs" variant="subtle" onClick={() => setGroup(i, { ...g, units: [...g.units, blankUnit()] })}>
                      + {t('structure.addUnit', { unit: unitLabel(s) })}
                    </Button>
                  </Group>
                )}
              </Stack>
            </Card>
          ))}
          {editable && (
            <Group><Button size="xs" variant="subtle" onClick={addGroup}>+ {t('structure.addGroup', { group: groupLabel(s) })}</Button></Group>
          )}
        </Stack>
        {note('locations')}
        {editable && <Button mt="md" variant="light" loading={save.isPending}
          onClick={() => save.mutate({ at: 'locations', path: 'locations', body: groups })}>{t('rec.save')}</Button>}
      </Card>
    </>
  );
}
