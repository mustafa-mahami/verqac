import { ActionIcon, Alert, Badge, Button, Card, Group, Select, Switch, Table, Tabs, Text, TextInput, Title, Tooltip } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError, type ProjectRole } from '../api';
import { pick } from '../i18n';
import { roleHint } from './ProjectTeam';

const KINDS = ['contractor', 'consultant', 'owner'] as const;

/** Team roles of the project: each party renames or hides its roles and adds its own on top of a role of the same party. */
export default function ProjectRoles({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['projectRoles', projectId], queryFn: () => api<ProjectRole[]>(`/projects/${projectId}/roles`) });
  const [err, setErr] = useState<string | null>(null);
  const [draft, setDraft] = useState({ name_ar: '', name_en: '', base_role_id: '' });
  const onError = (e: unknown) => setErr(t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic')));
  const refresh = () => { setErr(null); qc.invalidateQueries({ queryKey: ['projectRoles', projectId] }); qc.invalidateQueries({ queryKey: ['team', projectId] }); };
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<Pick<ProjectRole, 'name_ar' | 'name_en' | 'hidden'>> }) =>
      api(`/projects/${projectId}/roles/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    onSuccess: refresh, onError,
  });
  const add = useMutation({
    mutationFn: () => api(`/projects/${projectId}/roles`, { method: 'POST', body: JSON.stringify(draft) }),
    onSuccess: () => { setDraft({ name_ar: '', name_en: '', base_role_id: '' }); refresh(); }, onError,
  });
  const del = useMutation({ mutationFn: (id: string) => api(`/projects/${projectId}/roles/${id}`, { method: 'DELETE' }), onSuccess: refresh, onError });
  const roles = q.data ?? [];
  const byCode = Object.fromEntries(roles.map((r) => [r.code, r]));
  const mine = roles.find((r) => r.can_edit)?.party_kind ?? 'contractor';
  const kinds = KINDS.filter((k) => roles.some((r) => r.party_kind === k));
  const rename = (r: ProjectRole, f: 'name_ar' | 'name_en', v: string) => {
    v = v.trim();
    if (v && v !== r[f]) patch.mutate({ id: r.id, body: { [f]: v } });
  };
  return (
    <Card withBorder>
      <Title order={5}>{t('roles.title')}</Title>
      <Text size="sm" c="dimmed" mb="md">{t('roles.hint')}</Text>
      {err && <Alert color="red" mb="sm" withCloseButton onClose={() => setErr(null)}>{err}</Alert>}
      <Tabs defaultValue={mine} key={mine}>
        <Tabs.List>{kinds.map((k) => <Tabs.Tab key={k} value={k}>{t(`party.${k}`)}</Tabs.Tab>)}</Tabs.List>
        {kinds.map((k) => {
          const list = roles.filter((r) => r.party_kind === k);
          const editable = list.some((r) => r.can_edit);
          const bases = list.filter((r) => !r.custom);
          return (
            <Tabs.Panel key={k} value={k} pt="sm">
              <Table verticalSpacing={4} horizontalSpacing={6}>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th w={170}>{t('roles.nameAr')}</Table.Th><Table.Th w={170}>{t('roles.nameEn')}</Table.Th>
                    <Table.Th>{t('roles.perms')}</Table.Th><Table.Th w={60}>{t('roles.members')}</Table.Th>
                    <Table.Th w={70}>{t('roles.hidden')}</Table.Th>{editable && <Table.Th w={30} />}
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {list.map((r) => (
                    <Table.Tr key={r.id} opacity={r.hidden ? 0.55 : 1}>
                      <Table.Td><TextInput size="xs" key={`${r.id}a${r.name_ar}`} defaultValue={r.name_ar} disabled={!r.can_edit}
                        onBlur={(e) => rename(r, 'name_ar', e.currentTarget.value)} /></Table.Td>
                      <Table.Td><TextInput size="xs" dir="ltr" key={`${r.id}e${r.name_en}`} defaultValue={r.name_en} disabled={!r.can_edit}
                        onBlur={(e) => rename(r, 'name_en', e.currentTarget.value)} /></Table.Td>
                      <Table.Td>
                        {r.custom && r.base_code && byCode[r.base_code] &&
                          <Badge size="xs" variant="light" tt="none" me={6}>{t('roles.like', { name: pick(byCode[r.base_code], 'name') })}</Badge>}
                        <Text span size="xs" c="dimmed">{roleHint(r.base_code ?? r.code)}</Text>
                      </Table.Td>
                      <Table.Td><Text size="sm" ta="center">{r.members}</Text></Table.Td>
                      <Table.Td><Switch size="xs" checked={r.hidden} disabled={!r.can_edit}
                        onChange={(e) => patch.mutate({ id: r.id, body: { hidden: e.currentTarget.checked } })} /></Table.Td>
                      {editable && <Table.Td>{r.custom && (
                        <Tooltip label={r.members ? t('errors.role_in_use') : t('roles.delete')}>
                          <ActionIcon size="sm" variant="subtle" color="red" disabled={!r.can_edit || r.members > 0} aria-label="delete"
                            onClick={() => del.mutate(r.id)}>×</ActionIcon>
                        </Tooltip>)}</Table.Td>}
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
              {editable && (
                <Group mt="sm" align="end" gap="xs">
                  <TextInput size="xs" w={170} label={t('roles.nameAr')} value={draft.name_ar} onChange={(e) => setDraft({ ...draft, name_ar: e.currentTarget.value })} />
                  <TextInput size="xs" w={170} dir="ltr" label={t('roles.nameEn')} value={draft.name_en} onChange={(e) => setDraft({ ...draft, name_en: e.currentTarget.value })} />
                  <Select size="xs" w={220} label={t('roles.base')} value={draft.base_role_id || null} allowDeselect={false}
                    data={bases.map((b) => ({ value: b.id, label: pick(b, 'name') }))}
                    onChange={(v) => setDraft({ ...draft, base_role_id: v ?? '' })} />
                  <Button size="xs" loading={add.isPending} disabled={!draft.name_ar.trim() || !draft.name_en.trim() || !draft.base_role_id}
                    onClick={() => add.mutate()}>{t('roles.add')}</Button>
                </Group>
              )}
              {editable && draft.base_role_id && <Text size="xs" c="dimmed" mt={4}>{roleHint(roles.find((b) => b.id === draft.base_role_id)?.code ?? '')}</Text>}
            </Tabs.Panel>
          );
        })}
      </Tabs>
    </Card>
  );
}
