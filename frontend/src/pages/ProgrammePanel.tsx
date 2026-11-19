import {
  ActionIcon, Alert, Badge, Button, Card, Checkbox, FileButton, Group, Modal, NumberInput, ScrollArea, Select, Stack, Table, Text,
  TextInput, Title, Tooltip,
} from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Fragment, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError, openProtected, type RecordDetail } from '../api';
import type { ProgressOut } from '../daily';
import { fmtDate } from '../format';
import i18n, { pick } from '../i18n';
import { addDays, cellKey, cellPlanned, cellStatus, cpm, daysBetween, schedule, type ImportRow, type Rel, type PCycle, type PLine, type ProgrammeOut } from '../programme';
import { useStructure } from './Structure';
import Gantt, { type GanttItem } from './Gantt';

const errText = (e: unknown) => i18n.t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, { defaultValue: i18n.t('errors.generic') });

/** Floor cycle: per stage a start, days per floor and days until the next floor starts. */
function CycleModal({ opened, onClose, cycles, onApply, stages, units, existing, storeKey }: {
  storeKey: string; opened: boolean; onClose: () => void; cycles: PCycle[]; onApply: (c: PCycle[]) => void;
  stages: { id: string; name: string; whole: boolean }[]; units: { id: string; name: string }[]; existing: PLine[];
}) {
  const unitCount = units.length;
  const { t } = useTranslation();
  const [rows, setRows] = useState<(PCycle & { on: boolean })[]>([]);
  useEffect(() => {
    if (!opened) return;
    let kept: PCycle[] | null = null;  // what was typed here last time, even if never generated
    try { kept = JSON.parse(localStorage.getItem(storeKey) ?? 'null'); } catch { kept = null; }
    const by = Object.fromEntries((kept ?? cycles).map((c) => [c.stage_id, c]));
    setRows(stages.map((s) => ({ stage_id: s.id, start: by[s.id]?.start ?? null, duration: by[s.id]?.duration ?? 0, lag: by[s.id]?.lag ?? 0,
      link: by[s.id]?.link ?? 'fs', pred: by[s.id]?.pred ?? null, rel: by[s.id]?.rel ?? 'after_end', pred_days: by[s.id]?.pred_days ?? 0, on: !!by[s.id] })));
  }, [opened, cycles, stages, storeKey]);
  const set = (i: number, p: Partial<PCycle & { on: boolean }>) => {
    const next = rows.map((r, j) => (j === i ? { ...r, ...p, on: p.on ?? true } : r));
    setRows(next);
    try { localStorage.setItem(storeKey, JSON.stringify(next.filter((r) => r.on).map(({ on: _on, ...c }) => c))); } catch { /* ignore */ }
  };
  const whole = useMemo(() => new Set(stages.filter((s) => s.whole).map((s) => s.id)), [stages]);
  const ok = rows.filter((r) => r.on && r.duration > 0 && (r.pred || r.start));
  const plan = useMemo(() => schedule(ok.map(({ on: _on, ...c }) => c), units.map((u) => u.id), whole, existing), [ok, units, whole, existing]);
  const byStage = useMemo(() => {
    const m = new Map<string, PLine[]>();
    for (const l of plan.lines) m.set(l.stage_id, [...(m.get(l.stage_id) ?? []), l]);
    return m;
  }, [plan]);
  const uname = Object.fromEntries(units.map((u) => [u.id, u.name]));
  const names = Object.fromEntries(stages.map((s) => [s.id, s.name]));
  const RELS: Rel[] = ['after_end', 'after_start', 'before_end', 'before_start'];
  return (
    <Modal opened={opened} onClose={onClose} title={t('prg.cycleTitle')} size="95%">
      <Alert variant="light" mb="sm" title={t('prg.cycleHowTitle')}>
        <Text size="sm" style={{ whiteSpace: 'pre-line' }}>{t('prg.cycleHow', { n: unitCount, first: units[0]?.name ?? '', second: units[1]?.name ?? '' })}</Text>
      </Alert>
      {plan.error && <Alert color="red" mb="sm">{t(`errors.${plan.error}`)}</Alert>}
      <ScrollArea>
        <Table verticalSpacing={4} fz="sm" miw={1050}>
          <Table.Thead><Table.Tr>
            <Table.Th w={30} /><Table.Th miw={150}>{t('structure.stage')}</Table.Th>
            <Table.Th w={330}>{t('prg.pred')}</Table.Th><Table.Th w={140}>{t('prg.start')}</Table.Th>
            <Table.Th w={100}>{t('prg.duration')}</Table.Th><Table.Th w={210}>{t('prg.lag')}</Table.Th><Table.Th w={130}>{t('prg.span2')}</Table.Th>
          </Table.Tr></Table.Thead>
          <Table.Tbody>
            {rows.map((r, i) => {
              const s = stages[i];
              const ls = byStage.get(r.stage_id) ?? [];
              const first = ls.length ? ls.map((l) => l.start).reduce((a, b) => (a < b ? a : b)) : null;
              const last = ls.length ? ls.map((l) => l.finish).reduce((a, b) => (a > b ? a : b)) : null;
              const linked = !!r.pred;
              return (
                <Table.Tr key={r.stage_id} opacity={r.on ? 1 : 0.6}>
                  <Table.Td><Checkbox checked={r.on} onChange={(e) => set(i, { on: e.currentTarget.checked })} /></Table.Td>
                  <Table.Td>{s.name} {s.whole && <Badge size="xs" variant="light">{t('structure.whole')}</Badge>}</Table.Td>
                  <Table.Td>
                    <Group gap={4} wrap="nowrap">
                      <Select size="xs" w={140} clearable placeholder={t('prg.noPred')} value={r.pred ?? null}
                        data={stages.filter((x) => x.id !== r.stage_id).map((x) => ({ value: x.id, label: x.name }))}
                        onChange={(v) => set(i, { pred: v })} />
                      {linked && <>
                        <Select size="xs" w={110} allowDeselect={false} value={r.rel ?? 'after_end'}
                          data={RELS.map((x) => ({ value: x, label: t(`prg.rel.${x}`) }))} onChange={(v) => set(i, { rel: (v ?? 'after_end') as Rel })} />
                        <NumberInput size="xs" w={72} min={0} value={r.pred_days ?? 0} suffix={` ${t('prg.days')}`} onChange={(v) => set(i, { pred_days: Number(v) || 0 })} />
                      </>}
                    </Group>
                  </Table.Td>
                  <Table.Td>{linked
                    ? <Text size="xs" c="dimmed">{first ? fmtDate(first) : t('prg.predMissing')}</Text>
                    : <TextInput size="xs" type="date" value={r.start ?? ''} onChange={(e) => set(i, { start: e.currentTarget.value || null })} />}</Table.Td>
                  <Table.Td><NumberInput size="xs" min={0} value={r.duration} suffix={` ${t('prg.days')}`} onChange={(v) => set(i, { duration: Number(v) || 0 })} /></Table.Td>
                  <Table.Td>{!s.whole && (
                    <Group gap={4} wrap="nowrap">
                      <NumberInput size="xs" w={70} min={0} value={r.lag} suffix={` ${t('prg.days')}`} onChange={(v) => set(i, { lag: Number(v) || 0 })} />
                      <Select size="xs" w={130} allowDeselect={false} value={r.link ?? 'fs'} onChange={(v) => set(i, { link: (v ?? 'fs') as 'fs' | 'ss' })}
                        data={[{ value: 'fs', label: t('prg.linkFs') }, { value: 'ss', label: t('prg.linkSs') }]} />
                    </Group>
                  )}</Table.Td>
                  <Table.Td>
                    {first && last ? (
                      <Tooltip multiline w={280} disabled={ls.length < 2} style={{ whiteSpace: 'pre-line' }}
                        label={ls.map((l) => `${uname[l.location_id ?? ''] ?? ''}: ${fmtDate(l.start)} → ${fmtDate(l.finish)}`).join('\n')}>
                        <Text size="xs" c="dimmed" style={{ cursor: 'help' }}>{fmtDate(first)} → {fmtDate(last)}</Text>
                      </Tooltip>
                    ) : ''}
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </ScrollArea>
      {plan.missing.length > 0 && <Text size="xs" c="orange" mt="xs">{t('prg.predMissingList', { list: plan.missing.map((x) => names[x]).join('، ') })}</Text>}
      <Group justify="flex-end" mt="md">
        <Text size="xs" c="dimmed">{t('prg.cycleReplace')}</Text>
        <Button disabled={!ok.length || !!plan.error} onClick={() => onApply(ok.map(({ on: _on, ...c }) => c))}>{t('prg.generate')}</Button>
      </Group>
    </Modal>
  );
}

/** Rows read from a file, with the stage and floor their names suggest; the engineer checks them before they count. */
function ImportModal({ rows, onClose, onApply, stageData, unitData, whole }: {
  rows: ImportRow[] | null; onClose: () => void; onApply: (lines: PLine[]) => void;
  stageData: { value: string; label: string }[]; unitData: { value: string; label: string }[]; whole: Set<string>;
}) {
  const { t } = useTranslation();
  const [list, setList] = useState<(ImportRow & { on: boolean })[]>([]);
  useEffect(() => { if (rows) setList(rows.filter((r) => r.start || r.finish).map((r) => ({ ...r, on: !!(r.stage_id && r.start && r.finish && (whole.has(r.stage_id) || r.location_id)) }))); }, [rows, whole]);
  const set = (i: number, p: Partial<ImportRow & { on: boolean }>) => setList(list.map((r, j) => {
    if (j !== i) return r;
    const n = { ...r, ...p };
    return { ...n, on: p.on ?? !!(n.stage_id && n.start && n.finish && (whole.has(n.stage_id) || n.location_id)) };
  }));
  const chosen = list.filter((r) => r.on && r.stage_id && r.start && r.finish && (whole.has(r.stage_id) || r.location_id));
  const apply = () => {
    const cells = new Map<string, PLine>();
    for (const r of chosen) {
      const loc = whole.has(r.stage_id!) ? null : r.location_id;
      const k = cellKey(r.stage_id!, loc);
      const o = cells.get(k);
      cells.set(k, { stage_id: r.stage_id!, location_id: loc, start: o && o.start < r.start! ? o.start : r.start!, finish: o && o.finish > r.finish! ? o.finish : r.finish! });
    }
    onApply([...cells.values()]);
  };
  return (
    <Modal opened={!!rows} onClose={onClose} title={t('prg.importTitle')} size="90%">
      <Text size="sm" c="dimmed" mb="sm">{t('prg.importHint', { all: list.length, ok: chosen.length })}</Text>
      <ScrollArea h={460}>
        <Table verticalSpacing={2} fz="xs" stickyHeader>
          <Table.Thead><Table.Tr>
            <Table.Th w={30} /><Table.Th>{t('prg.task')}</Table.Th><Table.Th w={95}>{t('prg.start')}</Table.Th><Table.Th w={95}>{t('prg.finish')}</Table.Th>
            <Table.Th w={210}>{t('structure.stage')}</Table.Th><Table.Th w={170}>{t('prg.location')}</Table.Th>
          </Table.Tr></Table.Thead>
          <Table.Tbody>
            {list.map((r, i) => (
              <Table.Tr key={i} opacity={r.on ? 1 : 0.5}>
                <Table.Td><Checkbox size="xs" checked={r.on} onChange={(e) => set(i, { on: e.currentTarget.checked })} /></Table.Td>
                <Table.Td>
                  <Text size="xs">{r.name}</Text>
                  {(r.path.length > 0 || r.location) && <Text size="xs" c="dimmed">{[...r.path, r.location].filter(Boolean).join(' › ')}</Text>}
                </Table.Td>
                <Table.Td dir="ltr">{r.start ?? '—'}</Table.Td><Table.Td dir="ltr">{r.finish ?? '—'}</Table.Td>
                <Table.Td><Select size="xs" data={stageData} value={r.stage_id} searchable clearable
                  onChange={(v) => set(i, { stage_id: v, location_id: v && whole.has(v) ? null : r.location_id })} /></Table.Td>
                <Table.Td>{r.stage_id && whole.has(r.stage_id)
                  ? <Text size="xs" c="dimmed">{t('structure.whole')}</Text>
                  : <Select size="xs" data={unitData} value={r.location_id} searchable clearable onChange={(v) => set(i, { location_id: v })} />}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea>
      <Group justify="flex-end" mt="md">
        <Text size="xs" c="dimmed">{t('prg.importReplace')}</Text>
        <Button disabled={!chosen.length} onClick={apply}>{t('prg.importApply', { n: chosen.length })}</Button>
      </Group>
    </Modal>
  );
}

/** The programme of a programme record: floor cycle, dates by hand or imported, a bar chart; supervision approves it. */
export default function ProgrammePanel({ rec }: { rec: RecordDetail }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['programme', rec.id], queryFn: () => api<ProgrammeOut>(`/records/${rec.id}/programme`) });
  const s = useStructure(rec.project_id).data;
  // the actual progress (approved daily reports), to compare this programme with the site while it is drafted
  const prog = useQuery({ queryKey: ['progress', rec.project_id], queryFn: () => api<ProgressOut>(`/projects/${rec.project_id}/progress`) });
  const [lines, setLines] = useState<PLine[]>([]);
  const [cycles, setCycles] = useState<PCycle[]>([]);
  const [source, setSource] = useState<ProgrammeOut['source']>('manual');
  const [dirty, setDirty] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [cycleOpen, setCycleOpen] = useState(false);
  const [shiftTo, setShiftTo] = useState<string | null>(null);
  const [rows, setRows] = useState<ImportRow[] | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  useEffect(() => { if (q.data) { setLines(q.data.lines); setCycles(q.data.cycles); setSource(q.data.source); setDirty(false); } }, [q.data]);
  // unsaved work is kept in this browser until it is saved, and leaving the page asks first
  const draftKey = `verqac:prg-draft:${rec.id}`;
  const [draft, setDraft] = useState<{ lines: PLine[]; cycles: PCycle[]; source: ProgrammeOut['source']; at: string } | null>(null);
  useEffect(() => {
    try { const raw = localStorage.getItem(draftKey); setDraft(raw ? JSON.parse(raw) : null); } catch { setDraft(null); }
  }, [draftKey]);
  useEffect(() => {
    if (!dirty) return;
    try { localStorage.setItem(draftKey, JSON.stringify({ lines, cycles, source, at: new Date().toISOString() })); } catch { /* storage full or blocked */ }
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty, lines, cycles, source, draftKey]);
  const dropDraft = () => { try { localStorage.removeItem(draftKey); } catch { /* ignore */ } setDraft(null); };
  const stages = useMemo(() => (s?.stages ?? []).filter((x) => x.is_active && x.id), [s]);
  const units = useMemo(() => (s?.locations ?? []).filter((g) => g.is_active).flatMap((g) => g.units.filter((u) => u.is_active && u.id)), [s]);
  const whole = useMemo(() => new Set(stages.filter((x) => x.scope === 'whole' || !units.length).map((x) => x.id!)), [stages, units]);
  const byKey = useMemo(() => new Map(lines.map((l) => [cellKey(l.stage_id, l.location_id), l])), [lines]);
  const save = useMutation({
    mutationFn: () => {
      // cells of stages or floors removed from the structure since are dropped (they would count nowhere)
      const sids = new Set(stages.map((x) => x.id!)), uids = new Set(units.map((u) => u.id!));
      const kept = lines.filter((l) => sids.has(l.stage_id) && (whole.has(l.stage_id) || (l.location_id && uids.has(l.location_id))))
        .map((l) => (whole.has(l.stage_id) ? { ...l, location_id: null } : l));
      const cs = cycles.filter((c) => sids.has(c.stage_id)).map((c) => ({ ...c, pred: c.pred && sids.has(c.pred) ? c.pred : null }));
      return api<ProgrammeOut>(`/records/${rec.id}/programme`, { method: 'PUT', body: JSON.stringify({ lines: kept, cycles: cs, source }) });
    },
    onSuccess: (d) => { qc.setQueryData(['programme', rec.id], d); dropDraft(); try { localStorage.removeItem(`verqac:prg-cycle:${rec.id}`); } catch { /* ignore */ } setMsg({ ok: true, text: t('settings.saved') }); },
    onError: (e) => setMsg({ ok: false, text: errText(e) }),
  });
  const upload = useMutation({
    mutationFn: (f: File) => { const fd = new FormData(); fd.append('file', f); return api<ImportRow[]>(`/records/${rec.id}/programme/import`, { method: 'POST', body: fd }); },
    onSuccess: setRows, onError: (e) => setMsg({ ok: false, text: errText(e) }),
  });
  if (!q.data || !s) return null;
  const edit = q.data.can_edit;
  const change = (next: PLine[], src: ProgrammeOut['source'] = source) => { setLines(next); setSource(src); setDirty(true); setMsg(null); };
  const setCell = (stage: string, loc: string | null, p: Partial<PLine>) => {
    const k = cellKey(stage, loc);
    const old = byKey.get(k);
    const n = { stage_id: stage, location_id: loc, start: old?.start ?? '', finish: old?.finish ?? '', ...p };
    const rest = lines.filter((l) => cellKey(l.stage_id, l.location_id) !== k);
    change(n.start || n.finish ? [...rest, { ...n, finish: n.finish || n.start, start: n.start || n.finish }] : rest, 'manual');
  };
  const generate = (cs: PCycle[]) => {
    const ids = new Set(cs.map((c) => c.stage_id));
    const gen = schedule(cs, units.map((u) => u.id!), whole, lines).lines;
    setCycles([...cycles.filter((c) => !ids.has(c.stage_id)), ...cs]);
    change([...lines.filter((l) => !ids.has(l.stage_id)), ...gen], 'cycle');
    setCycleOpen(false);
  };
  const imported = (ls: PLine[]) => {
    const keys = new Set(ls.map((l) => cellKey(l.stage_id, l.location_id)));
    change([...lines.filter((l) => !keys.has(cellKey(l.stage_id, l.location_id))), ...ls], 'import');
    setRows(null);
  };
  const stageSpan = (sid: string) => {
    const ls = lines.filter((l) => l.stage_id === sid && l.start && l.finish);
    return ls.length ? { start: ls.reduce((m, l) => (l.start < m ? l.start : m), ls[0].start), finish: ls.reduce((m, l) => (l.finish > m ? l.finish : m), ls[0].finish), n: ls.length } : null;
  };
  const spans = stages.map((st) => ({ st, sp: stageSpan(st.id!) }));
  const bars = spans.filter((x) => x.sp).map(({ st, sp }) => ({ label: pick(st, 'name'), start: sp!.start, finish: sp!.finish }));
  const from = bars.length ? bars.reduce((m, b) => (b.start < m ? b.start : m), bars[0].start) : null;
  const to = bars.length ? bars.reduce((m, b) => (b.finish > m ? b.finish : m), bars[0].finish) : null;
  const floats = cpm(lines, cycles, units.map((u) => u.id!), whole);
  const today = new Date().toISOString().slice(0, 10);
  const done = new Map((prog.data?.cells ?? []).map((c) => [cellKey(c.stage_id, c.location_id), c]));
  const hasActual = (prog.data?.cells ?? []).some((c) => c.progress > 0 || c.started_on);
  const gItems: GanttItem[] = stages.flatMap((st) => (whole.has(st.id!) ? [null] : units.map((u) => u.id!)).map((loc) => {
    const k = cellKey(st.id!, loc);
    const l = byKey.get(k);
    const a = done.get(k);
    const started = !!a && (a.progress > 0 || !!a.started_on);
    const planned = l?.start && l.finish ? cellPlanned(l.start, l.finish, today) : 0;
    const status: NonNullable<GanttItem['actual']>['status'] = started ? cellStatus(planned, a!.progress)
      : l?.start && l.start <= today ? 'late_start' : 'not_due';
    return { stageId: st.id!, stageName: pick(st, 'name'), locId: loc, locName: loc ? pick(units.find((u) => u.id === loc)!, 'name') : null,
      plan: l?.start && l.finish ? { start: l.start, finish: l.finish } : null, base: null,
      actual: hasActual ? { start: a?.started_on ?? null, finish: a?.finished_on ?? null, pct: a?.progress ?? 0, status } : null,
      float: cycles.length ? floats.get(k) ?? null : null,
      unlinked: !cycles.find((c) => c.stage_id === st.id && c.pred) };
  }));
  // how a stage was generated: its link to an earlier stage, days per floor and the stop between floors
  const linkText = (sid: string) => {
    const c = cycles.find((x) => x.stage_id === sid);
    if (!c) return <Text size="xs" c="dimmed">{t('prg.byHand')}</Text>;
    const pred = c.pred ? stages.find((x) => x.id === c.pred) : null;
    const parts = [
      pred ? t('prg.linkTxt', { rel: t(`prg.rel.${c.rel ?? 'after_end'}`), stage: pick(pred, 'name'), n: c.pred_days ?? 0 }) : c.start ? t('prg.startTxt', { d: fmtDate(c.start) }) : null,
      c.duration ? t('prg.durTxt', { n: c.duration }) : null,
      !whole.has(sid) ? ((c.link ?? 'fs') === 'fs' ? t('prg.gapTxt', { n: c.lag }) : t('prg.ssTxt', { n: c.lag })) : null,
    ].filter(Boolean);
    return <Text size="xs" c={pred ? 'blue' : undefined}>{parts.join(' · ')}</Text>;
  };
  const dateIn = (stage: string, loc: string | null, f: 'start' | 'finish') => (
    <TextInput size="xs" type="date" w={140} disabled={!edit} value={byKey.get(cellKey(stage, loc))?.[f] ?? ''}
      onChange={(e) => setCell(stage, loc, { [f]: e.currentTarget.value })} />
  );
  const dur = (stage: string, loc: string | null) => {
    const l = byKey.get(cellKey(stage, loc));
    return l?.start && l.finish ? `${daysBetween(l.start, l.finish) + 1} ${t('prg.days')}` : '';
  };
  return (
    <Stack>
      <Group justify="space-between" align="flex-start">
        <div>
          <Title order={5}>{t('prg.title')}</Title>
          <Text size="sm" c="dimmed">
            {from && to ? t('prg.span', { from: fmtDate(from), to: fmtDate(to), days: daysBetween(from, to) + 1 }) : t('prg.empty')}
            {' · '}{t(`prg.source.${source}`)}
          </Text>
        </div>
        <Group gap="xs">
          {q.data.lines.length > 0 && (
            <Button size="xs" variant="light" color="green" onClick={() => openProtected(`/records/${rec.id}/programme/xlsx?lang=${i18n.language}`, `${rec.number}-R${rec.rev_no}.xlsx`)}>
              {t('prg.exportXlsx')}
            </Button>
          )}
          <Button size="xs" variant="subtle" onClick={() => openProtected(`/projects/${rec.project_id}/programme/template?lang=${i18n.language}`, 'programme-template.xlsx')}>
            {t('prg.template')}
          </Button>
          {edit && <>
            <FileButton accept=".xlsx,.xlsm,.csv,.xml,.xer" onChange={(f) => f && upload.mutate(f)}>
              {(props) => <Button size="xs" variant="light" loading={upload.isPending} {...props}>{t('prg.import')}</Button>}
            </FileButton>
            <Button size="xs" variant="light" onClick={() => setCycleOpen(true)}>{t('prg.cycle')}</Button>
            {from && <Button size="xs" variant="light" onClick={() => setShiftTo(from)}>{t('prg.shift')}</Button>}
            {(lines.length > 0 || cycles.length > 0) && (
              <Button size="xs" variant="subtle" color="red" onClick={() => {
                if (!window.confirm(t('prg.clearConfirm'))) return;
                try { localStorage.removeItem(`verqac:prg-cycle:${rec.id}`); } catch { /* ignore */ }
                setCycles([]); change([], 'manual');
              }}>{t('prg.clear')}</Button>
            )}
            {dirty && <Button size="xs" variant="subtle" color="gray" onClick={() => { setLines(q.data!.lines); setCycles(q.data!.cycles); setSource(q.data!.source); setDirty(false); setMsg(null); dropDraft(); }}>{t('prg.undo')}</Button>}
            <Button size="xs" disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>{t('rec.save')}</Button>
          </>}
        </Group>
      </Group>
      {edit && <Text size="xs" c="dimmed">{t('prg.formats')}</Text>}
      {msg && <Alert color={msg.ok ? 'green' : 'red'} withCloseButton onClose={() => setMsg(null)}>{msg.text}</Alert>}
      {edit && draft && !dirty && (
        <Alert color="orange" title={t('prg.draftTitle')}>
          <Text size="sm">{t('prg.draftHint', { at: new Date(draft.at).toLocaleString(i18n.language === 'ar' ? 'ar-EG' : 'en-GB') })}</Text>
          <Group mt="xs" gap="xs">
            <Button size="xs" onClick={() => { setLines(draft.lines); setCycles(draft.cycles); setSource(draft.source); setDirty(true); setDraft(null); }}>{t('prg.draftRestore')}</Button>
            <Button size="xs" variant="subtle" color="gray" onClick={dropDraft}>{t('prg.draftDrop')}</Button>
          </Group>
        </Alert>
      )}
      {from && to && <Card withBorder p="xs"><Gantt items={gItems} showActual={hasActual} /></Card>}
      <Card withBorder p={0}>
        <Table verticalSpacing={4} fz="sm">
          <Table.Thead><Table.Tr>
            <Table.Th>{t('structure.stage')}</Table.Th><Table.Th w={150}>{t('prg.start')}</Table.Th><Table.Th w={150}>{t('prg.finish')}</Table.Th>
            <Table.Th w={90}>{t('prg.duration')}</Table.Th><Table.Th>{t('prg.linkCol')}</Table.Th>
          </Table.Tr></Table.Thead>
          <Table.Tbody>
            {spans.map(({ st, sp }) => {
              const sid = st.id!;
              if (whole.has(sid)) return (
                <Table.Tr key={sid}>
                  <Table.Td fw={600}>{pick(st, 'name')} <Badge size="xs" variant="light">{t('structure.whole')}</Badge></Table.Td>
                  <Table.Td>{dateIn(sid, null, 'start')}</Table.Td><Table.Td>{dateIn(sid, null, 'finish')}</Table.Td>
                  <Table.Td><Text size="xs" c="dimmed">{dur(sid, null)}</Text></Table.Td>
                  <Table.Td>{linkText(sid)}</Table.Td>
                </Table.Tr>
              );
              return (
                <Fragment key={sid}>
                  <Table.Tr style={{ cursor: 'pointer' }} onClick={() => setOpen({ ...open, [sid]: !open[sid] })}>
                    <Table.Td fw={600}>
                      <ActionIcon size="xs" variant="subtle" me={4}>{open[sid] ? '▾' : '▸'}</ActionIcon>
                      {pick(st, 'name')} <Text span size="xs" c="dimmed">({sp?.n ?? 0}/{units.length})</Text>
                    </Table.Td>
                    <Table.Td><Text size="xs">{sp ? fmtDate(sp.start) : '—'}</Text></Table.Td>
                    <Table.Td><Text size="xs">{sp ? fmtDate(sp.finish) : '—'}</Text></Table.Td>
                    <Table.Td><Text size="xs" c="dimmed">{sp ? `${daysBetween(sp.start, sp.finish) + 1} ${t('prg.days')}` : ''}</Text></Table.Td>
                    <Table.Td>{linkText(sid)}</Table.Td>
                  </Table.Tr>
                  {open[sid] && units.map((u) => (
                    <Table.Tr key={`${sid}${u.id}`} bg="var(--mantine-color-gray-0)">
                      <Table.Td ps={36}><Text size="xs">{pick(u, 'name')}</Text></Table.Td>
                      <Table.Td>{dateIn(sid, u.id!, 'start')}</Table.Td><Table.Td>{dateIn(sid, u.id!, 'finish')}</Table.Td>
                      <Table.Td><Text size="xs" c="dimmed">{dur(sid, u.id!)}</Text></Table.Td>
                      <Table.Td />
                    </Table.Tr>
                  ))}
                </Fragment>
              );
            })}
          </Table.Tbody>
        </Table>
      </Card>
      {edit && dirty && <Tooltip label={t('prg.unsaved')}><Button onClick={() => save.mutate()} loading={save.isPending}>{t('rec.save')}</Button></Tooltip>}
      <Modal opened={shiftTo !== null} onClose={() => setShiftTo(null)} title={t('prg.shiftTitle')}>
        {from && shiftTo !== null && (
          <Stack>
            <Text size="sm" c="dimmed">{t('prg.shiftHint', { from: fmtDate(from) })}</Text>
            <TextInput type="date" label={t('prg.shiftNew')} value={shiftTo} onChange={(e) => setShiftTo(e.currentTarget.value)} />
            {shiftTo && <Text size="sm">{t('prg.shiftBy', { n: daysBetween(from, shiftTo) })}</Text>}
            <Button disabled={!shiftTo || shiftTo === from} onClick={() => {
              const n = daysBetween(from, shiftTo);
              const moved = cycles.map((c) => (c.start ? { ...c, start: addDays(c.start, n) } : c));
              setCycles(moved);
              try { localStorage.setItem(`verqac:prg-cycle:${rec.id}`, JSON.stringify(moved)); } catch { /* ignore */ }
              change(lines.map((l) => ({ ...l, start: addDays(l.start, n), finish: addDays(l.finish, n) })));
              setShiftTo(null);
            }}>{t('prg.shiftApply')}</Button>
          </Stack>
        )}
      </Modal>
      <CycleModal storeKey={`verqac:prg-cycle:${rec.id}`} opened={cycleOpen} onClose={() => setCycleOpen(false)} cycles={cycles} onApply={generate} existing={lines}
        units={units.map((u) => ({ id: u.id!, name: pick(u, 'name') }))}
        stages={stages.map((x) => ({ id: x.id!, name: pick(x, 'name'), whole: whole.has(x.id!) }))} />
      <ImportModal rows={rows} onClose={() => setRows(null)} onApply={imported} whole={whole}
        stageData={stages.map((x) => ({ value: x.id!, label: pick(x, 'name') }))} unitData={units.map((u) => ({ value: u.id!, label: pick(u, 'name') }))} />
    </Stack>
  );
}
