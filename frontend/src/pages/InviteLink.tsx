import { Alert, Button, CopyButton, Stack, Text, TextInput } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import type { InviteOut } from '../api';

/** Shown after any invitation: the link is always visible so it can be sent by hand. */
export default function InviteLink({ invite, onDone }: { invite: InviteOut; onDone: () => void }) {
  const { t, i18n } = useTranslation();
  const date = new Date(invite.expires_at).toLocaleDateString(i18n.language === 'en' ? 'en-GB' : 'ar-PS-u-nu-latn');
  return (
    <Stack>
      <Alert color={invite.email_sent ? 'green' : 'yellow'}>
        {invite.email_sent ? t('invite.emailSent', { email: invite.email }) : t('invite.emailNotSent', { email: invite.email })}
      </Alert>
      <TextInput label={t('invite.linkTitle')} value={invite.link} readOnly dir="ltr" onFocus={(e) => e.currentTarget.select()} />
      <Text size="xs" c="dimmed">{t('invite.validDays', { date })}</Text>
      <CopyButton value={invite.link}>
        {({ copied, copy }) => (
          <Button color={copied ? 'teal' : undefined} onClick={copy}>{copied ? t('invite.copied') : t('invite.copy')}</Button>
        )}
      </CopyButton>
      <Button variant="default" onClick={onDone}>{t('common.close')}</Button>
    </Stack>
  );
}
