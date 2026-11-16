import {
  Alert, Badge, Button, Card, FileInput, Group, Modal, MultiSelect, Select, SimpleGrid, Stack, Switch, Table, Text, Textarea,
  TextInput, UnstyledButton,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api, ApiError, type LinkedRef, type Place, type RecordDetail, type RecordMeta, type RecordRow } from '../api';
import { fmtDate, requiredColor, stateColor } from '../format';
import { pick } from '../i18n';
import { PlacePicker, placeText, rowTitle, useStructure } from './Structure';
import RecordStats, { applyFilter, CATEGORIES, type StatsFilter } from './RecordStats';

const DETAIL_KEYS = ['item', 'manufacturer', 'supplier', 'drawing_ref', 'spec_ref', 'boq_ref', 'quantity', 'unit'] as const;
const IR_KEYS = ['item', 'drawing_ref', 'spec_ref', 'boq_ref'] as const;
export type RegisterType = 'submittal' | 'inspection';

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

function NewSubmittal({ projectId, meta, onClose, type }: { projectId: string; meta: RecordMeta; onClose: () => void; type: RegisterType }) {
  const isIR = type === 'inspection';
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const structure = useStructure(projectId);
  const [place, setPlace] = useState<Place>({ stage_id: null, topic_id: null, all_locations: false, location_ids: [] });
  const kinds = meta.submittal_kinds.map((k) => ({ value: k.code ?? '', label: pick(k, 'name') }));
  const form = useForm({
    initialValues: {
      title: '', discipline_id: meta.disciplines[0]?.id ?? '', description: '', number: '', submittal_kind: kinds[0]?.value ?? '',
      item: '', manufacturer: '', supplier: '', drawing_ref: '', spec_ref: '', boq_ref: '', quantity: '', unit: '',
      required_by: '', required_by_note: '', files: [] as File[], requested_for: '', linked: [] as string[],
    },
  });

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
          discipline_id: v.discipline_id || null, number: blank(v.number),
          ...place,
          required_by: !isIR && v.required_by ? v.required_by : null,
          required_by_note: !isIR && v.required_by ? blank(v.required_by_note) : null,
          details: isIR
            ? { item: blank(v.item), drawing_ref: blank(v.drawing_ref), spec_ref: blank(v.spec_ref), boq_ref: blank(v.boq_ref) }
            : {
              submittal_kind: v.submittal_kind || null, item: blank(v.item), manufacturer: blank(v.manufacturer),
              supplier: blank(v.supplier), drawing_ref: blank(v.drawing_ref), spec_ref: blank(v.spec_ref),
              boq_ref: blank(v.boq_ref), quantity: blank(v.quantity), unit: blank(v.unit),
            },
        }),
      });
      for (const f of v.files) {
        const fd = new FormData();
        fd.append('file', f);
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
        {structure.data
          ? <PlacePicker structure={structure.data} value={place} onChange={setPlace}
              title={form.values.title} onTitle={(x) => form.setFieldValue('title', x)} />
          : <TextInput label={t('rec.title')} required {...form.getInputProps('title')} />}
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <Select label={t('rec.discipline')} allowDeselect={false}
            data={meta.disciplines.map((d) => ({ value: d.id, label: pick(d, 'name') }))} {...form.getInputProps('discipline_id')} />
          {isIR
            ? <TextInput type="datetime-local" label={t('ir.requestedFor')} description={t('ir.requestedForHint')} {...form.getInputProps('requested_for')} />
            : <Select label={t('rec.f.submittal_kind')} data={kinds} allowDeselect={false} searchable {...form.getInputProps('submittal_kind')} />}
          <TextInput label={t('rec.number')} placeholder={t('rec.numberHint')} dir="ltr" {...form.getInputProps('number')} />
        </SimpleGrid>
        {isIR && meta.link_submittals && (
          <LinkPicker projectId={projectId} stageId={place.stage_id} value={form.values.linked} onChange={(v) => form.setFieldValue('linked', v)} />
        )}
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          {(isIR ? IR_KEYS : DETAIL_KEYS).map((k) => (
            <TextInput key={k} label={t(isIR && k === 'item' ? 'ir.item' : `rec.f.${k}`)} dir={['drawing_ref', 'spec_ref', 'boq_ref', 'quantity'].includes(k) ? 'ltr' : undefined}
              {...form.getInputProps(k)} />
          ))}
        </SimpleGrid>
        <Textarea label={t('rec.description')} autosize minRows={2} {...form.getInputProps('description')} />
        {!isIR && <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <TextInput type="date" label={t('rec.requiredBy')} description={t('rec.requiredByHint')} {...form.getInputProps('required_by')} />
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

type SortKey = 'number' | 'title' | 'discipline' | 'state' | 'submitted' | 'due';
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
  }
}

