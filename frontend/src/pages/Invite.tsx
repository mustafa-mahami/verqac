import { Alert, Button, PasswordInput, SegmentedControl, SimpleGrid, Stack, Text, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { api, ApiError, type InvitationInfo, type Org } from '../api';
import { useAuth } from '../auth';
import { pick } from '../i18n';
import AuthLayout from './AuthLayout';

export default function Invite() {
  const { t, i18n } = useTranslation();
  const { token = '' } = useParams();
  const { me, signIn, signOut } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const info = useQuery({ queryKey: ['invite', token], queryFn: () => api<InvitationInfo>(`/invitations/${token}`), retry: false });
  const myOrgs = useQuery({
    queryKey: ['inviteOrgs', token, me?.user.id], enabled: !!me,
    queryFn: () => api<Org[]>(`/invitations/${token}/my-orgs`),
  });
  const form = useForm({
    initialValues: { full_name_ar: '', full_name_en: '', password: '', org_choice: 'new', org_name_ar: '', org_name_en: '' },
  });

  const inv = info.data;
  if (info.isError) return <AuthLayout title={t('invite.title')}><Alert color="red">{t('invite.expired')}</Alert></AuthLayout>;
  if (!inv) return null;

  const signedInAs = me?.user.email.toLowerCase();
  const wrongUser = !!signedInAs && signedInAs !== inv.email;
  const needsLogin = !me && inv.user_exists;
  const isParty = inv.kind === 'project_party';
  const orgs = myOrgs.data ?? [];

  const submit = form.onSubmit(async (v) => {
    setError(null);
    const body: Record<string, unknown> = { locale: i18n.language === 'en' ? 'en' : 'ar' };
    if (!me) Object.assign(body, { full_name_ar: v.full_name_ar, full_name_en: v.full_name_en, password: v.password });
    if (isParty) {
      if (v.org_choice !== 'new') body.org_id = v.org_choice;
      else Object.assign(body, { org_name_ar: v.org_name_ar || inv.party_placeholder, org_name_en: v.org_name_en });
    }
    try {
      const r = await api<{ access_token: string }>(`/invitations/${token}/accept`, { method: 'POST', body: JSON.stringify(body) });
      await signIn(r.access_token);
      navigate(inv.project ? `/projects/${inv.project.id}` : '/inbox', { replace: true });
    } catch (e) {
      setError(t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic')));
    }
  });

  const inviter = pick({ name_ar: inv.inviter_name_ar, name_en: inv.inviter_name_en }, 'name');
  return (
    <AuthLayout title={t('invite.title')} width={560}>
      <Stack>
        <Text>
          {isParty
            ? t('invite.toProject', { inviter, project: inv.project ? pick(inv.project, 'name') : '', party: t(`party.${inv.party_kind}`) })
            : t('invite.toOrg', { inviter, org: inv.org ? pick(inv.org, 'name') : '' })}
        </Text>
        {inv.role && <Text size="sm" c="dimmed">{t('invite.yourRole', { role: pick(inv.role, 'name') })}</Text>}
        <Text size="sm" c="dimmed" dir="ltr" ta="start">{inv.email}</Text>

        {inv.status !== 'valid' ? <Alert color="red">{t(`invite.${inv.status}`)}</Alert>
          : wrongUser ? (
            <Alert color="yellow">
              {t('invite.otherEmail', { email: signedInAs, invited: inv.email })}
              <Button mt="sm" size="compact-sm" variant="light" onClick={signOut}>{t('auth.logout')}</Button>
            </Alert>
          ) : needsLogin ? (
            <Alert color="yellow">
              {t('invite.loginFirst')}
              <Button mt="sm" size="compact-sm" variant="light" onClick={() => navigate(`/login?next=/invite/${token}`)}>{t('auth.login')}</Button>
            </Alert>
          ) : (
            <form onSubmit={submit}>
              <Stack>
                {error && <Alert color="red">{error}</Alert>}
                {!me && (
                  <>
                    <SimpleGrid cols={{ base: 1, sm: 2 }}>
                      <TextInput label={t('auth.fullNameAr')} dir="rtl" required {...form.getInputProps('full_name_ar')} />
                      <TextInput label={t('auth.fullNameEn')} dir="ltr" required {...form.getInputProps('full_name_en')} />
                    </SimpleGrid>
                    <PasswordInput label={t('auth.password')} description={t('auth.passwordHint')} dir="ltr" required minLength={10}
                      autoComplete="new-password" {...form.getInputProps('password')} />
                  </>
                )}
                {isParty && (
                  <>
                    {orgs.length > 0 && (
                      <div>
                        <Text size="sm" fw={500} mb={4}>{t('invite.joinWith')}</Text>
                        <SegmentedControl fullWidth {...form.getInputProps('org_choice')}
                          data={[...orgs.map((o) => ({ value: o.id, label: pick(o, 'name') })), { value: 'new', label: t('invite.newOrg') }]} />
                      </div>
                    )}
                    {form.values.org_choice === 'new' && (
                      <SimpleGrid cols={{ base: 1, sm: 2 }}>
                        <TextInput label={t('invite.orgNameAr')} dir="rtl" placeholder={inv.party_placeholder ?? ''} {...form.getInputProps('org_name_ar')} />
                        <TextInput label={t('invite.orgNameEn')} dir="ltr" required {...form.getInputProps('org_name_en')} />
                      </SimpleGrid>
                    )}
                  </>
                )}
                <Button type="submit" loading={form.submitting}>{t('invite.accept')}</Button>
              </Stack>
            </form>
          )}
      </Stack>
    </AuthLayout>
  );
}
