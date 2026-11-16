import {
  ActionIcon, Alert, Badge, Button, Card, Group, Menu, Modal, MultiSelect, Select, SimpleGrid, Stack, Table,
  Text, TextInput, Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import {
  api, ApiError, type Discipline, type InviteOut, type Member, type OrgMember, type Role, type Team, type TeamParty,
} from '../api';
import { useAuth } from '../auth';
import i18n, { pick } from '../i18n';
import InviteLink from './InviteLink';


const errText = (_t: unknown, e: unknown) =>
  i18n.t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, { defaultValue: i18n.t('errors.generic') });

type Dialog =
  | { kind: 'addParty' }
  | { kind: 'inviteParty'; party: TeamParty }
  | { kind: 'link'; invite: InviteOut }
  | { kind: 'addMember'; party: TeamParty }
  | { kind: 'inviteNew'; party: TeamParty }
  | { kind: 'editMember'; member: Member; party: TeamParty }
  | null;

function PartyForm({ projectId, party, kinds = [], onInvite }: {
  projectId: string; party?: TeamParty; kinds?: string[]; onInvite: (i: InviteOut | null) => void;
}) {
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: { kind: kinds[0] ?? 'consultant', placeholder_name: '', email: '' } });
  const save = useMutation({
    mutationFn: (v: typeof form.values) =>
      party
        ? api<InviteOut>(`/projects/${projectId}/parties/${party.id}/invite`, { method: 'POST', body: JSON.stringify({ email: v.email }) })
        : api<InviteOut | null>(`/projects/${projectId}/parties`, {
            method: 'POST', body: JSON.stringify({ ...v, email: v.email || null }),
          }),
    onSuccess: onInvite,
    onError: (e) => setError(errText(t, e)),
  });
  return (
    <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
      <Stack>
        {error && <Alert color="red">{error}</Alert>}
        {!party && (
          <>
            <Select label={t('team.partyKind')} data={kinds.map((k) => ({ value: k, label: t(`party.${k}`) }))}
              allowDeselect={false} {...form.getInputProps('kind')} />
            <TextInput label={t('team.partyName')} required {...form.getInputProps('placeholder_name')} />
          </>
        )}
        <TextInput label={t('team.inviteEmail')} description={t('team.inviteEmailHint')} type="email" dir="ltr"
          required={!!party} {...form.getInputProps('email')} />
        <Button type="submit" loading={save.isPending}>{party ? t('team.invite') : t('team.addParty')}</Button>
      </Stack>
    </form>
  );
}

function MemberForm({ projectId, party, team, onDone }: { projectId: string; party: TeamParty; team: Team; onDone: () => void }) {
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);
  const orgId = party.org!.id;
  const users = useQuery({ queryKey: ['orgMembers', orgId], queryFn: () => api<OrgMember[]>(`/orgs/${orgId}/members`) });
  const roles = useQuery({ queryKey: ['roles'], queryFn: () => api<Role[]>('/roles') });
  const discs = useQuery({ queryKey: ['disciplines', orgId], queryFn: () => api<Discipline[]>(`/orgs/${orgId}/disciplines`) });
  const activeIds = new Set(team.members.filter((m) => m.is_active).map((m) => m.user.id));
  const candidates = (users.data ?? []).filter((m) => !activeIds.has(m.user.id));
  const form = useForm({ initialValues: { user_id: '', role_id: '', discipline_ids: [] as string[] } });
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: (v: typeof form.values) =>
      api(`/projects/${projectId}/members`, { method: 'POST', body: JSON.stringify({ ...v, party_id: party.id }) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['team', projectId] }); onDone(); },
    onError: (e) => setError(errText(t, e)),
  });
  if (users.isSuccess && candidates.length === 0) return <Alert>{t('team.noUsersToAdd')}</Alert>;
  return (
    <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
      <Stack>
        {error && <Alert color="red">{error}</Alert>}
        <Select label={t('team.user')} required searchable
          data={candidates.map((m) => ({ value: m.user.id, label: `${pick(m.user, 'full_name')} · ${m.user.email}` }))}
          {...form.getInputProps('user_id')} />
        <Select label={t('team.role')} required
          data={(roles.data ?? []).filter((r) => r.party_kind === party.kind).map((r) => ({ value: r.id, label: pick(r, 'name') }))}
          {...form.getInputProps('role_id')} />
        <MultiSelect label={t('team.disciplines')} placeholder={t('team.allDisciplines')}
          data={(discs.data ?? []).map((d) => ({ value: d.id, label: pick(d, 'name') }))}
          {...form.getInputProps('discipline_ids')} />
        <Button type="submit" loading={save.isPending}>{t('team.addMember')}</Button>
      </Stack>
    </form>
  );
}

