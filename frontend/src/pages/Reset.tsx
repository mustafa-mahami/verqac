import { Alert, Anchor, Button, PasswordInput, Stack, Text } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';
import { api, ApiError } from '../api';
import { useAuth } from '../auth';
import AuthLayout from './AuthLayout';

/** Opened from a reset link (e-mailed, or sent by an org admin). */
export default function Reset() {
  const { t } = useTranslation();
  const { token = '' } = useParams();
  const { me, signOut } = useAuth();
  const info = useQuery({ queryKey: ['reset', token], queryFn: () => api<{ email: string }>(`/auth/reset/${token}`), retry: false });
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (pw !== pw2) return setError(t('account.mismatch'));
    try {
      await api(`/auth/reset/${token}`, { method: 'POST', body: JSON.stringify({ password: pw }) });
      setDone(true);
      if (me) await signOut();
    } catch (err) {
      setError(t(`errors.${err instanceof ApiError ? err.code : 'generic'}`, t('errors.generic')));
    }
  };
  if (info.isError) return <AuthLayout title={t('account.resetTitle')}><Alert color="red">{t('account.resetExpired')}</Alert></AuthLayout>;
  if (!info.data) return null;
  return (
    <AuthLayout title={t('account.resetTitle')}>
      {done ? (
        <Stack>
          <Alert color="green">{t('account.resetDone')}</Alert>
          <Anchor component={Link} to="/">{t('auth.login')}</Anchor>
        </Stack>
      ) : (
        <form onSubmit={submit}>
          <Stack>
            <Text size="sm">{t('account.resetFor')} <Text span fw={600} dir="ltr">{info.data.email}</Text></Text>
            {error && <Alert color="red">{error}</Alert>}
            <PasswordInput label={t('account.newPassword')} description={t('account.passwordHint')} dir="ltr" required minLength={10}
              value={pw} onChange={(e) => setPw(e.currentTarget.value)} autoComplete="new-password" />
            <PasswordInput label={t('account.confirmPassword')} dir="ltr" required value={pw2} onChange={(e) => setPw2(e.currentTarget.value)}
              autoComplete="new-password" />
            <Button type="submit">{t('account.savePassword')}</Button>
          </Stack>
        </form>
      )}
    </AuthLayout>
  );
}
