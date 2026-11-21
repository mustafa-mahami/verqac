import { Stack, Tabs, Text, Title } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useParams, useSearchParams } from 'react-router-dom';
import { api, type ProjectItem, type ProjectSettings as SettingsT } from '../api';
import { pick } from '../i18n';
import BackButton from './BackButton';
import ProjectSettings from './ProjectSettings';
import ProjectTeam from './ProjectTeam';
import Submittals from './Submittals';
import ProgressMatrix from './ProgressMatrix';
import PeriodicPanel from './PeriodicPanel';
import KpiPanel from './KpiPanel';
import CashflowPanel, { useFinance } from './CashflowPanel';
import { TYPE_TABS } from '../recordTypes';

export default function ProjectPage() {
  const { t } = useTranslation();
  const { id = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'submittals';
  const item = useQuery({ queryKey: ['project', id], queryFn: () => api<ProjectItem>(`/projects/${id}`) });
  const settings = useQuery({ queryKey: ['settings', id], queryFn: () => api<SettingsT>(`/projects/${id}/settings`) });
  const finance = useFinance(id);
  // money (payment applications, cash flow) only for the roles that may see it
  const tabs = TYPE_TABS.filter(([code]) => (!settings.data || settings.data.types.includes(code)) && (code !== 'payment' || !!finance.data));

  return (
    <Stack maw={tab === 'progress' ? '100%' : 1200} mx="auto">
      <BackButton to="/projects" label={t('back.projects')} />
      {item.data && (
        <div>
          <Title order={3}>{pick(item.data.project, 'name')}</Title>
          <Text c="dimmed" size="sm" dir="ltr" ta="start">{item.data.project.code}</Text>
        </div>
      )}
      <Tabs value={tab} onChange={(v) => setParams({ tab: v ?? 'submittals' }, { replace: true })} keepMounted={false}>
        <Tabs.List>
          {tabs.map(([, tabKey]) => <Tabs.Tab key={tabKey} value={tabKey}>{t(`project.tabs.${tabKey}`)}</Tabs.Tab>)}
          <Tabs.Tab value="progress">{t('project.tabs.progress')}</Tabs.Tab>
          <Tabs.Tab value="reports">{t('project.tabs.reports')}</Tabs.Tab>
          <Tabs.Tab value="kpi">{t('project.tabs.kpi')}</Tabs.Tab>
          {finance.data && <Tabs.Tab value="cash">{t('project.tabs.cash')}</Tabs.Tab>}
          <Tabs.Tab value="team">{t('project.tabs.team')}</Tabs.Tab>
          <Tabs.Tab value="settings">{t('project.tabs.settings')}</Tabs.Tab>
        </Tabs.List>
        {tabs.map(([code, tabKey]) => (
          <Tabs.Panel key={tabKey} value={tabKey} pt="md"><Submittals projectId={id} type={code} /></Tabs.Panel>
        ))}
        <Tabs.Panel value="progress" pt="md"><ProgressMatrix projectId={id} /></Tabs.Panel>
        <Tabs.Panel value="reports" pt="md"><PeriodicPanel projectId={id} /></Tabs.Panel>
        <Tabs.Panel value="kpi" pt="md"><KpiPanel projectId={id} /></Tabs.Panel>
        <Tabs.Panel value="cash" pt="md"><CashflowPanel projectId={id} /></Tabs.Panel>
        <Tabs.Panel value="team" pt="md"><ProjectTeam /></Tabs.Panel>
        <Tabs.Panel value="settings" pt="md"><ProjectSettings projectId={id} /></Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