/** Role and discipline pickers for one party (roles of that party, disciplines of its organization). */
function useRolesAndDisciplines(party: TeamParty) {
  const orgId = party.org!.id;
  const roles = useQuery({ queryKey: ['roles'], queryFn: () => api<Role[]>('/roles') });
  const discs = useQuery({ queryKey: ['disciplines', orgId], queryFn: () => api<Discipline[]>(`/orgs/${orgId}/disciplines`) });
  return {
    roleData: (roles.data ?? []).filter((r) => r.party_kind === party.kind).map((r) => ({ value: r.id, label: pick(r, 'name') })),
    discData: (discs.data ?? []).map((d) => ({ value: d.id, label: pick(d, 'name') })),
  };
}

function MemberEditForm({ projectId, member, party, onDone }: { projectId: string; member: Member; party: TeamParty; onDone: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const { roleData, discData } = useRolesAndDisciplines(party);
  const form = useForm({ initialValues: { role_id: member.role.id, discipline_ids: member.discipline_ids } });
  const save = useMutation({
    mutationFn: (v: typeof form.values) => api(`/projects/${projectId}/members/${member.id}`, { method: 'PATCH', body: JSON.stringify(v) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['team', projectId] }); onDone(); },
    onError: (e) => setError(errText(t, e)),
  });
  return (
    <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
      <Stack>
        {error && <Alert color="red">{error}</Alert>}
        <Text fw={500}>{pick(member.user, 'full_name')}</Text>
        <Select label={t('team.role')} required data={roleData} allowDeselect={false} {...form.getInputProps('role_id')} />
        <MultiSelect label={t('team.disciplines')} placeholder={t('team.allDisciplines')} data={discData} {...form.getInputProps('discipline_ids')} />
        <Button type="submit" loading={save.isPending}>{t('rec.save')}</Button>
      </Stack>
    </form>
  );
}

function InviteNewForm({ projectId, party, onInvite }: { projectId: string; party: TeamParty; onInvite: (i: InviteOut) => void }) {
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);
  const { roleData, discData } = useRolesAndDisciplines(party);
  const form = useForm({ initialValues: { email: '', role_id: '', discipline_ids: [] as string[] } });
  const send = useMutation({
    mutationFn: (v: typeof form.values) =>
      api<InviteOut>(`/projects/${projectId}/parties/${party.id}/invite-member`, { method: 'POST', body: JSON.stringify(v) }),
    onSuccess: onInvite, onError: (e) => setError(errText(t, e)),
  });
  return (
    <form onSubmit={form.onSubmit((v) => send.mutate(v))}>
      <Stack>
        <Text size="sm" c="dimmed">{t('team.inviteNewHint')}</Text>
        {error && <Alert color="red">{error}</Alert>}
        <TextInput label={t('auth.email')} type="email" dir="ltr" required {...form.getInputProps('email')} />
        <Select label={t('team.role')} required data={roleData} {...form.getInputProps('role_id')} />
        <MultiSelect label={t('team.disciplines')} placeholder={t('team.allDisciplines')} data={discData} {...form.getInputProps('discipline_ids')} />
        <Button type="submit" loading={send.isPending}>{t('team.invite')}</Button>
      </Stack>
    </form>
  );
}

