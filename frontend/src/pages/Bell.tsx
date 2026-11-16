import { ActionIcon, Button, Divider, Indicator, Popover, ScrollArea, Stack, Switch, Text, UnstyledButton } from '@mantine/core';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { api, type NotificationItem, type Notifications } from '../api';
import { fmtDate } from '../format';
import { currentSubscription, disablePush, enablePush, pushSupported } from '../push';
import { pick } from '../i18n';

// ---- browser alerts (while a Verqac tab is open, even in the background)
const PREF = 'verqac.alerts';
type Prefs = { desktop: boolean; sound: boolean };
function loadPrefs(): Prefs {
  try { return { desktop: false, sound: true, ...JSON.parse(localStorage.getItem(PREF) ?? '{}') }; } catch { return { desktop: false, sound: true }; }
}
function savePrefs(p: Prefs) { try { localStorage.setItem(PREF, JSON.stringify(p)); } catch { /* private mode */ } }

let audio: AudioContext | null = null;
// browsers allow sound only after the user has interacted with the page once
if (typeof window !== 'undefined') {
  const unlock = () => {
    try { audio ??= new AudioContext(); void audio.resume(); } catch { /* no audio */ }
    window.removeEventListener('pointerdown', unlock); window.removeEventListener('keydown', unlock);
  };
  window.addEventListener('pointerdown', unlock); window.addEventListener('keydown', unlock);
}

/** A short, soft two-note chime made in the browser (no sound file). */
export function chime() {
  try {
    audio ??= new AudioContext();
    const now = audio.currentTime;
    [[880, 0], [1320, 0.16]].forEach(([freq, at]) => {
      const o = audio!.createOscillator(), g = audio!.createGain();
      o.type = 'sine'; o.frequency.value = freq;
      g.gain.setValueAtTime(0.0001, now + at);
      g.gain.exponentialRampToValueAtTime(0.25, now + at + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, now + at + 0.45);
      o.connect(g).connect(audio!.destination);
      o.start(now + at); o.stop(now + at + 0.5);
    });
  } catch { /* no audio */ }
}

const canDesktop = () => typeof window !== 'undefined' && 'Notification' in window;

export default function Bell() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const data = useQuery({ queryKey: ['notifications'], queryFn: () => api<Notifications>('/notifications'), refetchInterval: 30_000,
    refetchIntervalInBackground: true });
  const [prefs, setPrefs] = useState<Prefs>(loadPrefs);
  const [permission, setPermission] = useState(canDesktop() ? Notification.permission : 'denied');
  const lastSeen = useRef<number | null>(null);
  const setPref = (p: Prefs) => { setPrefs(p); savePrefs(p); };
  // Web Push: the browser shows notifications even when Verqac is closed
  const [pushOn, setPushOn] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { void currentSubscription().then((s) => setPushOn(!!s)).catch(() => undefined); }, []);
  // a push arrived while a tab is open: refresh now instead of waiting for the next poll
  useEffect(() => {
    if (!pushSupported()) return;
    const on = (e: MessageEvent) => { if (e.data?.type === 'verqac-push') void qc.invalidateQueries({ queryKey: ['notifications'] }); };
    navigator.serviceWorker.addEventListener('message', on);
    return () => navigator.serviceWorker.removeEventListener('message', on);
  }, [qc]);
  const toggleDesktop = async (on: boolean) => {
    setBusy(true);
    try {
      if (pushSupported()) {
        if (on) { setPermission(await enablePush()); setPushOn(!!(await currentSubscription())); }
        else { await disablePush(); setPushOn(false); }
      } else if (on && canDesktop() && Notification.permission !== 'granted') {
        setPermission(await Notification.requestPermission());
      }
      setPref({ ...prefs, desktop: on });
    } finally { setBusy(false); }
  };

  // new notifications since the last poll: sound + a system notification
  useEffect(() => {
    const items = data.data?.items;
    if (!items) return;
    const top = items.reduce((m, n) => Math.max(m, n.id), 0);
    if (lastSeen.current === null) { lastSeen.current = top; return; }  // first load: nothing is "new"
    const fresh = items.filter((n) => !n.read && n.id > (lastSeen.current ?? 0));
    lastSeen.current = Math.max(lastSeen.current, top);
    if (!fresh.length) return;
    qc.invalidateQueries({ queryKey: ['inbox'] });
    if (prefs.sound) chime();
    if (prefs.desktop && !pushOn && canDesktop() && Notification.permission === 'granted') {
      for (const n of fresh.slice(0, 3)) {
        const note = new Notification(pick(n, 'title'), { body: n.body ?? '', tag: `verqac-${n.id}`, icon: '/favicon.svg' });
        note.onclick = () => { window.focus(); note.close(); openItem(n); };
      }
    }
  }, [data.data]);  // eslint-disable-line react-hooks/exhaustive-deps

  // unread count in the tab title: "(2) Verqac"
  useEffect(() => {
    const base = document.title.replace(/^\(\d+\+?\) /, '');
    const n = data.data?.unread ?? 0;
    document.title = n ? `(${n > 99 ? '99+' : n}) ${base}` : base;
  }, [data.data?.unread]);

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
        <Divider />
        <Stack gap={6} p="sm">
          <Switch size="xs" label={t('bell.desktop')} checked={(pushOn || prefs.desktop) && permission === 'granted'}
            disabled={busy || !canDesktop() || permission === 'denied'}
            description={permission === 'denied' ? t('bell.blocked') : undefined}
            onChange={(e) => void toggleDesktop(e.currentTarget.checked)} />
          <Switch size="xs" label={t('bell.sound')} checked={prefs.sound}
            onChange={(e) => { setPref({ ...prefs, sound: e.currentTarget.checked }); if (e.currentTarget.checked) chime(); }} />
          <Text size="xs" c="dimmed">{t(pushOn ? 'bell.pushOn' : pushSupported() ? 'bell.pushHint' : 'bell.whileOpen')}</Text>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}
