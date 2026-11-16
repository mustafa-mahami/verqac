import { Alert, Button, Card, PasswordInput, SegmentedControl, SimpleGrid, Stack, Text, TextInput, Title } from '@mantine/core';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError, type User } from '../api';
import { useAuth } from '../auth';
import { applyLanguage } from '../i18n';

export default function Account() {
  const { t } = useTranslation();
  const { me, reload } = useAuth();
  const u = me!.user;
  const [names, setNames] = useState({ full_name_ar: u.full_name_ar, full_name_en: u.full_name_en, locale: u.locale });
  const [pw, setPw] = useState({ current: '', next: '', again: '' });
  const [msg, setMsg] = useState<{ at: string; ok: boolean; text: string } | null>(null);
  const err = (e: unknown) => t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic'));
  const saveNames = async () => {
    try {
      await api<User>('/auth/me', { method: 'PATCH', body: JSON.stringify(names) });
      applyLanguage(names.locale === 'en' ? 'en' : 'ar');
      await reload();
      setMsg({ at: 'names', ok: true, text: t('settings.saved') });
    } catch (e) { setMsg({ at: 'names', ok: false, text: err(e) }); }
  };
  const savePw = async () => {
    if (pw.next !== pw.again) return setMsg({ at: 'pw', ok: false, text: t('account.mismatch') });
    try {
      await api('/auth/password', { method: 'POST', body: JSON.stringify({ current_password: pw.current, new_password: pw.next }) });
      setPw({ current: '', next: '', again: '' });
      setMsg({ at: 'pw', ok: true, text: t('account.passwordChanged') });
    } catch (e) { setMsg({ at: 'pw', ok: false, text: err(e) }); }
  };
  const note = (at: string) => msg?.at === at && <Alert color={msg.ok ? 'green' : 'red'}>{msg.text}</Alert>;
  return (
    <Stack maw={640} mx="auto">
      <Title order={3}>{t('account.title')}</Title>
      <Card withBorder>
        <Stack>
          <Text size="sm" c="dimmed">{t('auth.email')}: <Text span dir="ltr" fw={500} c="dark">{u.email}</Text></Text>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput label={t('auth.fullNameAr')} value={names.full_name_ar} onChange={(e) => setNames({ ...names, full_name_ar: e.currentTarget.value })} />
            <TextInput label={t('auth.fullNameEn')} dir="ltr" value={names.full_name_en} onChange={(e) => setNames({ ...names, full_name_en: e.currentTarget.value })} />
          </SimpleGrid>
          <div>
            <Text size="sm" fw={500} mb={4}>{t('account.language')}</Text>
            <SegmentedControl value={names.locale} onChange={(v) => setNames({ ...names, locale: v })}
              data={[{ value: 'ar', label: 'العربية' }, { value: 'en', label: 'English' }]} />
          </div>
          {note('names')}
          <Button onClick={saveNames} w="fit-content">{t('rec.save')}</Button>
        </Stack>
      </Card>
      <Card withBorder>
        <Stack>
          <Title order={5}>{t('account.changePassword')}</Title>
          <PasswordInput label={t('account.currentPassword')} dir="ltr" value={pw.current} autoComplete="current-password"
            onChange={(e) => setPw({ ...pw, current: e.currentTarget.value })} />
          <PasswordInput label={t('account.newPassword')} description={t('account.passwordHint')} dir="ltr" value={pw.next} autoComplete="new-password"
            onChange={(e) => setPw({ ...pw, next: e.currentTarget.value })} />
          <PasswordInput label={t('account.confirmPassword')} dir="ltr" value={pw.again} autoComplete="new-password"
            onChange={(e) => setPw({ ...pw, again: e.currentTarget.value })} />
          <Text size="xs" c="dimmed">{t('account.otherDevices')}</Text>
          {note('pw')}
          <Button onClick={savePw} w="fit-content" disabled={!pw.current || pw.next.length < 10}>{t('account.savePassword')}</Button>
        </Stack>
      </Card>
    </Stack>
  );
}