function sortRows(rows: RecordRow[], key: SortKey, dir: 'asc' | 'desc'): RecordRow[] {
  const sign = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = sortValue(a, key), y = sortValue(b, key);
    if (x === y) return 0;
    if (x === null) return 1;
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
  const structure = useStructure(projectId);
  const filter: StatsFilter = {
    status: params.get('st') ?? 'all', discipline: params.get('disc') ?? 'all', kind: params.get('kind') ?? 'all',
    stage: params.get('stage') ?? 'all', topic: params.get('topic') ?? 'all', loc: params.get('loc') ?? 'all',
    q: params.get('q') ?? '', from: params.get('from') ?? '', to: params.get('to') ?? '',
  };
  const setFilter = (f: StatsFilter) => {
    const next = new URLSearchParams(params);
    const put = (k: string, v: string | undefined, empty = '') => (v && v !== empty ? next.set(k, v) : next.delete(k));
    put('st', f.status, 'all'); put('disc', f.discipline, 'all'); put('kind', f.kind, 'all'); put('stage', f.stage, 'all'); put('topic', f.topic, 'all'); put('loc', f.loc, 'all'); put('q', f.q); put('from', f.from); put('to', f.to);
    setParams(next, { replace: true });
  };
  const sort = (params.get('sort') ?? 'number') as SortKey;
  const dir = params.get('dir') === 'desc' ? 'desc' : 'asc';
  const onSort = (k: SortKey) => {
    const next = new URLSearchParams(params);
    const nextDir = sort === k && dir === 'asc' ? 'desc' : 'asc';
    k === 'number' && nextDir === 'asc' ? next.delete('sort') : next.set('sort', k);
    nextDir === 'asc' ? next.delete('dir') : next.set('dir', nextDir);
    setParams(next, { replace: true });
  };
  const shown = useMemo(() => sortRows(applyFilter(rows.data ?? [], filter, false, structure.data), sort, dir),
    [rows.data, structure.data, filter.status, filter.discipline, filter.kind, filter.stage, filter.topic, filter.loc, filter.q, filter.from, filter.to, sort, dir]);
  const narrowed = !!(filter.q || filter.from || filter.to);

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
        {meta.data?.can_create && <Button onClick={() => setOpen(true)}>{t(type === 'inspection' ? 'ir.new' : 'rec.new')}</Button>}
      </Group>
      {rows.data && rows.data.length > 0 && (
        <RecordStats rows={rows.data} filter={filter} onChange={setFilter} showDraft={meta.data?.party_kind === 'contractor'}
          structure={structure.data} states={meta.data?.states} />
      )}
      {rows.isSuccess && shown.length === 0 ? <Text c="dimmed">{rows.data.length ? t('stats.noneHere') : t('rec.empty')}</Text> : (
        <Card withBorder p={0}>
          <Table.ScrollContainer minWidth={760}>
            <Table highlightOnHover verticalSpacing="sm" horizontalSpacing="md">
              <Table.Thead>
                <Table.Tr>
                  <SortTh label={t('rec.number')} k="number" sort={sort} dir={dir} onSort={onSort} />
                  <SortTh label={t('rec.title')} k="title" sort={sort} dir={dir} onSort={onSort} />
                  <SortTh label={t('rec.discipline')} k="discipline" sort={sort} dir={dir} onSort={onSort} />
                  <SortTh label={t('rec.state')} k="state" sort={sort} dir={dir} onSort={onSort} />
                  <SortTh label={t('rec.submitted')} k="submitted" sort={sort} dir={dir} onSort={onSort} />
                  <SortTh label={t('rec.due')} k="due" sort={sort} dir={dir} onSort={onSort} />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {shown.map((r) => (
                  <Table.Tr key={r.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/records/${r.id}`)}>
                    <Table.Td><Text size="sm" fw={500} dir="ltr" ta="start" style={{ whiteSpace: 'nowrap' }}>{r.number} · R{r.rev_no}</Text></Table.Td>
                    <Table.Td>
                      <Text size="sm" lineClamp={2}>{rowTitle(structure.data, r)}</Text>
                      {(r.stage_id || r.all_locations || r.location_ids.length > 0) && (
                        <Text size="xs" c="dimmed" lineClamp={1}>{placeText(structure.data, r)}</Text>
                      )}
                    </Table.Td>
                    <Table.Td><Text size="sm">{r.discipline ? pick(r.discipline, 'name') : ''}</Text></Table.Td>
                    <Table.Td><Badge tt="none" variant="light" color={stateColor(r.state.color)}>{pick(r.state, 'name')}</Badge></Table.Td>
                    <Table.Td><Text size="sm">{fmtDate(r.submitted_at)}</Text></Table.Td>
                    <Table.Td>
                      <Text size="sm" c={r.overdue ? 'red' : undefined} fw={r.overdue ? 600 : undefined}>{fmtDate(r.due_at, type === 'inspection')}</Text>
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
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>
      )}
      <Modal opened={open} onClose={() => setOpen(false)} title={t(type === 'inspection' ? 'ir.new' : 'rec.new')} size="xl">
        {meta.data && <NewSubmittal projectId={projectId} meta={meta.data} type={type} onClose={() => setOpen(false)} />}
      </Modal>
    </Stack>
  );
}
