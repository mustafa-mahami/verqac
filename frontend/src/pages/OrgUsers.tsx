import { Alert, Badge, Button, Card, Group, Modal, SegmentedControl, Stack, Table, Text, TextInput, Title } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError, type InviteOut, type OrgMember, type PendingInvite } from '../api';
import { useAuth } from '../auth';
import { pick } from '../i18n';
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
  const members = useQuery({ queryKey: ['orgMembers', orgId], enabled: !!orgId, queryFn: () => api<OrgMember[]>(`/orgs/${orgId}/members`) });
  const pending = useQuery({ queryKey: ['orgInvites', orgId], enabled: !!orgId, queryFn: () => api<PendingInvite[]>(`/orgs/${orgId}/invitations`) });
  const form = useForm({ initialValues: { email: '', org_role: 'member' } });
  const send = useMutation({
    mutationFn: (v: typeof form.values) => api<InviteOut>(`/orgs/${orgId}/invitations`, { method: 'POST', body: JSON.stringify(v) }),
    onSuccess: (inv) => { setInvite(inv); form.reset(); qc.invalidateQueries({ queryKey: ['orgInvites', orgId] }); },
    onError: (e) => setError(t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic'))),
  });
  if (!admin) return null;
  const close = () => { setOpen(false); setInvite(null); setError(null); };

  return (
    <Stack maw={900} mx="auto">
      <Group justify="space-between">
        <div>
          <Title order={3}>{t('org.title')}</Title>
          <Text c="dimmed" size="sm">{pick(admin.org, 'name')}</Text>
        </div>
        <Button onClick={() => setOpen(true)}>{t('org.invite')}</Button>
      </Group>
      <Text size="sm" c="dimmed">{t('org.hint')}</Text>
      <Card withBorder p={0}>
        <Table verticalSpacing="sm" horizontalSpacing="md">
          <Table.Tbody>
            {members.data?.map((m) => (
              <Table.Tr key={m.user.id}>
                <Table.Td>
                  <Text size="sm" fw={500}>{pick(m.user, 'full_name')}</Text>
                  <Text size="xs" c="dimmed" dir="ltr" ta="start">{m.user.email}</Text>
                </Table.Td>
                <Table.Td><Badge tt="none" variant="light" color={m.org_role === 'admin' ? 'verqac' : 'gray'}>{t(`org.${m.org_role}`)}</Badge></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>
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
