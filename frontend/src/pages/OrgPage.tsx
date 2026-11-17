import { Stack, Tabs } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth';
import OrgUsers from './OrgUsers';
import ProjectTypes from './ProjectTypes';
import OrgCalendar from './Calendar';

/** Organization settings for its admins: users, and project types with their templates. */
export default function OrgPage() {
  const { t } = useTranslation();
  const { me } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'users';
  const admin = (me?.orgs ?? []).find((m) => m.org_role === 'admin');
  if (!admin) return null;
  return (
    <Stack maw={1200} mx="auto" w="100%">
      <Tabs value={tab} onChange={(v) => setParams({ tab: v ?? 'users' }, { replace: true })} keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="users">{t('org.tabs.users')}</Tabs.Tab>
          <Tabs.Tab value="types">{t('org.tabs.types')}</Tabs.Tab>
          <Tabs.Tab value="calendar">{t('org.tabs.calendar')}</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="users"><OrgUsers /></Tabs.Panel>
        <Tabs.Panel value="types"><ProjectTypes orgId={admin.org.id} /></Tabs.Panel>
        <Tabs.Panel value="calendar"><OrgCalendar orgId={admin.org.id} /></Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
