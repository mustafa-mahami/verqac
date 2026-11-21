import {
  ActionIcon, Alert, Badge, Button, Card, Checkbox, FileInput, Group, Modal, MultiSelect, Select, SimpleGrid, Stack, Switch, Table, Text, Textarea,
  TextInput, UnstyledButton,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { saveNav } from '../recordNav';
import { api, ApiError, type LinkedRef, type Place, type RecordDetail, type RecordMeta, type RecordRow, type User } from '../api';
import { fmtDate, requiredColor, stateColor } from '../format';
import { pick } from '../i18n';
import { PlacePicker, placeText, rowTitle, useStructure } from './Structure';
import { shrinkPhoto } from './Photos';
import { linesFromTemplate, saveLab, type ConcreteClass, type LabTemplate } from '../lab';
import RecordStats, { applyFilter, CATEGORIES, type StatsFilter } from './RecordStats';

import { CustomInput, fieldLabel, LTR_KEYS, profile, typeText, type RegisterType } from '../recordTypes';

export type { RegisterType };

/** Approved submittals an inspection can rely on (shown when the project links them). */
function LinkPicker({ projectId, stageId, value, onChange }: {
  projectId: string; stageId: string | null; value: string[]; onChange: (v: string[]) => void;
}) {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ['linkCandidates', projectId, stageId],
    queryFn: () => api<LinkedRef[]>(`/projects/${projectId}/link-candidates${stageId ? `?stage_id=${stageId}` : ''}`),
  });
  const rows = q.data ?? [];
  const approved = (x: LinkedRef) => ['approved', 'approved_as_noted'].includes(x.state.category);
  const inStage = rows.filter((x) => !stageId || x.stage_id === stageId);
  const chosen = rows.filter((x) => value.includes(x.id));
  return (
    <Stack gap={4}>
      <MultiSelect label={t('ir.linked')} description={t('ir.linkedHint')} searchable clearable value={value} onChange={onChange}
        data={rows.map((x) => ({ value: x.id, label: `${x.number} R${x.rev_no} · ${x.title} — ${pick(x.state, 'name')}${approved(x) ? ' ✓' : ''}` }))} />
      {q.isSuccess && stageId && !inStage.some(approved) && <Alert color="orange" variant="light" py={6}>{t('ir.noApprovedInStage')}</Alert>}
      {chosen.some((x) => !approved(x)) && <Alert color="orange" variant="light" py={6}>{t('ir.linkNotApproved')}</Alert>}
    </Stack>
  );
}

