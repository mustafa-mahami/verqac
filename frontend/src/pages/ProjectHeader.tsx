import { Alert, Button, Card, FileButton, Group, Image, Text, Title } from '@mantine/core';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError, blobUrl, type ProjectSettings } from '../api';

/** The project's letterhead: one wide image with the parties' logos, printed at the top of the project's PDFs. */
export default function ProjectHeader({ projectId, settings }: { projectId: string; settings: ProjectSettings }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true, made: string | null = null;
    if (settings.has_header) blobUrl(`/projects/${projectId}/header`).then((u) => { made = u; if (live) setUrl(u); });
    else setUrl(null);
    return () => { live = false; if (made) URL.revokeObjectURL(made); };
  }, [projectId, settings.has_header, settings]);
  const run = async (fn: () => Promise<ProjectSettings>) => {
    setBusy(true); setError(null);
    try { qc.setQueryData(['settings', projectId], await fn()); }
    catch (e) { setError(t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic'))); }
    finally { setBusy(false); }
  };
  const upload = (file: File | null) => file && run(() => {
    const fd = new FormData();
    fd.append('file', file);
    return api<ProjectSettings>(`/projects/${projectId}/header`, { method: 'POST', body: fd });
  });
  return (
    <Card withBorder>
      <Title order={5}>{t('header.title')}</Title>
      <Text size="sm" c="dimmed" mb="md">{t('header.hint')}</Text>
      {url
        ? <Image src={url} alt="" radius="sm" style={{ border: '1px solid var(--mantine-color-gray-3)', background: 'white' }} mah={140} fit="contain" />
        : <Text size="sm" c="dimmed" ta="center" py="lg" style={{ border: '1px dashed var(--mantine-color-gray-4)', borderRadius: 8 }}>{t('header.none')}</Text>}
      {error && <Alert mt="sm" color="red">{error}</Alert>}
      {settings.can_edit && (
        <Group mt="md">
          <FileButton accept="image/png,image/jpeg,image/webp" onChange={upload}>
            {(props) => <Button {...props} variant="light" loading={busy}>{url ? t('header.replace') : t('header.upload')}</Button>}
          </FileButton>
          {url && <Button variant="subtle" color="red" disabled={busy}
            onClick={() => run(() => api<ProjectSettings>(`/projects/${projectId}/header`, { method: 'DELETE' }))}>{t('header.remove')}</Button>}
        </Group>
      )}
    </Card>
  );
}
