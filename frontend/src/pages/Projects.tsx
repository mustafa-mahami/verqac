import { Alert, Badge, Button, Card, Group, Modal, Progress, Select, SimpleGrid, Stack, Table, Text, TextInput, Title, Tooltip } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useDisclosure } from '@mantine/hooks';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { api, ApiError, type ProjectItem, type ProjectTypeT } from '../api';
import { useAuth } from '../auth';
import { pick } from '../i18n';
import { fmtDate } from '../format';

function partyName(item: ProjectItem, kind: string) {
  const p = item.parties.find((x) => x.kind === kind);
  if (!p) return null;
  return { name: p.org ? pick(p.org, 'name') : p.placeholder_name, joined: p.status === 'active' };
}

function ProjectsTable({ items }: { items: ProjectItem[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const party = (item: ProjectItem, kind: string) => {
    const x = partyName(item, kind);
    if (!x) return <Text size="sm" c="dimmed">—</Text>;
    return (
      <Group gap={4} wrap="nowrap">
        <Text size="sm" lineClamp={1}>{x.name}</Text>
        {!x.joined && <Badge size="xs" color="gray" variant="outline" tt="none" style={{ flexShrink: 0 }}>{t('partyStatus.invited')}</Badge>}
      </Group>
    );
  };
  return (
    <Card withBorder p={0}>
      <Table.ScrollContainer minWidth={980}>
        <Table highlightOnHover verticalSpacing="sm" horizontalSpacing="md">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('projects.colCode')}</Table.Th>
              <Table.Th>{t('projects.colName')}</Table.Th>
              <Table.Th>{t('projects.client')}</Table.Th>
              <Table.Th>{t('party.consultant')}</Table.Th>
              <Table.Th>{t('party.owner')}</Table.Th>
              <Table.Th>{t('projects.myRole')}</Table.Th>
              <Table.Th>{t('projects.startDate')}</Table.Th>
              <Table.Th>{t('projects.endDate')}</Table.Th>
              <Table.Th miw={140}>{t('projects.colProgress')}</Table.Th>
              <Table.Th ta="center">{t('projects.colOpen')}</Table.Th>
              <Table.Th ta="center">{t('projects.colOverdue')}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {items.map((item) => {
              const p = item.project;
              return (
                <Table.Tr key={p.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/projects/${p.id}`)}>
                  <Table.Td><Text size="sm" fw={600} dir="ltr">{p.code}</Text></Table.Td>
                  <Table.Td><Text size="sm" fw={500} lineClamp={1}>{pick(p, 'name')}</Text></Table.Td>
                  <Table.Td><Text size="sm" lineClamp={1}>{p.client_name ?? '—'}</Text></Table.Td>
                  <Table.Td>{party(item, 'consultant')}</Table.Td>
                  <Table.Td>{party(item, 'owner')}</Table.Td>
                  <Table.Td><Text size="sm">{item.my_role ? pick(item.my_role, 'name') : '—'}</Text></Table.Td>
                  <Table.Td><Text size="sm" dir="ltr" ta="start">{p.start_date ? fmtDate(p.start_date) : '—'}</Text></Table.Td>
                  <Table.Td><Text size="sm" dir="ltr" ta="start">{p.end_date ? fmtDate(p.end_date) : '—'}</Text></Table.Td>
                  <Table.Td>
                    {item.stats.progress === null || item.stats.progress === undefined ? <Text size="sm" c="dimmed">—</Text> : (() => {
                      const behind = item.stats.planned !== null && item.stats.planned !== undefined && item.stats.progress + 5 < item.stats.planned;
                      return (
                        <Tooltip label={item.stats.planned !== null && item.stats.planned !== undefined
                          ? t('projects.progressTip', { a: item.stats.progress, p: item.stats.planned }) : t('projects.progressNoPlan')}>
                          <Group gap={6} wrap="nowrap">
                            <Progress value={item.stats.progress} w={70} size="sm" color={behind ? 'red' : 'verqac'} />
                            <Text size="sm" fw={600} c={behind ? 'red' : undefined}>{item.stats.progress}%</Text>
                          </Group>
                        </Tooltip>
                      );
                    })()}
                  </Table.Td>
                  <Table.Td ta="center"><Text size="sm" fw={item.stats.open ? 600 : 400}>{item.stats.open}</Text></Table.Td>
                  <Table.Td ta="center">
                    {item.stats.overdue ? <Badge color="red" tt="none">{item.stats.overdue}</Badge> : <Text size="sm" c="dimmed">0</Text>}
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Card>
  );
}

function NewProject({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const { me } = useAuth();
  const qc = useQueryClient();
  const adminOrgs = (me?.orgs ?? []).filter((m) => m.org_role === 'admin' && m.org.kind !== 'owner');
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: {
      org_id: adminOrgs[0]?.org.id ?? '', code: '', name_ar: '', name_en: '', client_name: '', donor_name: '',
      contract_no: '', start_date: '', end_date: '', consultant_name: '', owner_name: '', project_type_id: '',
    },
  });
  const types = useQuery({
    queryKey: ['projectTypes', form.values.org_id], enabled: !!form.values.org_id,
    queryFn: () => api<ProjectTypeT[]>(`/orgs/${form.values.org_id}/project-types`),
  });
  const create = useMutation({
    mutationFn: (v: typeof form.values) => {
      const body = Object.fromEntries(Object.entries(v).map(([k, val]) => [k, val === '' ? null : val]));
      return api<ProjectItem>('/projects', { method: 'POST', body: JSON.stringify(body) });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['projects'] });
      onClose();
    },
    onError: (e) => setError(e instanceof ApiError ? e.code : 'generic'),
  });

  return (
    <form onSubmit={form.onSubmit((v) => create.mutate(v))}>
      <Stack>
        {error && <Alert color="red">{t(`errors.${error}`, t('errors.generic'))}</Alert>}
        {adminOrgs.length > 1 && (
          <Select label={t('projects.org')} data={adminOrgs.map((m) => ({ value: m.org.id, label: pick(m.org, 'name') }))}
            {...form.getInputProps('org_id')} />
        )}
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label={t('projects.code')} description={t('projects.codeHint')} dir="ltr" required maxLength={20}
            {...form.getInputProps('code')} />
          <Select label={t('structure.projectType')} description={t('projects.typeHint')} clearable
            data={(types.data ?? []).filter((x) => x.is_active).map((x) => ({ value: x.id!, label: pick(x, 'name') }))}
            {...form.getInputProps('project_type_id')} />
        </SimpleGrid>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label={t('projects.nameAr')} dir="rtl" required {...form.getInputProps('name_ar')} />
          <TextInput label={t('projects.nameEn')} dir="ltr" required {...form.getInputProps('name_en')} />
          <TextInput label={t('projects.client')} {...form.getInputProps('client_name')} />
          <TextInput label={t('projects.donor')} {...form.getInputProps('donor_name')} />
          <TextInput label={t('projects.contractNo')} {...form.getInputProps('contract_no')} />
          <div />
          <TextInput type="date" label={t('projects.startDate')} {...form.getInputProps('start_date')} />
          <TextInput type="date" label={t('projects.endDate')} {...form.getInputProps('end_date')} />
          <TextInput label={t('projects.consultantName')} {...form.getInputProps('consultant_name')} />
          <TextInput label={t('projects.ownerName')} {...form.getInputProps('owner_name')} />
        </SimpleGrid>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="submit" loading={create.isPending}>{t('projects.create')}</Button>
        </Group>
      </Stack>
    </form>
  );
}

export default function Projects() {
  const { t } = useTranslation();
  const { me } = useAuth();
  const [opened, { open, close }] = useDisclosure(false);
  const { data, isLoading } = useQuery({ queryKey: ['projects'], queryFn: () => api<ProjectItem[]>('/projects') });
  const canCreate = (me?.orgs ?? []).some((m) => m.org_role === 'admin' && m.org.kind !== 'owner');

  return (
    <Stack maw={1300} mx="auto">
      <Group justify="space-between">
        <Title order={3}>{t('projects.title')}</Title>
        {canCreate && <Button onClick={open}>{t('projects.new')}</Button>}
      </Group>
      {!isLoading && data?.length === 0 && <Text c="dimmed">{t('projects.empty')}</Text>}
      {!!data?.length && <ProjectsTable items={data} />}
      <Modal opened={opened} onClose={close} title={t('projects.new')} size="lg">
        <NewProject onClose={close} />
      </Modal>
    </Stack>
  );
}
