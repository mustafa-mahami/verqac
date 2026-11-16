import { Stack, Tabs, Text, Title } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useParams, useSearchParams } from 'react-router-dom';
import { api, type ProjectItem } from '../api';
import { pick } from '../i18n';
import BackButton from './BackButton';
import ProjectSettings from './ProjectSettings';
import ProjectTeam from './ProjectTeam';
import Submittals from './Submittals';

export default function ProjectPage() {
  const { t } = useTranslation();
  const { id = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'submittals';
  const item = useQuery({ queryKey: ['project', id], queryFn: () => api<ProjectItem>(`/projects/${id}`) });

  return (
    <Stack maw={1200} mx="auto">
      <BackButton to="/projects" label={t('back.projects')} />
      {item.data && (
        <div>
          <Title order={3}>{pick(item.data.project, 'name')}</Title>
          <Text c="dimmed" size="sm" dir="ltr" ta="start">{item.data.project.code}</Text>
        </div>
      )}
      <Tabs value={tab} onChange={(v) => setParams({ tab: v ?? 'submittals' }, { replace: true })} keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="submittals">{t('project.tabs.submittals')}</Tabs.Tab>
          <Tabs.Tab value="inspections">{t('project.tabs.inspections')}</Tabs.Tab>
          <Tabs.Tab value="team">{t('project.tabs.team')}</Tabs.Tab>
          <Tabs.Tab value="settings">{t('project.tabs.settings')}</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="submittals" pt="md"><Submittals projectId={id} /></Tabs.Panel>
        <Tabs.Panel value="inspections" pt="md"><Submittals projectId={id} type="inspection" /></Tabs.Panel>
        <Tabs.Panel value="team" pt="md"><ProjectTeam /></Tabs.Panel>
        <Tabs.Panel value="settings" pt="md"><ProjectSettings projectId={id} /></Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
