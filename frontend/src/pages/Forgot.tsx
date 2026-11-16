import { Alert, Anchor, Button, Stack, Text, TextInput } from '@mantine/core';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { api } from '../api';
import AuthLayout from './AuthLayout';

export default function Forgot() {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState<null | boolean>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api<{ mail_enabled: boolean }>('/auth/forgot', { method: 'POST', body: JSON.stringify({ email }) });
      setSent(r.mail_enabled);
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthLayout title={t('account.forgotTitle')}>
      <form onSubmit={submit}>
        <Stack>
          {sent === null ? (
            <>
              <Text size="sm" c="dimmed">{t('account.forgotHint')}</Text>
              <TextInput label={t('auth.email')} type="email" dir="ltr" required value={email} onChange={(e) => setEmail(e.currentTarget.value)} />
              <Button type="submit" loading={busy}>{t('account.sendLink')}</Button>
            </>
          ) : (
            <Alert color={sent ? 'green' : 'yellow'}>{t(sent ? 'account.linkSent' : 'account.noMail')}</Alert>
          )}
          <Anchor component={Link} to="/" size="sm">{t('account.backToLogin')}</Anchor>
        </Stack>
      </form>
    </AuthLayout>
  );
}
