import { Alert, Badge, Group, Loader, Stack, Table, Text } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { api } from '../api';
import { fmtDate, stateColor } from '../format';
import AuthLayout from './AuthLayout';

interface Name { ar: string; en: string }
interface VState { code: string; category: string; color: string | null; name: Name }
interface VerifyInfo {
  stamp: string; intact: boolean; project_code: string; project: Name; contractor: Name | null; consultant: Name | null;
  record_type: Name; number: string; rev_no: number; title: string; decision: VState; answered_at: string;
  answered_by: Name; on_behalf_of: Name | null; latest_rev: number; latest_state: VState | null; cancelled: boolean;
}

/** Public page opened from the QR on a printed reply. Works signed in or not. */
export default function Verify() {
  const { t, i18n } = useTranslation();
  const { stamp = '' } = useParams();
  const q = useQuery({ queryKey: ['verify', stamp], queryFn: () => api<VerifyInfo>(`/verify/${stamp}`), retry: false });
  const n = (x: Name | null | undefined) => (x ? (i18n.language === 'en' ? x.en : x.ar) : '');
  const short = stamp.slice(0, 12).toUpperCase().replace(/(.{4})(?=.)/g, '$1-');

  let body;
  if (q.isLoading) body = <Group justify="center"><Loader /></Group>;
  else if (q.isError || !q.data) body = <Alert color="red" title={t('verify.notFound')}>{t('verify.notFoundHint')}</Alert>;
  else {
    const v = q.data;
    const row = (label: string, value: React.ReactNode) => (
      <Table.Tr><Table.Th w={150} fw={500} c="dimmed">{label}</Table.Th><Table.Td>{value}</Table.Td></Table.Tr>
    );
    body = (
      <Stack>
        {v.intact
          ? <Alert color="green" title={t('verify.ok')}>{t('verify.okHint')}</Alert>
          : <Alert color="red" title={t('verify.changed')}>{t('verify.changedHint')}</Alert>}
        {v.latest_state && (
          <Alert color="orange">{t('verify.newer', { rev: v.latest_rev, state: n(v.latest_state.name) })}</Alert>
        )}
        {v.cancelled && <Alert color="gray">{t('verify.cancelled')}</Alert>}
        <Table withRowBorders={false} verticalSpacing={6}>
          <Table.Tbody>
            {row(t('verify.project'), <>{n(v.project)} <Text span c="dimmed" dir="ltr">· {v.project_code}</Text></>)}
            {row(t('verify.record'), <>{n(v.record_type)} <Text span fw={600} dir="ltr" style={{ whiteSpace: 'nowrap' }}>{v.number} · R{v.rev_no}</Text></>)}
            {row(t('verify.subject'), v.title)}
            {row(t('verify.decision'), <Badge color={stateColor(v.decision.color ?? 'gray')} variant="light">{n(v.decision.name)}</Badge>)}
            {row(t('verify.answeredAt'), fmtDate(v.answered_at, true))}
            {row(t('verify.answeredBy'), <>{n(v.answered_by)}{v.on_behalf_of && <Text span c="dimmed" size="sm"> — {t('verify.onBehalf')} {n(v.on_behalf_of)}</Text>}</>)}
            {v.consultant && row(t('verify.consultant'), n(v.consultant))}
            {v.contractor && row(t('verify.contractor'), n(v.contractor))}
          </Table.Tbody>
        </Table>
      </Stack>
    );
  }
  return (
    <AuthLayout title={t('verify.title')} width={560}>
      <Stack>
        <Text size="sm" c="dimmed">{t('verify.stamp')}: <Text span fw={700} c="dark" dir="ltr">{short}</Text></Text>
        {body}
      </Stack>
    </AuthLayout>
  );
}