/** A daily report is created for a date; the previous report's crew, equipment and plan come with it. */
function NewDaily({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  const [day, setDay] = useState(today);
  const [copy, setCopy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true); setError(null);
    try {
      const r = await api<{ id: string }>(`/projects/${projectId}/daily-reports`, { method: 'POST', body: JSON.stringify({ report_date: day, copy_previous: copy }) });
      navigate(`/records/${r.id}`);
    } catch (e) {
      setError(t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic')));
    } finally { setBusy(false); }
  };
  return (
    <Stack>
      {error && <Alert color="red">{error}</Alert>}
      <TextInput type="date" label={t('daily.date')} max={today} value={day} onChange={(e) => setDay(e.currentTarget.value)} />
      <Switch label={t('daily.copy')} description={t('daily.copyHint')} checked={copy} onChange={(e) => setCopy(e.currentTarget.checked)} />
      <Group justify="flex-end">
        <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
        <Button loading={busy} disabled={!day} onClick={go}>{t('rec.create')}</Button>
      </Group>
    </Stack>
  );
}

function NewSubmittal({ projectId, meta, onClose, type }: { projectId: string; meta: RecordMeta; onClose: () => void; type: RegisterType }) {
  const pf = profile(type);
  const isIR = pf.timed;
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [custom, setCustom] = useState<Record<string, string>>({});
  const isTest = type === 'test';
  const [tplId, setTplId] = useState<string | null>(null);
  const [classId, setClassId] = useState<string | null>(null);
  const templates = useQuery({ queryKey: ['labTemplates', projectId], enabled: isTest, queryFn: () => api<LabTemplate[]>(`/projects/${projectId}/lab-templates`) });
  const classes = useQuery({ queryKey: ['concreteClasses', projectId], enabled: isTest, queryFn: () => api<ConcreteClass[]>(`/projects/${projectId}/concrete-classes`) });
  const tpl = templates.data?.find((x) => x.id === tplId);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const structure = useStructure(projectId);
  const [place, setPlace] = useState<Place>({ stage_id: null, topic_id: null, all_locations: false, location_ids: [] });
  const kinds = meta.submittal_kinds.map((k) => ({ value: k.code ?? '', label: pick(k, 'name') }));
  const form = useForm({
    initialValues: {
      title: '', discipline_id: pf.place === false ? '' : meta.disciplines[0]?.id ?? '', description: '', number: '', submittal_kind: kinds[0]?.value ?? '',
      item: '', manufacturer: '', supplier: '', drawing_ref: '', spec_ref: '', boq_ref: '', quantity: '', unit: '',
      required_by: '', required_by_note: '', files: [] as File[], requested_for: '', linked: [] as string[], addressed_to: '',
    },
  });

  const choose = meta.routing === 'choose';
  const addressees = useQuery({
    queryKey: ['addressees', projectId, type, form.values.discipline_id], enabled: choose,
    queryFn: () => api<User[]>(`/projects/${projectId}/addressees?type=${type}${form.values.discipline_id ? `&discipline_id=${form.values.discipline_id}` : ''}`),
  });
  useEffect(() => {
    const ids = addressees.data?.map((u) => u.id) ?? [];
    if (ids.length && !ids.includes(form.values.addressed_to)) form.setFieldValue('addressed_to', ids[0]);
  }, [addressees.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = form.onSubmit(async (v) => {
    setError(null);
    setBusy(true);
    const blank = (x: string) => (x.trim() === '' ? null : x.trim());
    try {
      const rec = await api<RecordDetail>(`/projects/${projectId}/records`, {
        method: 'POST',
        body: JSON.stringify({
          record_type: type, title: place.topic_id ? null : v.title.trim(), description: blank(v.description),
          requested_for: isIR && v.requested_for ? new Date(v.requested_for).toISOString() : null,
          linked_ids: isIR ? v.linked : [],
          addressed_to: choose ? v.addressed_to || null : null,
          discipline_id: v.discipline_id || null, number: blank(v.number),
          ...place,
          required_by: pf.requiredBy && v.required_by ? v.required_by : null,
          required_by_note: pf.requiredBy && v.required_by ? blank(v.required_by_note) : null,
          details: {
            ...Object.fromEntries(pf.keys.map((k) => [k, blank(v[k])])),
            ...(pf.kind ? { submittal_kind: v.submittal_kind || null } : {}),
          },
          custom: Object.fromEntries(pf.custom.filter((f) => !f.response).map((f) => [f.key, blank(custom[f.key] ?? '')])),
        }),
      });
      if (isTest && tpl) {
        const k = classes.data?.find((x) => x.id === classId);
        await saveLab(rec.id, { template_id: tpl.id, material: tpl.material, acceptance: tpl.acceptance, specification: tpl.standard,
          class_id: tpl.acceptance === 'concrete' ? classId : null,
          // concrete: the specimen lines come from the lab report (AI) - or are generated by hand on the test
          lines: linesFromTemplate(tpl, { specimens: 0, fck: k?.fck ?? null }) });
      }
      for (const f of v.files) {
        const fd = new FormData();
        fd.append('file', await shrinkPhoto(f));
        fd.append('kind', 'submission');
        await api(`/records/${rec.id}/attachments`, { method: 'POST', body: fd });
      }
      navigate(`/records/${rec.id}`);
    } catch (e) {
      setError(t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, t('errors.generic')));
    } finally {
      setBusy(false);
    }
  });

  return (
    <form onSubmit={submit}>
      <Stack>
        {error && <Alert color="red">{error}</Alert>}
        {structure.data && pf.place !== false
          ? <PlacePicker structure={structure.data} value={place} onChange={setPlace}
              title={form.values.title} onTitle={(x) => form.setFieldValue('title', x)} />
          : <TextInput label={t('rec.title')} required {...form.getInputProps('title')} />}
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
{pf.place !== false && (
          <Select label={t('rec.discipline')} allowDeselect={false}
            data={meta.disciplines.map((d) => ({ value: d.id, label: pick(d, 'name') }))} {...form.getInputProps('discipline_id')} />
)}
          {isIR && <TextInput type="datetime-local" label={t('ir.requestedFor')} description={t('ir.requestedForHint')} {...form.getInputProps('requested_for')} />}
          {pf.kind && <Select label={t('rec.f.submittal_kind')} data={kinds} allowDeselect={false} searchable {...form.getInputProps('submittal_kind')} />}
          <TextInput label={t('rec.number')} placeholder={t('rec.numberHint')} dir="ltr" {...form.getInputProps('number')} />
        </SimpleGrid>
        {isTest && (
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <Select label={t('lab.template')} searchable value={tplId} style={{ gridColumn: tpl?.acceptance === 'concrete' ? undefined : 'span 3' }}
              data={(templates.data ?? []).map((x) => ({ value: x.id!, label: pick(x, 'name') }))} onChange={setTplId} />
            {tpl?.acceptance === 'concrete' && (
              <Select label={t('lab.class')} clearable value={classId} style={{ gridColumn: 'span 2' }}
                description={(classes.data ?? []).length ? t('lab.classHint') : t('lab.noClasses')}
                data={(classes.data ?? []).filter((k) => k.is_active).map((k) => ({ value: k.id!, label: `${k.grade} · ${Number(k.fck)} MPa` }))} onChange={setClassId} />
            )}
          </SimpleGrid>
        )}
        {choose && (
          <Select label={t('rec.addressedTo')} description={t('rec.addressedToHint')} allowDeselect={false} required
            data={(addressees.data ?? []).map((u) => ({ value: u.id, label: pick(u, 'full_name') }))} {...form.getInputProps('addressed_to')} />
        )}
        {isIR && meta.link_submittals && (
          <LinkPicker projectId={projectId} stageId={place.stage_id} value={form.values.linked} onChange={(v) => form.setFieldValue('linked', v)} />
        )}
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          {pf.keys.map((k) => (
            <TextInput key={k} label={fieldLabel(type, k)} dir={LTR_KEYS.has(k) ? 'ltr' : undefined} {...form.getInputProps(k)} />
          ))}
          {pf.custom.filter((f) => !f.response).map((f) => (
            <CustomInput key={f.key} code={type} f={f} value={custom[f.key] ?? ''} onChange={(x) => setCustom({ ...custom, [f.key]: x })} />
          ))}
        </SimpleGrid>
        <Textarea label={typeText(type, 'description', 'rec.description')} autosize minRows={2} {...form.getInputProps('description')} />
        {pf.requiredBy && <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <TextInput type="date" label={typeText(type, 'requiredBy', 'rec.requiredBy')} description={typeText(type, 'requiredByHint', 'rec.requiredByHint')} {...form.getInputProps('required_by')} />
          <TextInput style={{ gridColumn: 'span 2' }} label={t('rec.requiredByNote')} disabled={!form.values.required_by}
            description="&nbsp;" maxLength={300} {...form.getInputProps('required_by_note')} />
        </SimpleGrid>}
        <FileInput label={t('rec.files')} description={t('rec.filesHint')} multiple clearable {...form.getInputProps('files')} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="submit" loading={busy}>{t('rec.create')}</Button>
        </Group>
      </Stack>
    </form>
  );
}

type SortKey = 'number' | 'title' | 'discipline' | 'state' | 'submitted' | 'due' | 'answered';
const CAT_ORDER = Object.fromEntries(CATEGORIES.map(([c], i) => [c, i]));
const collator = new Intl.Collator(['ar', 'en'], { numeric: true, sensitivity: 'base' });

/** Value a column sorts by; empty dates sort last in either direction. */
function sortValue(r: RecordRow, key: SortKey): string | number | null {
  switch (key) {
    case 'number': return `${r.number}#${String(r.rev_no).padStart(3, '0')}`;
    case 'title': return r.title;
    case 'discipline': return r.discipline ? pick(r.discipline, 'name') : null;
    case 'state': return CAT_ORDER[r.state.category] ?? 99;
    case 'submitted': return r.submitted_at;
    case 'due': return r.due_at;
    case 'answered': return r.answered_at;
  }
}

function sortRows(rows: RecordRow[], key: SortKey, dir: 'asc' | 'desc'): RecordRow[] {
  const sign = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = sortValue(a, key), y = sortValue(b, key);
    if (x === y) return key === 'number' ? 0 : sign * collator.compare(a.number, b.number);
    if (x === null) return 1; // no value (a draft not submitted yet) at the end, either way
    if (y === null) return -1;
    return sign * (typeof x === 'number' && typeof y === 'number' ? x - y : collator.compare(String(x), String(y)));
  });
}

