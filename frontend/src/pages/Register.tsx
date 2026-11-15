import { Alert, Anchor, Button, PasswordInput, SegmentedControl, SimpleGrid, Stack, Text, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { api, ApiError } from '../api';
import { useAuth } from '../auth';
import AuthLayout from './AuthLayout';

export default function Register() {
  const { t, i18n } = useTranslation();
  const { signIn } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: {
      org_kind: 'contractor', org_name_ar: '', org_name_en: '', full_name_ar: '', full_name_en: '', email: '', password: '',
    },
    validate: { password: (v) => (v.length >= 10 ? null : t('auth.passwordHint')) },
  });

  const submit = form.onSubmit(async (values) => {
    setError(null);
    try {
      const r = await api<{ access_token: string }>('/auth/register-org', {
        method: 'POST',
        body: JSON.stringify({ ...values, locale: i18n.language === 'en' ? 'en' : 'ar' }),
      });
      await signIn(r.access_token);
    } catch (e) {
      setError(e instanceof ApiError ? e.code : 'generic');
    }
  });

  return (
    <AuthLayout title={t('auth.register')} width={560}>
      <form onSubmit={submit}>
        <Stack>
          <Text size="sm" c="dimmed">{t('auth.registerHint')}</Text>
          {error && <Alert color="red">{t(`errors.${error}`, t('errors.generic'))}</Alert>}
          <div>
            <Text size="sm" fw={500} mb={4}>{t('auth.orgKind')}</Text>
            <SegmentedControl fullWidth {...form.getInputProps('org_kind')}
              data={['contractor', 'consultant', 'owner'].map((k) => ({ value: k, label: t(`orgKind.${k}`) }))} />
          </div>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput label={t('auth.orgNameAr')} dir="rtl" required {...form.getInputProps('org_name_ar')} />
            <TextInput label={t('auth.orgNameEn')} dir="ltr" required {...form.getInputProps('org_name_en')} />
            <TextInput label={t('auth.fullNameAr')} dir="rtl" required {...form.getInputProps('full_name_ar')} />
            <TextInput label={t('auth.fullNameEn')} dir="ltr" required {...form.getInputProps('full_name_en')} />
          </SimpleGrid>
          <TextInput label={t('auth.email')} type="email" dir="ltr" required autoComplete="username" {...form.getInputProps('email')} />
          <PasswordInput label={t('auth.password')} description={t('auth.passwordHint')} dir="ltr" required
            autoComplete="new-password" {...form.getInputProps('password')} />
          <Button type="submit" loading={form.submitting}>{t('auth.submitRegister')}</Button>
          <Anchor component={Link} to="/login" size="sm">{t('auth.haveAccount')}</Anchor>
        </Stack>
      </form>
    </AuthLayout>
  );
}
