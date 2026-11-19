import { ActionIcon, Badge, Group, Image, Modal, SimpleGrid, Skeleton, Text, UnstyledButton } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { fetchBlob, type Attachment } from '../api';

export const isPhoto = (a: { content_type: string }) => a.content_type.startsWith('image/');

/** A protected image (the token is in memory, so an <img src> cannot carry it). */
function useImage(fileId: string) {
  return useQuery({
    queryKey: ['image', fileId], staleTime: Infinity, gcTime: 10 * 60_000,
    queryFn: async () => URL.createObjectURL(await fetchBlob(`/files/${fileId}`)),
  });
}

function Thumb({ a, onOpen, onRemove }: { a: Attachment; onOpen: () => void; onRemove?: () => void }) {
  const { t } = useTranslation();
  const img = useImage(a.file_id);
  return (
    <div style={{ position: 'relative' }}>
      <UnstyledButton onClick={onOpen} w="100%" aria-label={a.filename}>
        {img.data
          ? <Image src={img.data} h={170} radius="sm" fit="contain" alt={a.filename}
              style={{ background: 'var(--mantine-color-gray-1)', border: '1px solid var(--mantine-color-gray-3)' }} />
          : <Skeleton h={170} radius="sm" />}
      </UnstyledButton>
      <Badge size="xs" tt="none" variant="white" color={a.kind === 'response' ? 'teal' : 'gray'}
        style={{ position: 'absolute', top: 4, insetInlineStart: 4 }}>{t(`rec.kind.${a.kind}`)}</Badge>
      {onRemove && (
        <ActionIcon size="sm" color="red" variant="filled" radius="xl" aria-label="remove" onClick={onRemove}
          style={{ position: 'absolute', top: 4, insetInlineEnd: 4 }}>×</ActionIcon>
      )}
    </div>
  );
}

function Large({ a }: { a: Attachment }) {
  const img = useImage(a.file_id);
  return img.data ? <Image src={img.data} fit="contain" mah="80vh" w="100%" alt={a.filename} /> : <Skeleton h={400} />;
}

export default function Photos({ items, canRemove, onRemove }: {
  items: Attachment[]; canRemove: (a: Attachment) => boolean; onRemove: (a: Attachment) => void;
}) {
  const [idx, setIdx] = useState<number | null>(null);
  const open = idx === null ? null : items[idx] ?? null;
  const step = (d: number) => setIdx((i) => (i === null ? i : (i + d + items.length) % items.length));
  useEffect(() => {
    if (idx === null) return;
    const rtl = document.documentElement.dir === 'rtl';
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') step(rtl ? 1 : -1);
      else if (e.key === 'ArrowRight') step(rtl ? -1 : 1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });
  if (!items.length) return null;
  return (
    <>
      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="xs" mb="sm">
        {items.map((a, i) => <Thumb key={a.id} a={a} onOpen={() => setIdx(i)} onRemove={canRemove(a) ? () => onRemove(a) : undefined} />)}
      </SimpleGrid>
      <Modal opened={open !== null} onClose={() => setIdx(null)} size="90%" centered
        title={open ? <Text size="sm" dir="ltr">{open.filename} · {(idx ?? 0) + 1} / {items.length}</Text> : ''}>
        {open && (
          <Group wrap="nowrap" gap="xs" align="center">
            {items.length > 1 && <ActionIcon variant="light" size="lg" aria-label="prev" onClick={() => step(-1)}>{document.documentElement.dir === 'rtl' ? '›' : '‹'}</ActionIcon>}
            <div style={{ flex: 1, minWidth: 0 }}><Large a={open} /></div>
            {items.length > 1 && <ActionIcon variant="light" size="lg" aria-label="next" onClick={() => step(1)}>{document.documentElement.dir === 'rtl' ? '‹' : '›'}</ActionIcon>}
          </Group>
        )}
      </Modal>
    </>
  );
}

/** Phone photos are large: shrink to 2000 px (JPEG) before upload; other files go as they are. */
export async function shrinkPhoto(file: File): Promise<File> {
  if (!/^image\/(jpeg|png|webp)$/.test(file.type) || file.size < 600_000) return file;
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' });
    const scale = Math.min(1, 2000 / Math.max(bmp.width, bmp.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(bmp.width * scale);
    canvas.height = Math.round(bmp.height * scale);
    canvas.getContext('2d')!.drawImage(bmp, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, 'image/jpeg', 0.85));
    if (!blob || blob.size >= file.size) return file;
    return new File([blob], file.name.replace(/\.\w+$/, '') + '.jpg', { type: 'image/jpeg' });
  } catch {
    return file;
  }
}