export default function ProjectTeam() {
  const { t } = useTranslation();
  const { id = '' } = useParams();
  const { me } = useAuth();
  const qc = useQueryClient();
  const [dialog, setDialog] = useState<Dialog>(null);
  const [error, setError] = useState<string | null>(null);
  const team = useQuery({ queryKey: ['team', id], queryFn: () => api<Team>(`/projects/${id}/team`) });
  const discs = useQuery({
    queryKey: ['allDisciplines', id, team.data?.parties.map((p) => p.org?.id).join()],
    enabled: !!team.data,
    queryFn: async () => {
      const orgIds = [...new Set(team.data!.parties.flatMap((p) => (p.org ? [p.org.id] : [])))];
      const lists = await Promise.all(orgIds.map((o) => api<Discipline[]>(`/orgs/${o}/disciplines`).catch(() => [])));
      return new Map(lists.flat().map((d) => [d.id, d]));
    },
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ['team', id] });
  const removeParty = useMutation({
    mutationFn: (p: TeamParty) => api(`/projects/${id}/parties/${p.id}`, { method: 'DELETE' }),
    onSuccess: refresh, onError: (e) => setError(errText(t, e)),
  });
  const toggleMember = useMutation({
    mutationFn: ({ mid, active }: { mid: string; active: boolean }) =>
      api(`/projects/${id}/members/${mid}`, { method: 'PATCH', body: JSON.stringify({ is_active: active }) }),
    onSuccess: refresh, onError: (e) => setError(errText(t, e)),
  });

  if (!team.data) return null;
  const data = team.data;
  const missingKinds = ['consultant', 'owner'].filter((k) => !data.parties.some((p) => p.kind === k));
  const close = () => setDialog(null);
  const afterInvite = (inv: InviteOut | null) => { refresh(); setDialog(inv ? { kind: 'link', invite: inv } : null); };

  return (
    <Stack>
      {error && <Alert color="red" withCloseButton onClose={() => setError(null)}>{error}</Alert>}

      <Group justify="space-between">
        <Title order={4}>{t('team.parties')}</Title>
        {data.can_manage_project && missingKinds.length > 0 && (
          <Button variant="light" onClick={() => setDialog({ kind: 'addParty' })}>{t('team.addParty')}</Button>
        )}
      </Group>
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        {data.parties.map((p) => (
          <Card key={p.id} withBorder>
            <Group justify="space-between" wrap="nowrap" align="flex-start">
              <div>
                <Text size="sm" c="dimmed">{t(`party.${p.kind}`)}</Text>
                <Text fw={600}>{p.org ? pick(p.org, 'name') : p.placeholder_name}</Text>
              </div>
              <Badge tt="none" variant="light" color={p.status === 'active' ? 'green' : 'gray'} style={{ flexShrink: 0 }}>
                {t(`partyStatus.${p.status}`)}
              </Badge>
            </Group>
            {p.pending_invite && <Text size="xs" c="dimmed" mt="xs">{t('team.pendingTo', { email: p.pending_invite.email })}</Text>}
            <Group gap="xs" mt="sm">
              {data.can_manage_project && p.status === 'invited' && (
                <>
                  <Button size="compact-sm" onClick={() => setDialog({ kind: 'inviteParty', party: p })}>
                    {p.pending_invite ? t('team.reinvite') : t('team.invite')}
                  </Button>
                  <Button size="compact-sm" variant="subtle" color="red" onClick={() => removeParty.mutate(p)}>{t('team.remove')}</Button>
                </>
              )}
              {p.can_manage_team && (
                <>
                  <Button size="compact-sm" variant="light" onClick={() => setDialog({ kind: 'addMember', party: p })}>
                    {t('team.addMember')}
                  </Button>
                  <Button size="compact-sm" variant="subtle" onClick={() => setDialog({ kind: 'inviteNew', party: p })}>
                    {t('team.inviteNew')}
                  </Button>
                </>
              )}
            </Group>
          </Card>
        ))}
      </SimpleGrid>

      <Title order={4} mt="md">{t('team.members')}</Title>
      <Card withBorder p={0}>
        <Table.ScrollContainer minWidth={640}>
          <Table verticalSpacing="sm" horizontalSpacing="md">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('team.user')}</Table.Th>
                <Table.Th>{t('team.partyKind')}</Table.Th>
                <Table.Th>{t('team.role')}</Table.Th>
                <Table.Th>{t('team.disciplines')}</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.members.map((m) => {
                const party = data.parties.find((p) => p.id === m.party_id);
                const self = m.user.id === me?.user.id;
                return (
                  <Table.Tr key={m.id} opacity={m.is_active ? 1 : 0.5}>
                    <Table.Td>
                      <Text size="sm" fw={500}>{pick(m.user, 'full_name')} {self && <Badge size="xs" tt="none" variant="outline">{t('team.you')}</Badge>}</Text>
                      <Text size="xs" c="dimmed" dir="ltr" ta="start">{m.user.email}</Text>
                    </Table.Td>
                    <Table.Td><Text size="sm">{party ? t(`party.${party.kind}`) : ''}</Text></Table.Td>
                    <Table.Td><Text size="sm">{pick(m.role, 'name')}</Text></Table.Td>
                    <Table.Td>
                      <Text size="sm">
                        {m.discipline_ids.length === 0
                          ? t('team.allDisciplines')
                          : m.discipline_ids.map((d) => (discs.data?.get(d) ? pick(discs.data.get(d)!, 'name') : '…')).join('، ')}
                      </Text>
                      {!m.is_active && <Badge size="xs" color="gray" tt="none">{t('team.inactive')}</Badge>}
                    </Table.Td>
                    <Table.Td>
                      {party?.can_manage_team && !self && (
                        <Menu position="bottom-end">
                          <Menu.Target><ActionIcon variant="subtle" aria-label="menu">⋮</ActionIcon></Menu.Target>
                          <Menu.Dropdown>
                            {m.is_active && party && (
                              <Menu.Item onClick={() => setDialog({ kind: 'editMember', member: m, party })}>{t('team.edit')}</Menu.Item>
                            )}
                            <Menu.Item onClick={() => toggleMember.mutate({ mid: m.id, active: !m.is_active })}>
                              {m.is_active ? t('team.deactivate') : t('team.activate')}
                            </Menu.Item>
                          </Menu.Dropdown>
                        </Menu>
                      )}
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>

      <Modal opened={dialog !== null} onClose={close} title={
        dialog?.kind === 'link' ? t('invite.linkTitle')
          : dialog?.kind === 'addMember' ? t('team.addMember')
          : dialog?.kind === 'inviteNew' ? t('team.inviteNew')
          : dialog?.kind === 'editMember' ? t('team.edit')
          : dialog?.kind === 'inviteParty' ? `${t('team.invite')}: ${dialog.party.placeholder_name ?? ''}`
          : t('team.addParty')}>
        {dialog?.kind === 'addParty' && <PartyForm projectId={id} kinds={missingKinds} onInvite={afterInvite} />}
        {dialog?.kind === 'inviteParty' && <PartyForm projectId={id} party={dialog.party} onInvite={afterInvite} />}
        {dialog?.kind === 'link' && <InviteLink invite={dialog.invite} onDone={close} />}
        {dialog?.kind === 'addMember' && <MemberForm projectId={id} party={dialog.party} team={data} onDone={close} />}
        {dialog?.kind === 'inviteNew' && <InviteNewForm projectId={id} party={dialog.party} onInvite={(inv) => setDialog({ kind: 'link', invite: inv })} />}
        {dialog?.kind === 'editMember' && <MemberEditForm projectId={id} member={dialog.member} party={dialog.party} onDone={close} />}
      </Modal>
    </Stack>
  );
}
