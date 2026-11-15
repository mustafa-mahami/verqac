import { Alert, Badge, Button, Card, Group, Modal, Select, SimpleGrid, Stack, Text, TextInput, Title } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useDisclosure } from '@mantine/hooks';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError, type ProjectItem } from '../api';
import { useAuth } from '../auth';
import { pick } from '../i18n';

function ProjectCard({ item }: { item: ProjectItem }) {
  const { t } = useTranslation();
  const p = item.project;
  return (
    <Card withBorder padding="md">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <div>
          <Text fw={600}>{pick(p, 'name')}</Text>
          <Text size="sm" c="dimmed" dir="ltr" ta="start">{p.code}</Text>
        </div>
        {item.my_role && <Badge variant="light" tt="none" style={{ flexShrink: 0 }}>{pick(item.my_role, 'name')}</Badge>}
      </Group>
      <Stack gap={4} mt="sm">
        {item.parties.map((party) => (
          <Group key={party.id} gap="xs" wrap="nowrap">
            <Text size="sm" c="dimmed" w={80}>{t(`party.${party.kind}`)}</Text>
            <Text size="sm" truncate>{party.org ? pick(party.org, 'name') : party.placeholder_name}</Text>
            {party.status !== 'active' && <Badge size="xs" color="gray" variant="outline" tt="none" style={{ flexShrink: 0 }}>{t(`partyStatus.${party.status}`)}</Badge>}
          </Group>
        ))}
      </Stack>
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
      contract_no: '', start_date: '', end_date: '', consultant_name: '', owner_name: '',
    },
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
        <TextInput label={t('projects.code')} description={t('projects.codeHint')} dir="ltr" required maxLength={20}
          {...form.getInputProps('code')} />
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
    <Stack maw={1100} mx="auto">
      <Group justify="space-between">
        <Title order={3}>{t('projects.title')}</Title>
        {canCreate && <Button onClick={open}>{t('projects.new')}</Button>}
      </Group>
      {!isLoading && data?.length === 0 && <Text c="dimmed">{t('projects.empty')}</Text>}
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
        {data?.map((item) => <ProjectCard key={item.project.id} item={item} />)}
      </SimpleGrid>
      <Modal opened={opened} onClose={close} title={t('projects.new')} size="lg">
        <NewProject onClose={close} />
      </Modal>
    </Stack>
  );
}
