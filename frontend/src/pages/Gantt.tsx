import { ActionIcon, Badge, Button, Checkbox, Group, ScrollArea, SegmentedControl, Text, TextInput, Tooltip } from '@mantine/core';
import { useMemo, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { CellStatus } from '../daily';
import { fmtDate } from '../format';
import { addDays, daysBetween } from '../programme';

/** One bar row: a stage on a floor (or a whole-project stage). */
export interface GanttItem {
  stageId: string; stageName: string; locId: string | null; locName: string | null; weight?: number;
  plan: { start: string; finish: string } | null;
  base: { start: string; finish: string } | null; // the baseline, when it differs
  actual: { start: string | null; finish: string | null; pct: number; status: CellStatus | 'late_start' | 'not_due' } | null;
}

const ZOOM = { week: 22, month: 5, quarter: 1.8 } as const;
type Zoom = keyof typeof ZOOM | 'fit';
const COL = { done: '#2f9e44', on_track: '#1c7ed6', ahead: '#1c7ed6', late: '#e03131', late_start: '#f76707', not_due: '#adb5bd', not_started: '#adb5bd' } as const;
const LABEL_W = 270, ROW = 24;

const today = () => new Date().toISOString().slice(0, 10);
const monthStarts = (from: string, to: string) => {
  const out: string[] = [];
  for (let d = `${from.slice(0, 7)}-01`; d <= to; d = `${addDays(d, 32).slice(0, 7)}-01`) out.push(d);
  return out;
};

/** Interactive Gantt: grouped by floor or by stage, zoom (week / month / quarter / fit), date range,
 * only behind, collapse, planned vs actual with status colours; follows the page direction. */
export default function Gantt({ items, showActual, toolbar }: { items: GanttItem[]; showActual: boolean; toolbar?: ReactNode }) {
  const { t, i18n } = useTranslation();
  const [by, setBy] = useState<'floor' | 'stage'>('floor');
  const [zoom, setZoom] = useState<Zoom>('month');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [onlyLate, setOnlyLate] = useState(false);
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  const box = useRef<HTMLDivElement>(null);
  const now = today();

  const shown = items.filter((x) => (x.plan || x.actual?.start) && (!onlyLate || ['late', 'late_start'].includes(x.actual?.status ?? '')));
  const dates = shown.flatMap((x) => [x.plan?.start, x.plan?.finish, x.base?.start, x.base?.finish, x.actual?.start, x.actual?.finish].filter(Boolean) as string[]);
  const lo = from || (dates.length ? addDays(dates.reduce((a, b) => (a < b ? a : b)), -7) : now);
  const hi = to || (dates.length ? addDays(dates.reduce((a, b) => (a > b ? a : b)), 14) : addDays(now, 30));
  const span = Math.max(1, daysBetween(lo, hi) + 1);
  const width = box.current?.clientWidth ?? 1100;
  const px = zoom === 'fit' ? Math.max(0.5, (width - LABEL_W - 20) / span) : ZOOM[zoom];
  const W = Math.ceil(span * px);
  const x = (d: string) => Math.min(Math.max(daysBetween(lo, d), 0), span) * px;
  const w = (s: string, f: string) => Math.max(2, x(addDays(f, 1)) - x(s));

  const groups = useMemo(() => {
    const m = new Map<string, { key: string; label: string; rows: GanttItem[] }>();
    for (const it of shown) {
      const key = by === 'floor' ? (it.locId ?? '_whole') : it.stageId;
      const label = by === 'floor' ? (it.locName ?? t('structure.whole')) : it.stageName;
      if (!m.has(key)) m.set(key, { key, label, rows: [] });
      m.get(key)!.rows.push(it);
    }
    const out = [...m.values()];
    if (by === 'floor') out.sort((a, b) => (a.key === '_whole' ? 1 : b.key === '_whole' ? -1 : 0));
    return out;
  }, [shown, by, t]);

  const bar = (it: GanttItem) => {
    const a = it.actual, p = it.plan;
    const tip = [
      `${it.stageName}${it.locName ? ' — ' + it.locName : ''}`,
      p && `${t('progress.planned')}: ${fmtDate(p.start)} → ${fmtDate(p.finish)}`,
      it.base && `${t('progress.baseline')}: ${fmtDate(it.base.start)} → ${fmtDate(it.base.finish)}`,
      a?.start && `${t('progress.actual')}: ${fmtDate(a.start)} → ${a.finish ? fmtDate(a.finish) : '…'} (${a.pct}%)`,
      a && t(`gantt.st.${a.status}`),
    ].filter(Boolean).join('\n');
    const aEnd = a?.start ? (a.finish ?? (a.pct > 0 ? (now > a.start ? now : a.start) : a.start)) : null;
    return (
      <Tooltip.Floating label={tip} multiline w={300} style={{ whiteSpace: 'pre-line' }}>
        <div style={{ position: 'relative', height: ROW, width: W }}>
          {p && <div style={{ position: 'absolute', insetInlineStart: x(p.start), width: w(p.start, p.finish), top: showActual ? 3 : 6, height: showActual ? 7 : 12,
            background: showActual ? '#ced4da' : 'var(--mantine-color-verqac-6)', borderRadius: 3, opacity: showActual ? 1 : 0.85 }} />}
          {it.base && <div style={{ position: 'absolute', insetInlineStart: x(it.base.start), width: w(it.base.start, it.base.finish), top: 2, height: showActual ? 9 : 14,
            border: '1px dashed #868e96', borderRadius: 3 }} />}
          {showActual && a?.start && aEnd && (
            <div style={{ position: 'absolute', insetInlineStart: x(a.start), width: w(a.start, aEnd), top: 12, height: 9, borderRadius: 3,
              background: `color-mix(in srgb, ${COL[a.status]} 45%, white)`, overflow: 'hidden' }}>
              <div style={{ width: `${Math.min(100, a.pct)}%`, height: '100%', background: COL[a.status] }} />
            </div>
          )}
          {showActual && a?.status === 'late_start' && p && (
            <div style={{ position: 'absolute', insetInlineStart: x(p.start), top: 12, width: 8, height: 9, background: COL.late_start, borderRadius: 2 }} />
          )}
        </div>
      </Tooltip.Floating>
    );
  };
  const summary = (rows: GanttItem[]) => {
    const ps = rows.map((r) => r.plan).filter(Boolean) as { start: string; finish: string }[];
    if (!ps.length) return <div style={{ height: ROW, width: W }} />;
    const s = ps.map((r) => r.start).reduce((a, b) => (a < b ? a : b)), f = ps.map((r) => r.finish).reduce((a, b) => (a > b ? a : b));
    return (
      <div style={{ position: 'relative', height: ROW, width: W }}>
        <div style={{ position: 'absolute', insetInlineStart: x(s), width: w(s, f), top: 9, height: 5, background: '#495057', borderRadius: 2 }} />
      </div>
    );
  };
  const avg = (rows: GanttItem[]) => rows.length ? Math.round(rows.reduce((n, r) => n + (r.actual?.pct ?? 0), 0) / rows.length) : 0;
  const months = monthStarts(lo, hi);
  const fmtM = (d: string) => new Date(`${d}T00:00:00Z`).toLocaleDateString(i18n.language === 'ar' ? 'ar-EG-u-nu-latn' : 'en-GB', { month: 'short', year: 'numeric', timeZone: 'UTC' });
  const weeks = zoom === 'week' ? Array.from({ length: Math.ceil(span / 7) }, (_, k) => addDays(lo, k * 7)) : [];
  const lines = (
    <>
      {months.map((m) => <div key={m} style={{ position: 'absolute', insetInlineStart: x(m), top: 0, bottom: 0, borderInlineStart: '1px solid #e9ecef' }} />)}
      {now >= lo && now <= hi && <div style={{ position: 'absolute', insetInlineStart: x(now), top: 0, bottom: 0, borderInlineStart: '2px dashed #e8590c', zIndex: 2 }} />}
    </>
  );
  const cell = { position: 'sticky' as const, insetInlineStart: 0, zIndex: 3, background: 'var(--mantine-color-body)', width: LABEL_W, minWidth: LABEL_W,
    borderInlineEnd: '1px solid #dee2e6', paddingInline: 8, display: 'flex', alignItems: 'center', gap: 6, height: ROW, overflow: 'hidden' };

  return (
    <div ref={box}>
      <Group gap="xs" mb="xs" wrap="wrap">
        {toolbar}
        <SegmentedControl size="xs" value={by} onChange={(v) => setBy(v as 'floor' | 'stage')}
          data={[{ value: 'floor', label: t('gantt.byFloor') }, { value: 'stage', label: t('gantt.byStage') }]} />
        <SegmentedControl size="xs" value={zoom} onChange={(v) => setZoom(v as Zoom)}
          data={(['week', 'month', 'quarter', 'fit'] as Zoom[]).map((z) => ({ value: z, label: t(`gantt.z.${z}`) }))} />
        <TextInput size="xs" type="date" w={140} value={from} onChange={(e) => setFrom(e.currentTarget.value)} aria-label={t('gantt.from')} leftSection={<Text size="xs">{t('gantt.from')}</Text>} leftSectionWidth={36} />
        <TextInput size="xs" type="date" w={140} value={to} onChange={(e) => setTo(e.currentTarget.value)} aria-label={t('gantt.to')} leftSection={<Text size="xs">{t('gantt.to')}</Text>} leftSectionWidth={36} />
        {showActual && <Checkbox size="xs" label={t('gantt.onlyLate')} checked={onlyLate} onChange={(e) => setOnlyLate(e.currentTarget.checked)} />}
        <Button size="compact-xs" variant="subtle" onClick={() => setClosed({})}>{t('gantt.expand')}</Button>
        <Button size="compact-xs" variant="subtle" onClick={() => setClosed(Object.fromEntries(groups.map((g) => [g.key, true])))}>{t('gantt.collapse')}</Button>
        <Button size="compact-xs" variant="subtle" onClick={() => window.print()}>{t('gantt.print')}</Button>
      </Group>
      {showActual && (
        <Group gap="md" mb={6}>
          <Group gap={4}><span style={{ width: 18, height: 6, background: '#ced4da', display: 'inline-block' }} /><Text size="xs">{t('progress.planned')}</Text></Group>
          <Group gap={4}><span style={{ width: 18, height: 8, border: '1px dashed #868e96', display: 'inline-block' }} /><Text size="xs">{t('progress.baseline')}</Text></Group>
          {(['done', 'on_track', 'late', 'late_start', 'not_due'] as const).map((k) => (
            <Group key={k} gap={4}><span style={{ width: 18, height: 8, background: COL[k], display: 'inline-block', borderRadius: 2 }} /><Text size="xs">{t(`gantt.st.${k}`)}</Text></Group>
          ))}
          <Text size="xs" c="dimmed">{t('gantt.darkPart')}</Text>
        </Group>
      )}
      <ScrollArea type="auto" offsetScrollbars style={{ border: '1px solid #dee2e6', borderRadius: 6 }}>
        <div style={{ width: LABEL_W + W, position: 'relative' }}>
          <div style={{ display: 'flex', position: 'sticky', top: 0, zIndex: 4, background: 'var(--mantine-color-gray-0)', borderBottom: '1px solid #dee2e6' }}>
            <div style={{ ...cell, background: 'var(--mantine-color-gray-0)', height: zoom === 'week' ? 40 : 26 }}>
              <Text size="xs" fw={600}>{by === 'floor' ? t('gantt.floorStage') : t('gantt.stageFloor')}</Text>
            </div>
            <div style={{ position: 'relative', width: W, height: zoom === 'week' ? 40 : 26 }}>
              {months.filter((m, k) => m >= lo || (k === 0 && (months[1] ? x(months[1]) > 70 : true))).map((m) => (
                <Text key={m} size="xs" fw={600} style={{ position: 'absolute', insetInlineStart: x(m) + 4, top: 5, whiteSpace: 'nowrap' }}>{fmtM(m)}</Text>
              ))}
              {weeks.map((d) => <Text key={d} size="10px" c="dimmed" style={{ position: 'absolute', insetInlineStart: x(d) + 2, top: 24 }}>{d.slice(8, 10)}</Text>)}
            </div>
          </div>
          {groups.length === 0 && <Text size="sm" c="dimmed" p="md">{t('gantt.empty')}</Text>}
          {groups.map((g) => (
            <div key={g.key}>
              <div style={{ display: 'flex', background: 'var(--mantine-color-gray-0)', position: 'relative' }}>
                <div style={{ ...cell, background: 'var(--mantine-color-gray-0)', cursor: 'pointer' }} onClick={() => setClosed({ ...closed, [g.key]: !closed[g.key] })}>
                  <ActionIcon size="xs" variant="subtle">{closed[g.key] ? '▸' : '▾'}</ActionIcon>
                  <Text size="xs" fw={700} style={{ flex: 1 }} truncate>{g.label}</Text>
                  {showActual && <Badge size="xs" variant="light">{avg(g.rows)}%</Badge>}
                </div>
                <div style={{ position: 'relative' }}>{lines}{summary(g.rows)}</div>
              </div>
              {!closed[g.key] && g.rows.map((it) => (
                <div key={`${it.stageId}${it.locId}`} style={{ display: 'flex', position: 'relative', borderTop: '1px solid #f1f3f5' }}>
                  <div style={{ ...cell, paddingInlineStart: 28 }}>
                    {showActual && <span style={{ width: 8, height: 8, borderRadius: 8, background: COL[it.actual?.status ?? 'not_due'], flex: 'none' }} />}
                    <Text size="xs" style={{ flex: 1 }} truncate>{by === 'floor' ? it.stageName : (it.locName ?? t('structure.whole'))}</Text>
                    {showActual && <Text size="xs" c="dimmed">{it.actual?.pct ?? 0}%</Text>}
                  </div>
                  <div style={{ position: 'relative' }}>{lines}{bar(it)}</div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
