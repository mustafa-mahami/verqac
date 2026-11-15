import { Center, Group, Paper, Stack, Text, Title } from '@mantine/core';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { LanguageButton } from '../App';

export default function AuthLayout({ title, children, width = 420 }: { title: string; children: ReactNode; width?: number }) {
  const { t } = useTranslation();
  return (
    <Center mih="100vh" p="md" bg="gray.0">
      <Stack w="100%" maw={width} gap="md">
        <Group justify="space-between">
          <div>
            <Title order={2} c="verqac.7">{t('app.name')}</Title>
            <Text size="sm" c="dimmed">{t('app.tagline')}</Text>
          </div>
          <LanguageButton />
        </Group>
        <Paper withBorder shadow="xs" p="lg">
          <Title order={4} mb="md">{title}</Title>
          {children}
        </Paper>
      </Stack>
    </Center>
  );
}
