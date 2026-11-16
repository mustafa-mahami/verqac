import { ActionIcon, Alert, Badge, Button, Card, CopyButton, Group, Menu, Modal, SegmentedControl, Stack, Table, Text, TextInput, Title } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError, type InviteOut, type OrgMember, type PendingInvite } from '../api';
import { useAuth } from '../auth';
import i18n, { pick } from '../i18n';
import InviteLink from './InviteLink';

export default function OrgUsers() {
  const { t } = useTranslation();
  const { me } = useAuth();
  const qc = useQueryClient();
  const admin = (me?.orgs ?? []).find((m) => m.org_role === 'admin');
  const orgId = admin?.org.id ?? '';
  const [open, setOpen] = useState(false);
  const [invite, setInvite] = useState<InviteOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<OrgMember | null>(null);
  const members = useQuery({ queryKey: ['orgMembers', orgId], enabled: !!orgId, queryFn: () => api<OrgMember[]>(`/orgs/${orgId}/members`) });
  const pending = useQuery({ queryKey: ['orgInvites', orgId], enabled: !!orgId, queryFn: () => api<PendingInvite[]>(`/orgs/${orgId}/invitations`) });
  const form = useForm({ initialValues: { email: '', org_role: 'member' } });
  const send = useMutation({
    mutationFn: (v: typeof form.values) => api<InviteOut>(`/orgs/${orgId}/invitations`, { method: 'POST', body: JSON.stringify(v) }),
    onSuccess: (inv) => { setInvite(inv); form.reset(); qc.invalidateQueries({ queryKey: ['orgInvites', orgId] }); },
    onError: (e) => setError(t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic'))),
  });
  const patch = useMutation({
    mutationFn: ({ uid, body }: { uid: string; body: Record<string, unknown> }) =>
      api<OrgMember[]>(`/orgs/${orgId}/members/${uid}`, { method: 'PATCH', body: JSON.stringify(body) }),
    onSuccess: (rows) => { qc.setQueryData(['orgMembers', orgId], rows); setConfirm(null); },
    onError: (e) => setError(t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic'))),
  });
  const [reset, setReset] = useState<{ name: string; link: string; expires_at: string; emailed: boolean } | null>(null);
  const resetLink = useMutation({
    mutationFn: async (m: OrgMember) => ({
      name: pick(m.user, 'full_name'),
      ...(await api<{ link: string; expires_at: string; emailed: boolean }>(`/orgs/${orgId}/members/${m.user.id}/reset-link`, { method: 'POST' })),
    }),
    onSuccess: setReset,
    onError: (e) => setError(t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic'))),
  });
  if (!admin) return null;
  const close = () => { setOpen(false); setInvite(null); setError(null); };

  return (
    <Stack maw={1200} mx="auto">
      <Group justify="space-between">
        <div>
          <Title order={3}>{t('org.title')}</Title>
          <Text c="dimmed" size="sm">{pick(admin.org, 'name')}</Text>
        </div>
        <Button onClick={() => setOpen(true)}>{t('org.invite')}</Button>
      </Group>
      <Text size="sm" c="dimmed">{t('org.hint')}</Text>
      {error && !open && <Alert color="red" withCloseButton onClose={() => setError(null)}>{error}</Alert>}
      <Card withBorder p={0}>
        <Table.ScrollContainer minWidth={760}>
          <Table verticalSpacing="sm" horizontalSpacing="md">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('team.user')}</Table.Th>
                <Table.Th>{t('org.orgRole')}</Table.Th>
                <Table.Th>{t('org.status')}</Table.Th>
                <Table.Th>{t('org.projects')}</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {members.data?.map((m) => {
                const self = m.user.id === me?.user.id;
                return (
                  <Table.Tr key={m.user.id} opacity={m.is_active ? 1 : 0.55}>
                    <Table.Td>
                      <Text size="sm" fw={500}>{pick(m.user, 'full_name')}</Text>
                      <Text size="xs" c="dimmed" dir="ltr" ta="start">{m.user.email}</Text>
                    </Table.Td>
                    <Table.Td><Badge tt="none" variant="light" color={m.org_role === 'admin' ? 'verqac' : 'gray'}>{t(`org.${m.org_role}`)}</Badge></Table.Td>
                    <Table.Td><Badge tt="none" variant="dot" color={m.is_active ? 'green' : 'red'}>{m.is_active ? t('org.active') : t('org.suspended')}</Badge></Table.Td>
                    <Table.Td>
                      {m.projects.filter((x) => x.is_active).length === 0 ? <Text size="xs" c="dimmed">{t('org.noProjects')}</Text> : (
                        <Group gap={4}>
                          {m.projects.filter((x) => x.is_active).map((x) => (
                            <Badge key={x.project_id} tt="none" variant="outline" color="gray" title={pick(x, 'name')}>
                              <span dir="ltr">{x.code}</span> · {pick(x.role, 'name')}
                            </Badge>
                          ))}
                        </Group>
                      )}
                    </Table.Td>
                    <Table.Td>
                      {!self && (
                        <Menu position="bottom-end">
                          <Menu.Target><ActionIcon variant="subtle" aria-label="menu">⋮</ActionIcon></Menu.Target>
                          <Menu.Dropdown>
                            {m.is_active
                              ? <Menu.Item color="red" onClick={() => setConfirm(m)}>{t('org.suspend')}</Menu.Item>
                              : <Menu.Item onClick={() => patch.mutate({ uid: m.user.id, body: { is_active: true } })}>{t('org.activate')}</Menu.Item>}
                            <Menu.Item onClick={() => patch.mutate({ uid: m.user.id, body: { org_role: m.org_role === 'admin' ? 'member' : 'admin' } })}>
                              {m.org_role === 'admin' ? t('org.makeMember') : t('org.makeAdmin')}
                            </Menu.Item>
                            {m.is_active && <Menu.Item onClick={() => resetLink.mutate(m)}>{t('account.resetLink')}</Menu.Item>}
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
      <Modal opened={!!reset} onClose={() => setReset(null)} title={reset ? t('account.resetLinkTitle', { name: reset.name }) : ''}>
        {reset && (
          <Stack>
            <Text size="sm">
              {t('account.resetLinkHint', { date: new Date(reset.expires_at).toLocaleString(i18n.language === 'en' ? 'en-GB' : 'ar-PS-u-nu-latn') })}
              {reset.emailed && ` ${t('account.resetLinkEmailed')}`}
            </Text>
            <TextInput value={reset.link} readOnly dir="ltr" onFocus={(e) => e.currentTarget.select()} />
            <CopyButton value={reset.link}>
              {({ copied, copy }) => <Button color={copied ? 'teal' : undefined} onClick={copy}>{copied ? t('invite.copied') : t('invite.copy')}</Button>}
            </CopyButton>
          </Stack>
        )}
      </Modal>
      <Modal opened={!!confirm} onClose={() => setConfirm(null)} title={t('org.suspend')}>
        {confirm && (
          <Stack>
            <Text fw={500}>{pick(confirm.user, 'full_name')}</Text>
            <Text size="sm">{t('org.suspendConfirm')}</Text>
            <Group justify="flex-end">
              <Button variant="default" onClick={() => setConfirm(null)}>{t('common.cancel')}</Button>
              <Button color="red" loading={patch.isPending} onClick={() => patch.mutate({ uid: confirm.user.id, body: { is_active: false } })}>
                {t('org.suspend')}
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
      {!!pending.data?.length && (
        <>
          <Title order={5}>{t('org.pending')}</Title>
          {pending.data.map((p) => <Text key={p.email} size="sm" dir="ltr" ta="start">{p.email}</Text>)}
        </>
      )}
      <Modal opened={open} onClose={close} title={t('org.invite')}>
        {invite ? <InviteLink invite={invite} onDone={close} /> : (
          <form onSubmit={form.onSubmit((v) => send.mutate(v))}>
            <Stack>
              {error && <Alert color="red">{error}</Alert>}
              <TextInput label={t('auth.email')} type="email" dir="ltr" required {...form.getInputProps('email')} />
              <div>
                <Text size="sm" fw={500} mb={4}>{t('org.orgRole')}</Text>
                <SegmentedControl fullWidth {...form.getInputProps('org_role')}
                  data={[{ value: 'member', label: t('org.member') }, { value: 'admin', label: t('org.admin') }]} />
              </div>
              <Button type="submit" loading={send.isPending}>{t('org.invite')}</Button>
            </Stack>
          </form>
        )}
      </Modal>
    </Stack>
  );
}