function SortTh({ label, k, sort, dir, onSort }: {
  label: string; k: SortKey; sort: SortKey; dir: 'asc' | 'desc'; onSort: (k: SortKey) => void;
}) {
  const active = sort === k;
  return (
    <Table.Th>
      <UnstyledButton onClick={() => onSort(k)} aria-sort={active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontWeight: 600, fontSize: 'inherit', whiteSpace: 'nowrap' }}>
        {label}
        <Text span size="xs" c={active ? 'verqac.7' : 'gray.4'}>{active ? (dir === 'asc' ? '▲' : '▼') : '⇅'}</Text>
      </UnstyledButton>
    </Table.Th>
  );
}

const PAGE = 80;

export default function Submittals({ projectId, type = 'submittal' }: { projectId: string; type?: RegisterType }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [allRevs, setAllRevs] = useState(false);
  const [open, setOpen] = useState(false);
  const meta = useQuery({ queryKey: ['recMeta', projectId, type], queryFn: () => api<RecordMeta>(`/projects/${projectId}/records/meta?type=${type}`) });
  const rows = useQuery({
    queryKey: ['records', projectId, type, allRevs],
    queryFn: () => api<RecordRow[]>(`/projects/${projectId}/records?type=${type}&all_revisions=${allRevs}`),
  });
  // the dashboard filter lives in the URL, so "back" from a record returns to the same view
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const structure = useStructure(projectId);
  const filter: StatsFilter = {
    status: params.get('st') ?? 'all', discipline: params.get('disc') ?? 'all', kind: params.get('kind') ?? 'all',
    stage: params.get('stage') ?? 'all', topic: params.get('topic') ?? 'all', loc: params.get('loc') ?? 'all',
    q: params.get('q') ?? '', from: params.get('from') ?? '', to: params.get('to') ?? '',
  };
  const setFilter = (f: StatsFilter) => {
    const next = new URLSearchParams(params);
    const put = (k: string, v: string | undefined, empty = '') => (v && v !== empty ? next.set(k, v) : next.delete(k));
    next.delete('pg'); // a new filter starts on the first page
    put('st', f.status, 'all'); put('disc', f.discipline, 'all'); put('kind', f.kind, 'all'); put('stage', f.stage, 'all'); put('topic', f.topic, 'all'); put('loc', f.loc, 'all'); put('q', f.q); put('from', f.from); put('to', f.to);
    setParams(next, { replace: true });
  };
  // by default the newest submission first
  const sort = (params.get('sort') ?? 'submitted') as SortKey;
  const dir = (params.get('dir') ?? (params.get('sort') ? 'asc' : 'desc')) as 'asc' | 'desc';
  const onSort = (k: SortKey) => {
    const next = new URLSearchParams(params);
    const nextDir = sort === k ? (dir === 'asc' ? 'desc' : 'asc') : k === 'submitted' ? 'desc' : 'asc';
    if (k === 'submitted' && nextDir === 'desc') {
      next.delete('sort'); next.delete('dir');
    } else {
      next.set('sort', k); next.set('dir', nextDir);
    }
    next.delete('pg');
    setParams(next, { replace: true });
  };
  const shown = useMemo(() => sortRows(applyFilter(rows.data ?? [], filter, false, structure.data), sort, dir),
    [rows.data, structure.data, filter.status, filter.discipline, filter.kind, filter.stage, filter.topic, filter.loc, filter.q, filter.from, filter.to, sort, dir]);
  const narrowed = !!(filter.q || filter.from || filter.to);
  // bulk actions: tick records, then run an action they allow (as in Odoo)
  const [sel, setSel] = useState<Set<string>>(new Set());
  useEffect(() => setSel(new Set()), [type, projectId]);
  // a page at a time (as in Odoo): a list of thousands of rows is slow to draw
  const pages = Math.max(1, Math.ceil(shown.length / PAGE));
  const page = Math.min(pages, Math.max(1, Number(params.get('pg')) || 1));
  const pageRows = useMemo(() => shown.slice((page - 1) * PAGE, page * PAGE), [shown, page]);
  const goPage = (n: number) => {
    const next = new URLSearchParams(params);
    n <= 1 ? next.delete('pg') : next.set('pg', String(n));
    setParams(next, { replace: true });
  };
  const visible = new Set(shown.map((r) => r.id));
  const chosen = [...sel].filter((id) => visible.has(id));
  const pageOn = pageRows.length > 0 && pageRows.every((r) => sel.has(r.id));
  const allOn = shown.length > 0 && chosen.length === shown.length;
  const pager = pages > 1 && (
    <Group gap={4} wrap="nowrap">
      <Text size="sm" c="dimmed" dir="ltr">{(page - 1) * PAGE + 1}-{Math.min(page * PAGE, shown.length)} / {shown.length}</Text>
      <ActionIcon variant="subtle" aria-label={t('rec.prevPage')} disabled={page <= 1} onClick={() => goPage(page - 1)}>{document.documentElement.dir === 'rtl' ? '›' : '‹'}</ActionIcon>
      <ActionIcon variant="subtle" aria-label={t('rec.nextPage')} disabled={page >= pages} onClick={() => goPage(page + 1)}>{document.documentElement.dir === 'rtl' ? '‹' : '›'}</ActionIcon>
    </Group>
  );
  const toggle = (id: string) => { const n = new Set(sel); if (n.has(id)) n.delete(id); else n.add(id); setSel(n); };

  return (
    <Stack>
      <Group justify="space-between">
        <Group>
          <TextInput placeholder={t('rec.search')} value={filter.q} onChange={(e) => setFilter({ ...filter, q: e.currentTarget.value })} w={260} />
          <Group gap={6} wrap="nowrap">
            <Text size="sm" c="dimmed">{t('stats.submittedFrom')}</Text>
            <TextInput type="date" w={150} aria-label={t('stats.submittedFrom')} value={filter.from}
              max={filter.to || undefined} onChange={(e) => setFilter({ ...filter, from: e.currentTarget.value })} />
            <Text size="sm" c="dimmed">{t('stats.to')}</Text>
            <TextInput type="date" w={150} aria-label={t('stats.to')} value={filter.to}
              min={filter.from || undefined} onChange={(e) => setFilter({ ...filter, to: e.currentTarget.value })} />
          </Group>
          {narrowed && (
            <Button variant="subtle" size="xs" onClick={() => setFilter({ ...filter, q: '', from: '', to: '' })}>{t('stats.clear')}</Button>
          )}
          <Switch label={t('rec.allRevisions')} checked={allRevs} onChange={(e) => setAllRevs(e.currentTarget.checked)} />
        </Group>
        {meta.data?.can_create && <Button onClick={() => setOpen(true)}>{typeText(type, 'new', 'rec.new')}</Button>}
      </Group>
      {rows.data && rows.data.length > 0 && (
        <RecordStats rows={rows.data} filter={filter} onChange={setFilter} showDraft={meta.data?.party_kind === 'contractor'}
          structure={structure.data} states={meta.data?.states} />
      )}
      {chosen.length > 0 && <BulkBar ids={chosen} projectId={projectId} onDone={() => setSel(new Set())} />}
      {(pager || (pageOn && !allOn)) && (
        <Group justify="space-between">
          <div>{pageOn && !allOn && (
            <Button size="compact-sm" variant="subtle" onClick={() => setSel(new Set(shown.map((r) => r.id)))}>{t('bulk.selectAll', { n: shown.length })}</Button>
          )}</div>
          {pager}
        </Group>
      )}
      {rows.isSuccess && shown.length === 0 ? <Text c="dimmed">{rows.data.length ? t('stats.noneHere') : typeText(type, 'empty', 'rec.empty')}</Text> : (
        <Card withBorder p={0}>
          <Table.ScrollContainer minWidth={760}>
            <Table highlightOnHover verticalSpacing="sm" horizontalSpacing="md">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th w={36}>
                    <Checkbox size="xs" aria-label={t('bulk.all')} checked={pageOn} indeterminate={chosen.length > 0 && !pageOn}
                      onChange={() => {
                        const n = new Set(sel);
                        pageRows.forEach((r) => (pageOn ? n.delete(r.id) : n.add(r.id)));
                        setSel(n);
                      }} />
                  </Table.Th>
                  <SortTh label={t('rec.number')} k="number" sort={sort} dir={dir} onSort={onSort} />
                  <SortTh label={t('rec.title')} k="title" sort={sort} dir={dir} onSort={onSort} />
                  <SortTh label={t('rec.discipline')} k="discipline" sort={sort} dir={dir} onSort={onSort} />
                  <SortTh label={t('rec.state')} k="state" sort={sort} dir={dir} onSort={onSort} />
                  <SortTh label={t('rec.submitted')} k="submitted" sort={sort} dir={dir} onSort={onSort} />
                  <SortTh label={t('rec.due')} k="due" sort={sort} dir={dir} onSort={onSort} />
                  <SortTh label={t('rec.answered')} k="answered" sort={sort} dir={dir} onSort={onSort} />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {pageRows.map((r) => (
                  <Table.Tr key={r.id} style={{ cursor: 'pointer' }} onClick={() => { saveNav(shown.map((x) => x.id), location.pathname + location.search); navigate(`/records/${r.id}`); }}>
                    <Table.Td onClick={(e) => e.stopPropagation()}>
                      <Checkbox size="xs" aria-label={r.number} checked={sel.has(r.id)} onChange={() => toggle(r.id)} />
                    </Table.Td>
                    <Table.Td><Text size="sm" fw={500} dir="ltr" ta="start" style={{ whiteSpace: 'nowrap' }}>{r.number} · R{r.rev_no}</Text></Table.Td>
                    <Table.Td>
                      <Text size="sm" lineClamp={2}>{rowTitle(structure.data, r)}</Text>
                      {(r.stage_id || r.all_locations || r.location_ids.length > 0) && (
                        <Text size="xs" c="dimmed" lineClamp={1}>{placeText(structure.data, r)}</Text>
                      )}
                    </Table.Td>
                    <Table.Td><Text size="sm">{r.discipline ? pick(r.discipline, 'name') : ''}</Text></Table.Td>
                    <Table.Td>
                      <Badge tt="none" variant="light" color={stateColor(r.state.color)}>{pick(r.state, 'name')}</Badge>
                      {r.lab_result && (
                        <Badge tt="none" size="sm" mt={4} color={r.lab_result === 'pass' ? 'green' : 'red'} style={{ display: 'block' }}>
                          {t(`lab.r.${r.lab_result}`)}{r.lab_decision ? ` · ${t(`lab.d.${r.lab_decision}`)}` : ''}
                        </Badge>
                      )}
                    </Table.Td>
                    <Table.Td><Text size="sm">{fmtDate(r.submitted_at)}</Text></Table.Td>
                    <Table.Td>
                      <Text size="sm" c={r.overdue ? 'red' : undefined} fw={r.overdue ? 600 : undefined}>{fmtDate(r.due_at, profile(type).timed)}</Text>
                      {r.overdue && <Badge size="xs" color="red" tt="none">{t('rec.overdue')}</Badge>}
                      {r.resubmit_due_at && (
                        <Badge size="xs" tt="none" variant="light" color={r.resubmit_overdue ? 'red' : 'orange'} style={{ display: 'block' }}>
                          {t(r.resubmit_overdue ? 'resubmit.lateShort' : 'resubmit.byShort')} {fmtDate(r.resubmit_due_at)}
                        </Badge>
                      )}
                      {r.required_by && ['draft', 'submitted'].includes(r.state.category) && (
                        <Badge size="xs" tt="none" variant="light" color={requiredColor(r.required_by)} style={{ display: 'block' }}>
                          {t('rec.requiredByShort')} {fmtDate(r.required_by)}
                        </Badge>
                      )}
                    </Table.Td>
                    <Table.Td>
                      {(() => {
                        const late = !!(r.answered_at && r.due_at && new Date(r.answered_at) > new Date(r.due_at));
                        return <Text size="sm" c={late ? 'orange.8' : undefined} title={late ? t('rec.answeredLate') : undefined}>
                          {fmtDate(r.answered_at, profile(type).timed)}</Text>;
                      })()}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>
      )}
      {pager && <Group justify="flex-end">{pager}</Group>}
      <Modal opened={open} onClose={() => setOpen(false)} title={typeText(type, 'new', 'rec.new')} size={type === 'daily_report' ? 'sm' : 'xl'}>
        {type === 'daily_report' ? <NewDaily projectId={projectId} onClose={() => setOpen(false)} />
          : meta.data && <NewSubmittal projectId={projectId} meta={meta.data} type={type} onClose={() => setOpen(false)} />}
      </Modal>
    </Stack>
  );
}


interface BulkAction { action: string; name_ar: string; name_en: string; requires_comment: boolean; style: string; count: number }
interface BulkResult { done: number; skipped: number; failed: { id: string; number: string; error: string }[] }
const STYLE: Record<string, string> = { green: 'green', teal: 'teal', orange: 'orange', red: 'red', primary: 'verqac', subtle: 'gray' };

/** The chosen records: the actions this user may take on them, each with how many it applies to. */
function BulkBar({ ids, projectId, onDone }: { ids: string[]; projectId: string; onDone: () => void }) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const key = [...ids].sort().join(',');
  const acts = useQuery({ queryKey: ['bulkActions', key], queryFn: () => api<BulkAction[]>('/records-bulk/actions', { method: 'POST', body: JSON.stringify({ ids }) }) });
  const [pick, setPick] = useState<BulkAction | null>(null);
  const [comment, setComment] = useState('');
  const [result, setResult] = useState<BulkResult | null>(null);
  const run = useMutation({
    mutationFn: () => api<BulkResult>('/records-bulk/transition', { method: 'POST', body: JSON.stringify({ ids, action: pick!.action, comment: comment || null }) }),
    onSuccess: (r) => {
      setResult(r); setPick(null); setComment('');
      qc.invalidateQueries({ queryKey: ['records', projectId] });
      qc.invalidateQueries({ queryKey: ['bulkActions'] });
      if (!r.failed.length) onDone();
    },
  });
  const name = (a: BulkAction) => (i18n.language === 'en' ? a.name_en : a.name_ar);
  return (
    <Card withBorder p="xs" bg="var(--mantine-color-gray-0)">
      <Group gap="xs">
        <Text size="sm" fw={600}>{t('bulk.chosen', { n: ids.length })}</Text>
        {acts.data?.length === 0 && <Text size="sm" c="dimmed">{t('bulk.none')}</Text>}
        {acts.data?.map((a) => (
          <Button key={a.action} size="xs" variant="light" color={STYLE[a.style] ?? 'gray'} onClick={() => { setPick(a); setResult(null); }}>
            {name(a)} ({a.count})
          </Button>
        ))}
        <Button size="xs" variant="subtle" color="gray" onClick={onDone}>{t('bulk.clear')}</Button>
      </Group>
      {result && (
        <Alert mt="xs" py={6} color={result.failed.length ? 'orange' : 'green'} withCloseButton onClose={() => setResult(null)}>
          {t('bulk.result', { done: result.done, skipped: result.skipped })}
          {result.failed.map((f) => <Text key={f.id} size="xs">{f.number}: {t(`errors.${f.error}`, { defaultValue: f.error })}</Text>)}
        </Alert>
      )}
      <Modal opened={!!pick} onClose={() => setPick(null)} title={pick ? name(pick) : ''}>
        {pick && (
          <Stack>
            <Text size="sm">{t('bulk.confirm', { n: pick.count, of: ids.length })}</Text>
            {pick.requires_comment && (
              <Textarea label={t('bulk.comment')} required autosize minRows={3} value={comment} onChange={(e) => setComment(e.currentTarget.value)} />
            )}
            <Group justify="flex-end">
              <Button variant="default" onClick={() => setPick(null)}>{t('common.cancel', { defaultValue: 'إلغاء' })}</Button>
              <Button color={STYLE[pick.style] ?? 'verqac'} loading={run.isPending} disabled={pick.requires_comment && !comment.trim()}
                onClick={() => run.mutate()}>{name(pick)} ({pick.count})</Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </Card>
  );
}
