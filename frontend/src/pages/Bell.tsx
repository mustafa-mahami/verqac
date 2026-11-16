import { ActionIcon, Button, Divider, Indicator, Popover, ScrollArea, Stack, Text, UnstyledButton } from '@mantine/core';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { api, type NotificationItem, type Notifications } from '../api';
import { fmtDate } from '../format';
import { pick } from '../i18n';

export default function Bell() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const data = useQuery({ queryKey: ['notifications'], queryFn: () => api<Notifications>('/notifications'), refetchInterval: 60_000 });

  const read = async (body: { ids?: number[]; all?: boolean }) => {
    await api('/notifications/read', { method: 'POST', body: JSON.stringify(body) }).catch(() => undefined);
    qc.invalidateQueries({ queryKey: ['notifications'] });
  };
  const openItem = (n: NotificationItem) => {
    setOpen(false);
    if (!n.read) void read({ ids: [n.id] });
    qc.invalidateQueries({ queryKey: ['inbox'] });
    if (n.record_id) navigate(`/records/${n.record_id}`);
  };
  const unread = data.data?.unread ?? 0;

  return (
    <Popover opened={open} onChange={setOpen} width={360} position="bottom-end" shadow="md">
      <Popover.Target>
        <Indicator disabled={!unread} label={unread > 99 ? '99+' : unread} size={16} color="red" offset={4}>
          <ActionIcon variant="subtle" size="lg" aria-label={t('bell.title')} onClick={() => setOpen((o) => !o)}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
            </svg>
          </ActionIcon>
        </Indicator>
      </Popover.Target>
      <Popover.Dropdown p={0}>
        <Text fw={600} p="sm">{t('bell.title')}</Text>
        <Divider />
        <ScrollArea.Autosize mah={420}>
          {!data.data?.items.length ? <Text size="sm" c="dimmed" p="sm">{t('bell.empty')}</Text> : (
            <Stack gap={0}>
              {data.data.items.map((n) => (
                <UnstyledButton key={n.id} onClick={() => openItem(n)} p="sm"
                  style={{ background: n.read ? undefined : 'var(--mantine-color-blue-0)', borderBottom: '1px solid var(--mantine-color-gray-2)' }}>
                  <Text size="sm" fw={n.read ? 400 : 600}>{pick(n, 'title')}</Text>
                  {n.body && <Text size="xs" c="dimmed" lineClamp={2}>{n.body}</Text>}
                  <Text size="xs" c="dimmed">{fmtDate(n.created_at, true)}</Text>
                </UnstyledButton>
              ))}
            </Stack>
          )}
        </ScrollArea.Autosize>
        {unread > 0 && (
          <>
            <Divider />
            <Button variant="subtle" fullWidth size="xs" onClick={() => read({ all: true })}>{t('bell.readAll')}</Button>
          </>
        )}
      </Popover.Dropdown>
    </Popover>
  );
}
