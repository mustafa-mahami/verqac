import { Stack, Tabs, Text, Title } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, useSearchParams } from 'react-router-dom';
import { api, type ProjectItem, type ProjectSettings as SettingsT } from '../api';
import { pick } from '../i18n';
import { PAGE_WIDTH } from '../format';
import BackButton from './BackButton';
import ProjectSettings from './ProjectSettings';
import ProjectTeam from './ProjectTeam';
import Submittals from './Submittals';
import ProgressMatrix from './ProgressMatrix';
import PeriodicPanel from './PeriodicPanel';
import KpiPanel from './KpiPanel';
import CashflowPanel, { useFinance } from './CashflowPanel';
import { TYPE_TABS } from '../recordTypes';

const GROUPS: [string, string[]][] = [
  ['daily', ['daily']],
  ['quality', ['submittals', 'inspections', 'materials', 'tests', 'ncrs', 'rfis', 'kpi']],
  ['progress', ['progress', 'reports']],
  ['finance', ['payments', 'cash']],
  ['documents', ['documents']],
  ['project', ['team', 'settings']],
];

export default function ProjectPage() {
  const { t } = useTranslation();
  const { id = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'submittals';
  const item = useQuery({ queryKey: ['project', id], queryFn: () => api<ProjectItem>(`/projects/${id}`) });
  const settings = useQuery({ queryKey: ['settings', id], queryFn: () => api<SettingsT>(`/projects/${id}/settings`) });
  const finance = useFinance(id);
  const last = useRef<Record<string, string>>({});  // the page last opened in each group
  // money (payment applications, cash flow) only for the roles that may see it
  const types = new Map(TYPE_TABS.filter(([code]) => (!settings.data || settings.data.types.includes(code)) && (code !== 'payment' || !!finance.data))
    .map(([code, key]) => [key, code]));
  const has = (key: string) => types.has(key) || ['progress', 'reports', 'kpi', 'team', 'settings'].includes(key) || (key === 'cash' && !!finance.data);
  // related pages under one heading; the page itself stays in the address (?tab=...), so old links still work
  const groups = GROUPS.map(([g, keys]) => [g, keys.filter(has)] as const).filter(([, keys]) => keys.length);
  const group = groups.find(([, keys]) => keys.includes(tab)) ?? groups.find(([g]) => g === 'quality') ?? groups[0];
  const leaf = group && group[1].includes(tab) ? tab : group?.[1][0] ?? 'submittals';
  const go = (key: string) => setParams({ tab: key }, { replace: true });

  const page = (key: string) => {
    if (types.has(key)) return <Submittals projectId={id} type={types.get(key)!} />;
    if (key === 'progress') return <ProgressMatrix projectId={id} />;
    if (key === 'reports') return <PeriodicPanel projectId={id} />;
    if (key === 'kpi') return <KpiPanel projectId={id} />;
    if (key === 'cash') return <CashflowPanel projectId={id} />;
    if (key === 'team') return <ProjectTeam />;
    if (key === 'settings') return <ProjectSettings projectId={id} />;
    return null;
  };

  return (
    <Stack maw={PAGE_WIDTH} mx="auto">
      <BackButton to="/projects" label={t('back.projects')} />
      {item.data && (
        <div>
          <Title order={3}>{pick(item.data.project, 'name')}</Title>
          <Text c="dimmed" size="sm" dir="ltr" ta="start">{item.data.project.code}</Text>
        </div>
      )}
      {group && (
        <Tabs value={group[0]} onChange={(g) => { const keys = groups.find(([x]) => x === g)?.[1]; if (keys) go(last.current[g!] && keys.includes(last.current[g!]) ? last.current[g!] : keys[0]); }}>
          <Tabs.List>
            {groups.map(([g, keys]) => (
              <Tabs.Tab key={g} value={g}>{keys.length === 1 ? t(`project.tabs.${keys[0]}`) : t(`project.groups.${g}`)}</Tabs.Tab>
            ))}
          </Tabs.List>
        </Tabs>
      )}
      {group && group[1].length > 1 && (
        <Tabs variant="pills" value={leaf} onChange={(v) => { if (v) { last.current[group[0]] = v; go(v); } }}>
          <Tabs.List>
            {group[1].map((key) => <Tabs.Tab key={key} value={key}>{t(`project.tabs.${key}`)}</Tabs.Tab>)}
          </Tabs.List>
        </Tabs>
      )}
      <div key={leaf}>{page(leaf)}</div>
    </Stack>
  );
}
