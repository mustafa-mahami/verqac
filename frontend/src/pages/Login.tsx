import { Alert, Anchor, Button, PasswordInput, Stack, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api, ApiError } from '../api';
import { useAuth } from '../auth';
import AuthLayout from './AuthLayout';

export default function Login() {
  const { t } = useTranslation();
  const { signIn } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const form = useForm({ initialValues: { email: '', password: '' } });

  const submit = form.onSubmit(async (values) => {
    setError(null);
    try {
      const r = await api<{ access_token: string }>('/auth/login', { method: 'POST', body: JSON.stringify(values) });
      await signIn(r.access_token);
      const next = params.get('next');
      navigate(next && next.startsWith('/') && !next.startsWith('//') ? next : '/inbox', { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.code : 'generic');
    }
  });

  return (
    <AuthLayout title={t('auth.login')}>
      <form onSubmit={submit}>
        <Stack>
          {error && <Alert color="red">{t(`errors.${error}`, t('errors.generic'))}</Alert>}
          <TextInput label={t('auth.email')} type="email" dir="ltr" required autoComplete="username" {...form.getInputProps('email')} />
          <PasswordInput label={t('auth.password')} dir="ltr" required autoComplete="current-password" {...form.getInputProps('password')} />
          <Button type="submit" loading={form.submitting}>{t('auth.login')}</Button>
          <Anchor component={Link} to="/forgot" size="sm">{t('account.forgot')}</Anchor>
          <Anchor component={Link} to="/register" size="sm">{t('auth.noAccount')}</Anchor>
        </Stack>
      </form>
    </AuthLayout>
  );
}
