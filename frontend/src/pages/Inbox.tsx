import { Badge, Card, Group, Select, Stack, Table, Text, Title } from '@mantine/core';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { api, type InboxItem } from '../api';
import { fmtDate, requiredColor, stateColor } from '../format';
import { pick } from '../i18n';

const reasonColor = { reply: 'blue', returned: 'orange', draft: 'gray' } as const;

export default function Inbox() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const items = useQuery({ queryKey: ['inbox'], queryFn: () => api<InboxItem[]>('/inbox'), refetchInterval: 60_000 });
  const [project, setProject] = useState<string | null>(null);
  const [kind, setKind] = useState<string | null>(null);
  const all = items.data ?? [];
  const kindName = (i: InboxItem) => (i.submittal_kind_name ? pick({ n_ar: i.submittal_kind_name.ar, n_en: i.submittal_kind_name.en }, 'n') : '');
  const projects = [...new Map(all.map((i) => [i.project_id, `${i.project_code} · ${pick({ n_ar: i.project_name_ar, n_en: i.project_name_en }, 'n')}`])).entries()];
  const kinds = [...new Set(all.map(kindName).filter(Boolean))];
  const shown = all.filter((i) => (!project || i.project_id === project) && (!kind || kindName(i) === kind));

  return (
    <Stack maw={1300} mx="auto">
      <Group justify="space-between">
        <Title order={3}>{t('inbox.title')}</Title>
        <Group gap="xs">
          {projects.length > 1 && (
            <Select size="xs" w={240} clearable placeholder={t('inbox.allProjects')} value={project} onChange={setProject}
              data={projects.map(([value, label]) => ({ value, label }))} />
          )}
          {kinds.length > 1 && (
            <Select size="xs" w={180} clearable placeholder={t('inbox.allKinds')} value={kind} onChange={setKind} data={kinds} />
          )}
        </Group>
      </Group>
      {items.isSuccess && shown.length === 0 ? <Text c="dimmed">{t('inbox.empty')}</Text> : (
        <Card withBorder p={0}>
          <Table.ScrollContainer minWidth={900}>
            <Table highlightOnHover verticalSpacing="sm" horizontalSpacing="md">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th />
                  <Table.Th>{t('inbox.project')}</Table.Th>
                  <Table.Th>{t('rec.number')}</Table.Th>
                  <Table.Th>{t('rec.title')}</Table.Th>
                  <Table.Th>{t('rec.state')}</Table.Th>
                  <Table.Th>{t('rec.due')}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {shown.map((i) => (
                  <Table.Tr key={i.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/records/${i.id}`)}>
                    <Table.Td>
                      <Badge tt="none" variant="light" color={reasonColor[i.reason]}>{t(`inbox.reason.${i.reason}`)}</Badge>
                      {i.assigned_to_me && <Badge ms={4} tt="none" size="xs" variant="outline">{t('inbox.assignedToMe')}</Badge>}
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" fw={500} dir="ltr" ta="start">{i.project_code}</Text>
                      <Text size="xs" c="dimmed" lineClamp={1}>{pick({ name_ar: i.project_name_ar, name_en: i.project_name_en }, 'name')}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" dir="ltr" ta="start" style={{ whiteSpace: 'nowrap' }}>{i.number} · R{i.rev_no}</Text>
                      <Text size="xs" c="dimmed">{pick(i.record_type, 'name')}</Text>
                    </Table.Td>
                    <Table.Td><Text size="sm" lineClamp={2}>{i.title}</Text></Table.Td>
                    <Table.Td><Badge tt="none" variant="light" color={stateColor(i.state.color)}>{pick(i.state, 'name')}</Badge></Table.Td>
                    <Table.Td>
                      <Text size="sm" c={i.overdue ? 'red' : undefined} fw={i.overdue ? 600 : undefined}>{fmtDate(i.due_at)}</Text>
                      {i.overdue && <Badge size="xs" color="red" tt="none">{t('rec.overdue')}</Badge>}
                      {i.required_by && (
                        <Badge size="xs" tt="none" variant="light" color={requiredColor(i.required_by)} style={{ display: 'block' }}>
                          {t('rec.requiredByShort')} {fmtDate(i.required_by)}
                        </Badge>
                      )}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>
      )}
    </Stack>
  );
}
