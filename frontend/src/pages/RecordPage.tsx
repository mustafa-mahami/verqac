import {
  ActionIcon, Alert, Anchor, Badge, Button, Card, FileButton, Grid, Group, Modal, MultiSelect, SegmentedControl, Select, SimpleGrid, Stack, Switch,
  Text, Textarea, TextInput, Timeline, Title, Tooltip,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { loadNav } from '../recordNav';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  api, ApiError, openProtected, type CheckLine, type LinkedRef, type Place, type RecordDetail, type RecordMeta, type Team, type Transition,
  type Attachment,
} from '../api';
import { daysUntil, fmtDate, fmtSize, requiredColor, stateColor } from '../format';
import i18n, { pick } from '../i18n';
import BackButton from './BackButton';
import Photos, { isPhoto, PdfViewer, shrinkPhoto } from './Photos';
import LabPanel from './LabPanel';
import DailyPanel from './DailyPanel';
import ProgrammePanel from './ProgrammePanel';
import { ApplicationReceipts } from './CashflowPanel';
import { PlacePicker, useStructure } from './Structure';
import { choiceLabel, CustomInput, fieldLabel, LTR_KEYS, money, profile, typeText } from '../recordTypes';

/** ISO timestamp -> value of an <input type="datetime-local"> in the browser's time zone, and back. */
const toLocalInput = (iso: string | null) => {
  if (!iso) return '';
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};
const fromLocalInput = (v: string) => (v ? new Date(v).toISOString() : null);
const DETAIL_KEYS = ['submittal_kind', 'item', 'manufacturer', 'supplier', 'drawing_ref', 'spec_ref', 'boq_ref', 'quantity', 'unit'] as const;
const btnColor: Record<string, string> = { primary: 'verqac', green: 'green', teal: 'teal', orange: 'orange', red: 'red', subtle: 'gray' };

const errText = (e: unknown) =>
  i18n.t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, { defaultValue: i18n.t('errors.generic') });

function Field({ label, value, ltr }: { label: string; value: string | null | undefined; ltr?: boolean }) {
  if (!value) return null;
  return (
    <div>
      <Text size="xs" c="dimmed">{label}</Text>
      <Text size="sm" dir={ltr ? 'ltr' : undefined} ta="start">{value}</Text>
    </div>
  );
}

function ActionForm({ rec, tr, onDone }: { rec: RecordDetail; tr: Transition; onDone: (r: RecordDetail) => void }) {
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);
  const team = useQuery({
    queryKey: ['team', rec.project_id], enabled: rec.can_act_on_behalf && tr.effect === 'respond',
    queryFn: () => api<Team>(`/projects/${rec.project_id}/team`),
  });
  const form = useForm({ initialValues: { comment: '', on_behalf_of: '' } });
  const party = team.data?.parties.find((p) => p.id === team.data?.my_party_id);
  const colleagues = (team.data?.members ?? []).filter((m) => m.is_active && m.party_id === party?.id);
  const go = useMutation({
    mutationFn: (v: typeof form.values) => api<RecordDetail>(`/records/${rec.id}/transitions`, {
      method: 'POST', body: JSON.stringify({ action: tr.action, comment: v.comment || null, on_behalf_of: v.on_behalf_of || null }),
    }),
    onSuccess: onDone, onError: (e) => setError(errText(e)),
  });
  return (
    <form onSubmit={form.onSubmit((v) => go.mutate(v))}>
      <Stack>
        {error && <Alert color="red">{error}</Alert>}
        <Text size="sm" dir="ltr" ta="start" fw={500}>{rec.number} · R{rec.rev_no}</Text>
        <Textarea label={t('rec.comment')} description={tr.requires_comment ? t('rec.commentRequired') : undefined}
          required={tr.requires_comment} autosize minRows={3} {...form.getInputProps('comment')} />
        {rec.can_act_on_behalf && tr.effect === 'respond' && colleagues.length > 1 && (
          <Select label={t('rec.onBehalfOf')} clearable placeholder={t('rec.myself')}
            data={colleagues.map((m) => ({ value: m.user.id, label: `${pick(m.user, 'full_name')} · ${pick(m.role, 'name')}` }))}
            {...form.getInputProps('on_behalf_of')} />
        )}
        <Button type="submit" color={btnColor[tr.style] ?? 'verqac'} loading={go.isPending}>{pick(tr, 'name')}</Button>
      </Stack>
    </form>
  );
}

/** The consultant writes the comments in a large field on the page, then picks the decision under it. */
/** Supervision writes the certified amount (with the retention kept) and the amount to pay, then certifies. */
function CertifyPanel({ rec, onDone }: { rec: RecordDetail; onDone: (r: RecordDetail) => void }) {
  const { t } = useTranslation();
  const [certified, setCertified] = useState(rec.custom.certified ?? '');
  const [payable, setPayable] = useState(rec.custom.payable ?? '');
  const [err, setErr] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => api<RecordDetail>(`/records/${rec.id}/certification`, { method: 'PUT', body: JSON.stringify({ certified, payable }) }),
    onSuccess: (r) => { setErr(null); onDone(r); },
    onError: (e) => setErr(errText(e)),
  });
  const changed = certified !== (rec.custom.certified ?? '') || payable !== (rec.custom.payable ?? '');
  return (
    <Card withBorder>
      <Title order={5} mb={4}>{t('pay.certifyTitle')}</Title>
      <Text size="sm" c="dimmed" mb="sm">{t('pay.certifyHint', { claimed: money(rec.custom.claimed) })}</Text>
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <TextInput label={t('custom.claimed')} value={money(rec.custom.claimed)} readOnly dir="ltr" />
        <TextInput label={t('custom.certified')} description={t('pay.certifiedHint')} value={certified} dir="ltr" inputMode="decimal"
          onChange={(e) => setCertified(e.currentTarget.value.replace(/[^0-9.,]/g, ''))} />
        <TextInput label={t('custom.payable')} description={t('pay.payableHint')} value={payable} dir="ltr" inputMode="decimal"
          onChange={(e) => setPayable(e.currentTarget.value.replace(/[^0-9.,]/g, ''))} />
      </SimpleGrid>
      {err && <Alert mt="sm" color="red">{err}</Alert>}
      <Group mt="sm">
        <Button variant="light" disabled={!changed} loading={save.isPending} onClick={() => save.mutate()}>{t('pay.saveAmounts')}</Button>
        {!changed && rec.custom.certified && rec.custom.payable && <Text size="sm" c="green">{t('pay.amountsSaved')}</Text>}
      </Group>
    </Card>
  );
}

function ResponsePanel({ rec, transitions, onDone }: { rec: RecordDetail; transitions: Transition[]; onDone: (r: RecordDetail) => void }) {
  const { t } = useTranslation();
  const key = `verqac.resp.${rec.id}`;
  const [text, setText] = useState(() => { try { return localStorage.getItem(key) ?? ''; } catch { return ''; } });
  const [onBehalf, setOnBehalf] = useState<string | null>(null);
  const [performed, setPerformed] = useState('');
  const [answeredOn, setAnsweredOn] = useState('');
  const [error, setError] = useState<string | null>(null);
  const ckey = `verqac.check.${rec.id}`;
  const [answers, setAnswers] = useState<Answer[]>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(ckey) ?? 'null') as Answer[] | null;
      if (saved && saved.length === rec.checklist.length) return saved;
    } catch { /* storage unavailable */ }
    return rec.checklist.map(() => ({ result: null, note: '' }));
  });
  const keepAnswers = (v: Answer[]) => { setAnswers(v); try { localStorage.setItem(ckey, JSON.stringify(v)); } catch { /* ignore */ } };
  const team = useQuery({
    queryKey: ['team', rec.project_id], enabled: rec.can_act_on_behalf,
    queryFn: () => api<Team>(`/projects/${rec.project_id}/team`),
  });
  const colleagues = (team.data?.members ?? []).filter((m) => m.is_active && m.party_id === team.data?.my_party_id);
  const assign = useMutation({
    mutationFn: (uid: string | null) => api<RecordDetail>(`/records/${rec.id}/assign`, { method: 'POST', body: JSON.stringify({ user_id: uid }) }),
    onSuccess: onDone, onError: (e) => setError(errText(e)),
  });
  const keep = (v: string) => { setText(v); try { localStorage.setItem(key, v); } catch { /* storage unavailable */ } };
  const go = useMutation({
    mutationFn: (tr: Transition) => {
      if (tr.requires_comment && !text.trim()) throw new ApiError(422, 'comment_required');
      return api<RecordDetail>(`/records/${rec.id}/transitions`, {
        method: 'POST', body: JSON.stringify({ action: tr.action, comment: text.trim() || null, on_behalf_of: onBehalf,
          performed_at: profile(rec.record_type.code).timed ? fromLocalInput(performed) : null,
          answered_on: (rec.imported || rec.record_type.code === 'payment') && answeredOn ? answeredOn : null,
          checklist: rec.checklist.length ? answers.map((x) => ({ result: x.result, note: x.note.trim() || null })) : null }),
      });
    },
    onSuccess: (r) => { try { localStorage.removeItem(key); localStorage.removeItem(ckey); } catch { /* ignore */ } onDone(r); },
    onError: (e) => setError(errText(e)),
  });
  return (
    <Card withBorder style={{ borderColor: 'var(--mantine-color-verqac-3)' }}>
      <Group justify="space-between" align="flex-start" mb="xs">
        <div>
          <Title order={5}>{typeText(rec.record_type.code, 'respTitle', 'resp.title')}</Title>
          <Text size="xs" c="dimmed">{t('resp.hint')}</Text>
        </div>
        {rec.can_assign && (
          <Select size="xs" w={240} label={t('assign.label')} placeholder={t('assign.none')} clearable
            value={rec.assigned_to?.id ?? null} disabled={assign.isPending}
            data={rec.assign_candidates.map((u) => ({ value: u.id, label: pick(u, 'full_name') }))}
            onChange={(v) => assign.mutate(v)} />
        )}
      </Group>
      {rec.checklist.length > 0 && <ChecklistAnswers rec={rec} value={answers} onChange={keepAnswers} />}
      <Textarea mt={rec.checklist.length ? 'md' : undefined} placeholder={t('resp.placeholder')} autosize minRows={6} maxRows={20} value={text}
        onChange={(e) => keep(e.currentTarget.value)} />
      {profile(rec.record_type.code).timed && (
        <TextInput mt="sm" w={260} type="datetime-local" label={t('ir.performedAt')} description={t('ir.performedHint')}
          value={performed} onChange={(e) => setPerformed(e.currentTarget.value)} />
      )}
      {(rec.imported || rec.record_type.code === 'payment') && (
        <TextInput mt="sm" w={260} type="date" label={t('resp.answeredOn')} description={t('resp.answeredOnHint')}
          max={new Date().toISOString().slice(0, 10)} min={rec.submitted_at?.slice(0, 10)}
          value={answeredOn} onChange={(e) => setAnsweredOn(e.currentTarget.value)} />
      )}
      {rec.can_act_on_behalf && colleagues.length > 1 && (
        <Select mt="sm" label={t('rec.onBehalfOf')} clearable placeholder={t('rec.myself')} value={onBehalf} onChange={setOnBehalf}
          data={colleagues.map((m) => ({ value: m.user.id, label: `${pick(m.user, 'full_name')} · ${pick(m.role, 'name')}` }))} />
      )}
      {error && <Alert color="red" mt="md" withCloseButton onClose={() => setError(null)}>{error}</Alert>}
      <Group gap="xs" mt="md">
        {transitions.map((tr) => (
          <Button key={tr.action} color={btnColor[tr.style] ?? 'verqac'} loading={go.isPending && go.variables?.action === tr.action}
            onClick={() => { setError(null); go.mutate(tr); }}>{pick(tr, 'name')}</Button>
        ))}
      </Group>
    </Card>
  );
}

type Answer = { result: CheckLine['result']; note: string };
const RESULT_COLOR = { ok: 'green', nc: 'red', na: 'gray' } as const;
const lineText = (x: CheckLine) => (i18n.language === 'en' ? x.en : x.ar);

/** The inspection checklist, read only: before the answer (what will be checked) or with its results. */
function ChecklistCard({ rec }: { rec: RecordDetail }) {
  const { t } = useTranslation();
  const answered = rec.checklist.some((x) => x.result);
  return (
    <Card withBorder>
      <Title order={5}>{t('checklist.title')}</Title>
      {!answered && <Text size="xs" c="dimmed" mb="xs">{t('checklist.preview')}</Text>}
      <Stack gap={4} mt="xs">
        {rec.checklist.map((x, i) => (
          <Group key={i} gap="xs" wrap="nowrap" align="flex-start">
            <Text size="sm" c="dimmed" w={20}>{i + 1}</Text>
            <Text size="sm" flex={1}>{lineText(x)}{x.note && <Text span size="xs" c="dimmed"> — {x.note}</Text>}</Text>
            {x.result && <Badge size="sm" tt="none" variant="light" color={RESULT_COLOR[x.result]}>{t(`checklist.r.${x.result}`)}</Badge>}
          </Group>
        ))}
      </Stack>
    </Card>
  );
}

/** Answering the checklist line by line (kept on this device until the reply is sent). */
function ChecklistAnswers({ rec, value, onChange }: { rec: RecordDetail; value: Answer[]; onChange: (v: Answer[]) => void }) {
  const { t } = useTranslation();
  const set = (i: number, patch: Partial<Answer>) => onChange(value.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const done = value.filter((x) => x.result).length;
  return (
    <Stack gap={6} mt="sm">
      <Group justify="space-between">
        <Text fw={600} size="sm">{t('checklist.title')}</Text>
        <Group gap="xs">
          <Text size="xs" c={done === value.length ? 'green.8' : 'dimmed'}>{t('checklist.progress', { done, total: value.length })}</Text>
          <Button size="compact-xs" variant="subtle" onClick={() => onChange(value.map((x) => (x.result ? x : { ...x, result: 'ok' })))}>
            {t('checklist.restOk')}
          </Button>
        </Group>
      </Group>
      {rec.checklist.map((x, i) => (
        <Stack key={i} gap={4} py={6} style={{ borderTop: '1px solid var(--mantine-color-gray-2)' }}>
          <Group gap="xs" wrap="nowrap" justify="space-between">
            <Text size="sm">{i + 1}. {lineText(x)}</Text>
            <SegmentedControl size="xs" value={value[i]?.result ?? ''} onChange={(v) => set(i, { result: v as Answer['result'] })}
              color={value[i]?.result ? RESULT_COLOR[value[i].result!] : undefined}
              data={(['ok', 'nc', 'na'] as const).map((r) => ({ value: r, label: t(`checklist.r.${r}`) }))} />
          </Group>
          {(value[i]?.result === 'nc' || value[i]?.note) && (
            <TextInput size="xs" placeholder={t('checklist.note')} value={value[i]?.note ?? ''}
              onChange={(e) => set(i, { note: e.currentTarget.value })} />
          )}
        </Stack>
      ))}
    </Stack>
  );
}

/** The contractor's "answer needed by" date (supply schedule). Both sides see it; it is never printed. */
function RequiredBy({ rec, onDone }: { rec: RecordDetail; onDone: (r: RecordDetail) => void }) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [day, setDay] = useState(rec.required_by ?? '');
  const [note, setNote] = useState(rec.required_by_note ?? '');
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (clear: boolean) => api<RecordDetail>(`/records/${rec.id}/required-by`, {
      method: 'PUT', body: JSON.stringify(clear ? { required_by: null } : { required_by: day || null, required_by_note: note.trim() || null }),
    }),
    onSuccess: (r) => { onDone(r); setEditing(false); setError(null); },
    onError: (e) => setError(errText(e)),
  });
  const open = ['draft', 'submitted'].includes(rec.state.category);
  if (!rec.required_by && !rec.can_set_required_by) return null;
  if (editing)
    return (
      <Card withBorder>
        <Stack gap="sm">
          {error && <Alert color="red">{error}</Alert>}
          <Group align="flex-end" wrap="wrap">
            <TextInput type="date" label={typeText(rec.record_type.code, 'requiredBy', 'rec.requiredBy')} value={day} onChange={(e) => setDay(e.currentTarget.value)} />
            <TextInput flex={1} miw={220} label={t('rec.requiredByNote')} maxLength={300} value={note} onChange={(e) => setNote(e.currentTarget.value)} />
          </Group>
          <Text size="xs" c="dimmed">{typeText(rec.record_type.code, 'requiredByHint', 'rec.requiredByHint')}</Text>
          <Group gap="xs">
            <Button size="xs" disabled={!day} loading={save.isPending} onClick={() => save.mutate(false)}>{t('rec.save')}</Button>
            <Button size="xs" variant="default" onClick={() => setEditing(false)}>{t('common.cancel')}</Button>
          </Group>
        </Stack>
      </Card>
    );
  if (!rec.required_by)
    return <Group><Button size="xs" variant="subtle" onClick={() => setEditing(true)}>+ {t('rec.requiredBySet')}</Button></Group>;
  const n = daysUntil(rec.required_by);
  const when = n < 0 ? t('rec.daysLate', { count: -n }) : n === 0 ? t('rec.dueToday') : t('rec.daysLeft', { count: n });
  return (
    <Alert color={open ? requiredColor(rec.required_by) : 'gray'} variant="light"
      title={open ? `${typeText(rec.record_type.code, 'requiredBy', 'rec.requiredBy')}: ${fmtDate(rec.required_by)} — ${when}` : t('rec.requiredByWas', { date: fmtDate(rec.required_by) })}>
      <Group justify="space-between" wrap="nowrap" align="flex-start">
        <Text size="sm">{rec.required_by_note || ''}</Text>
        {rec.can_set_required_by && (
          <Group gap={4} wrap="nowrap">
            <Button size="compact-xs" variant="subtle" onClick={() => setEditing(true)}>{t('rec.requiredByChange')}</Button>
            <Button size="compact-xs" variant="subtle" color="red" loading={save.isPending} onClick={() => save.mutate(true)}>{t('rec.requiredByClear')}</Button>
          </Group>
        )}
      </Group>
      {open && <Text size="xs" c="dimmed" mt={4}>{t('rec.notPrinted')}</Text>}
    </Alert>
  );
}

function EditForm({ rec, onDone }: { rec: RecordDetail; onDone: (r: RecordDetail) => void }) {
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);
  const type = rec.record_type.code;
  const pf = profile(type);
  const isIR = pf.timed;
  const [custom, setCustom] = useState<Record<string, string>>(rec.custom as Record<string, string>);
  const meta = useQuery({ queryKey: ['recMeta', rec.project_id, type], queryFn: () => api<RecordMeta>(`/projects/${rec.project_id}/records/meta?type=${type}`) });
  const cands = useQuery({ queryKey: ['linkCandidates', rec.project_id, 'all'], enabled: isIR,
    queryFn: () => api<LinkedRef[]>(`/projects/${rec.project_id}/link-candidates`) });
  const [requested, setRequested] = useState(toLocalInput(rec.requested_for));
  const [linked, setLinked] = useState<string[]>(rec.linked.map((x) => x.id));
  const d = rec.details;
  const structure = useStructure(rec.project_id);
  const initialPlace: Place = { stage_id: rec.stage?.id ?? null, topic_id: rec.topic?.id ?? null, all_locations: rec.all_locations, location_ids: rec.locations.map((x) => x.id) };
  const [place, setPlace] = useState<Place>(initialPlace);
  const kindOptions = (meta.data?.submittal_kinds ?? []).map((k) => ({ value: k.code ?? '', label: pick(k, 'name') }));
  // a record may hold a kind that was since deactivated (or legacy text): keep it selectable
  if (d.submittal_kind && !kindOptions.some((o) => o.value === d.submittal_kind))
    kindOptions.unshift({ value: d.submittal_kind, label: rec.submittal_kind_name ? pick({ n_ar: rec.submittal_kind_name.ar, n_en: rec.submittal_kind_name.en }, 'n') : d.submittal_kind });
  const form = useForm({
    initialValues: {
      title: rec.title, description: rec.description ?? '', discipline_id: rec.discipline?.id ?? '',
      ...Object.fromEntries(DETAIL_KEYS.map((k) => [k, d[k] == null ? '' : String(d[k])])),
    } as Record<string, string>,
  });
  const save = useMutation({
    mutationFn: (v: Record<string, string>) => {
      const blank = (x: string) => (x.trim() === '' ? null : x.trim());
      return api<RecordDetail>(`/records/${rec.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          title: place.topic_id ? null : v.title.trim(), description: blank(v.description), discipline_id: v.discipline_id || null,
          details: { ...Object.fromEntries(pf.keys.map((k) => [k, blank(v[k])])), ...(pf.kind ? { submittal_kind: v.submittal_kind || null } : {}) },
          custom: Object.fromEntries(pf.custom.filter((f) => !f.response).map((f) => [f.key, blank(custom[f.key] ?? '')])),
          ...place,
          ...(isIR ? { requested_for: fromLocalInput(requested), linked_ids: linked } : {}),
        }),
      });
    },
    onSuccess: onDone, onError: (e) => setError(errText(e)),
  });
  return (
    <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
      <Stack>
        {error && <Alert color="red">{error}</Alert>}
        {structure.data && pf.place !== false
          ? <PlacePicker structure={structure.data} value={place} onChange={setPlace} keep={initialPlace}
              title={form.values.title} onTitle={(x) => form.setFieldValue('title', x)} />
          : <TextInput label={t('rec.title')} required {...form.getInputProps('title')} />}
{pf.discipline !== false && (
        <Select label={t('rec.discipline')} allowDeselect={false}
          data={(meta.data?.disciplines ?? []).map((x) => ({ value: x.id, label: pick(x, 'name') }))} {...form.getInputProps('discipline_id')} />
)}
        {isIR && (
          <TextInput type="datetime-local" w={260} label={t('ir.requestedFor')} description={t('ir.requestedForHint')}
            value={requested} onChange={(e) => setRequested(e.currentTarget.value)} />
        )}
        {isIR && meta.data?.link_submittals && (
          <MultiSelect label={t('ir.linked')} description={t('ir.linkedHint')} searchable clearable value={linked} onChange={setLinked}
            data={(cands.data ?? []).map((x) => ({ value: x.id, label: `${x.number} R${x.rev_no} · ${x.title} — ${pick(x.state, 'name')}` }))} />
        )}
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          {pf.kind && <Select label={t('rec.f.submittal_kind')} allowDeselect={false} data={kindOptions} {...form.getInputProps('submittal_kind')} />}
          {pf.keys.map((k) => (
            <TextInput key={k} label={fieldLabel(type, k)} dir={LTR_KEYS.has(k) ? 'ltr' : undefined} {...form.getInputProps(k)} />
          ))}
          {pf.custom.filter((f) => !f.response).map((f) => (
            <CustomInput key={f.key} code={type} f={f} value={custom[f.key] ?? ''} onChange={(x) => setCustom({ ...custom, [f.key]: x })} />
          ))}
        </SimpleGrid>
        <Textarea label={typeText(type, 'description', 'rec.description')} autosize minRows={2} {...form.getInputProps('description')} />
        <Button type="submit" loading={save.isPending}>{t('rec.save')}</Button>
      </Stack>
    </form>
  );
}

export default function RecordPage() {
  const { t } = useTranslation();
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [action, setAction] = useState<Transition | null>(null);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [pdf, setPdf] = useState<Attachment | null>(null);
  const [internal, setInternal] = useState(false);
  const rec = useQuery({ queryKey: ['record', id], queryFn: () => api<RecordDetail>(`/records/${id}`) });
  // previous / next record of the list it was opened from (Alt+P / Alt+N)
  const nav = loadNav(id);
  const go = (step: number) => {
    const to = nav?.ids[nav.index + step];
    if (to) { setEditing(false); navigate(`/records/${to}`); }
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.altKey || !nav) return;
      if (e.key.toLowerCase() === 'n') { e.preventDefault(); go(1); }
      if (e.key.toLowerCase() === 'p') { e.preventDefault(); go(-1); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });
  const put = (r: RecordDetail) => {
    qc.setQueryData(['record', r.id], r);
    qc.invalidateQueries({ queryKey: ['records', r.project_id] });
  };
  const upload = useMutation({
    mutationFn: async ({ files, kind }: { files: File[]; kind: string }) => {
      let last: RecordDetail | null = null;
      for (const file of files) {
        const fd = new FormData();
        fd.append('file', await shrinkPhoto(file));
        fd.append('kind', kind);
        last = await api<RecordDetail>(`/records/${id}/attachments`, { method: 'POST', body: fd });
      }
      return last!;
    },
    onSuccess: put, onError: (e) => setError(errText(e)),
  });
  const caption = useMutation({
    mutationFn: ({ aid, text }: { aid: string; text: string }) =>
      api<RecordDetail>(`/records/${id}/attachments/${aid}`, { method: 'PATCH', body: JSON.stringify({ caption: text }) }),
    onSuccess: put, onError: (e) => setError(errText(e)),
  });
  const detach = useMutation({
    mutationFn: (aid: string) => api<RecordDetail>(`/records/${id}/attachments/${aid}`, { method: 'DELETE' }),
    onSuccess: put, onError: (e) => setError(errText(e)),
  });
  const revise = useMutation({
    mutationFn: () => api<RecordDetail>(`/records/${id}/revise`, { method: 'POST' }),
    onSuccess: (r) => { put(r); navigate(`/records/${r.id}`); }, onError: (e) => setError(errText(e)),
  });
  const addComment = useMutation({
    mutationFn: () => api<RecordDetail>(`/records/${id}/comments`, {
      method: 'POST', body: JSON.stringify({ body: comment, visibility: internal ? 'internal' : 'shared' }),
    }),
    onSuccess: (r) => { put(r); setComment(''); }, onError: (e) => setError(errText(e)),
  });

  if (rec.isError) return <Alert color="red" maw={600} mx="auto">{t('errors.generic')}</Alert>;
  const r = rec.data;
  if (!r) return null;
  const isDraft = r.state.category === 'draft';
  const det = r.details;
  const responses = r.transitions.filter((x) => x.effect === 'respond');
  const others = r.transitions.filter((x) => x.effect !== 'respond');

  const wide = ['programme', 'daily_report'].includes(r.record_type.code); // the programme / the daily report tables take the full width
  return (
    <Stack maw={wide ? '100%' : 1200} mx="auto">
      <Group justify="space-between" wrap="nowrap">
        <BackButton to={nav?.back ?? `/projects/${r.project_id}?tab=${profile(r.record_type.code).tab}`}
          label={typeText(r.record_type.code, 'back', 'back.submittals')} />
        {nav && nav.ids.length > 1 && (
          <Group gap={4} wrap="nowrap">
            <Tooltip label={`${t('rec.prev')} (Alt+P)`}>
              <ActionIcon variant="default" disabled={nav.index === 0} aria-label={t('rec.prev')}
                onClick={() => go(-1)}>{i18n.dir() === 'rtl' ? '›' : '‹'}</ActionIcon>
            </Tooltip>
            <Text size="sm" c="dimmed" dir="ltr" miw={70} ta="center">{nav.index + 1} / {nav.ids.length}</Text>
            <Tooltip label={`${t('rec.next')} (Alt+N)`}>
              <ActionIcon variant="default" disabled={nav.index === nav.ids.length - 1} aria-label={t('rec.next')}
                onClick={() => go(1)}>{i18n.dir() === 'rtl' ? '‹' : '›'}</ActionIcon>
            </Tooltip>
          </Group>
        )}
      </Group>
      <Group justify="space-between" align="flex-start">
        <div>
          <Group gap="xs">
            <Title order={3} dir="ltr">{r.number} · R{r.rev_no}</Title>
            <Badge size="lg" tt="none" variant="light" color={stateColor(r.state.color)}>{pick(r.state, 'name')}</Badge>
            {r.overdue && <Badge size="lg" tt="none" color="red">{t('rec.overdue')}</Badge>}
            {r.assigned_to && r.state.category === 'submitted' && (
              <Badge size="lg" tt="none" variant="outline">{t('assign.assignedTo', { name: pick(r.assigned_to, 'full_name') })}</Badge>
            )}
          </Group>
          <Text size="lg" mt={4}>{r.topic ? pick(r.topic, 'name') : r.title}</Text>
          <Text size="sm" c="dimmed">{pick(r.record_type, 'name')}{r.discipline ? ` · ${pick(r.discipline, 'name')}` : ''}</Text>
        </div>
        <Group gap="xs">
          <Button variant="default" size="xs" onClick={() => openProtected(`/records/${r.id}/pdf?lang=ar`, `${r.number}-R${r.rev_no}.pdf`, true)}>{t('rec.pdfAr')}</Button>
          <Button variant="default" size="xs" onClick={() => openProtected(`/records/${r.id}/pdf?lang=en`, `${r.number}-R${r.rev_no}.pdf`, true)}>{t('rec.pdfEn')}</Button>
        </Group>
      </Group>

      {error && <Alert color="red" withCloseButton onClose={() => setError(null)}>{error}</Alert>}
      {isDraft && <Alert color="gray">{t('rec.draftNote')}</Alert>}
      {isDraft && r.no_discipline_engineer && <Alert color="yellow">{t('rec.noEngineer')}</Alert>}
      {r.resubmit_due_at && !r.resubmitted_at && (() => {
        const n = daysUntil(r.resubmit_due_at.slice(0, 10));
        return (
          <Alert color={r.resubmit_overdue ? 'red' : 'orange'} variant="light"
            title={`${t('resubmit.by')}: ${fmtDate(r.resubmit_due_at)} — ${n < 0 ? t('rec.daysLate', { count: -n }) : n === 0 ? t('rec.dueToday') : t('rec.daysLeft', { count: n })}`}>
            <Text size="sm">{t('resubmit.hint')}</Text>
          </Alert>
        );
      })()}
      {profile(r.record_type.code).requiredBy && <RequiredBy key={`${r.id}-${r.required_by}-${r.required_by_note}`} rec={r} onDone={put} />}

      {(others.length > 0 || r.can_edit || r.can_revise) && (
        <Group gap="xs">
          {others.map((tr) => (
            <Button key={tr.action} color={btnColor[tr.style] ?? 'verqac'} variant={tr.style === 'subtle' ? 'subtle' : 'filled'}
              onClick={() => setAction(tr)}>{pick(tr, 'name')}</Button>
          ))}
          {r.can_edit && !['daily_report', 'programme'].includes(r.record_type.code) && <Button variant="light" onClick={() => setEditing(true)}>{t('rec.edit')}</Button>}
          {r.can_revise && <Button variant="light" loading={revise.isPending} onClick={() => revise.mutate()}>{t('rec.newRevision')}</Button>}
        </Group>
      )}

      <Grid gutter="md">
        <Grid.Col span={{ base: 12, md: wide ? 12 : 8 }}>
          <Stack>
            {r.record_type.code === 'payment' && r.state.category === 'submitted' && responses.some((x) => x.action === 'certify') && (
              <CertifyPanel rec={r} onDone={put} />
            )}
            {responses.length > 0 && <ResponsePanel rec={r} transitions={responses} onDone={put} />}
            {r.answered_at && (
              <Card withBorder style={{ borderInlineStartWidth: 4, borderInlineStartColor: `var(--mantine-color-${stateColor(r.state.color)}-6)` }}>
                <Text fw={600} mb={4}>{typeText(r.record_type.code, 'response', 'rec.response')}: {pick(r.state, 'name')}</Text>
                {r.response_comment && <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{r.response_comment}</Text>}
                <Text size="xs" c="dimmed" mt="xs">
                  {t('rec.answeredBy')}: {r.answered_by ? pick(r.answered_by, 'full_name') : ''}
                  {r.answered_on_behalf_of ? ` (${t('rec.onBehalf')} ${pick(r.answered_on_behalf_of, 'full_name')})` : ''} · {fmtDate(r.answered_at, true)}
                </Text>
              </Card>
            )}

            {r.checklist.length > 0 && responses.length === 0 && <ChecklistCard rec={r} />}
            {r.record_type.code === 'payment' && r.state.category === 'approved' && <ApplicationReceipts projectId={r.project_id} recordId={r.id} />}
            {r.record_type.code === 'test' && <LabPanel rec={r} />}
            {r.record_type.code === 'daily_report' && <DailyPanel rec={r} />}
            {r.record_type.code === 'programme' && <ProgrammePanel rec={r} />}
            <Card withBorder>
              <Title order={5} mb="sm">{t('rec.details')}</Title>
              <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
                {r.stage && <Field label={t('structure.stage')} value={pick(r.stage, 'name')} />}
                {(r.all_locations || r.locations.length > 0) && (
                  <Field label={t('structure.location')}
                    value={r.all_locations ? t('structure.wholeProject') : r.locations.map((x) => pick(x, 'name')).join(i18n.language === 'en' ? ', ' : '، ')} />
                )}
                {profile(r.record_type.code).timed && <>
                  <Field label={t('ir.requestedFor')} value={r.requested_for ? fmtDate(r.requested_for, true) : t('ir.asap')} />
                  {r.performed_at && <Field label={t('ir.performedAt')} value={fmtDate(r.performed_at, true)} />}
                </>}
                {([...(profile(r.record_type.code).kind ? ['submittal_kind'] as const : []), ...profile(r.record_type.code).keys.filter((k) => k !== 'unit')] as (typeof DETAIL_KEYS[number])[]).map((k) => (
                  <Field key={k} label={k === 'submittal_kind' ? t('rec.f.submittal_kind') : fieldLabel(r.record_type.code, k)} ltr={LTR_KEYS.has(k)}
                    value={k === 'quantity' && det.quantity != null ? `${Number(det.quantity)} ${det.unit ?? ''}`
                      : k === 'submittal_kind' && r.submittal_kind_name ? pick({ n_ar: r.submittal_kind_name.ar, n_en: r.submittal_kind_name.en }, 'n')
                      : (det[k] as string | null)} />
                ))}
                {profile(r.record_type.code).custom.filter((f) => f.kind !== 'long').map((f) => (
                  <Field key={f.key} label={fieldLabel(r.record_type.code, f.key)} ltr={LTR_KEYS.has(f.key)}
                    value={r.custom[f.key] ? (f.kind === 'select' ? choiceLabel(r.custom[f.key]!) : f.kind === 'number' ? money(r.custom[f.key]) : r.custom[f.key]) : null} />
                ))}
                <Field label={t('rec.submitted')} value={fmtDate(r.submitted_at, true)} />
                <Field label={t('rec.due')} value={fmtDate(r.due_at, profile(r.record_type.code).timed)} />
                {r.answered_at && <Field label={t('rec.answered')} value={fmtDate(r.answered_at, true)} />}
                {r.answered_by && <Field label={t('rec.answeredBy')} value={`${pick(r.answered_by, 'full_name')}${r.answered_on_behalf_of ? ` (${t('rec.onBehalf')} ${pick(r.answered_on_behalf_of, 'full_name')})` : ''}`} />}
                {r.resubmit_due_at && <Field label={t('resubmit.byShort')} value={fmtDate(r.resubmit_due_at, profile(r.record_type.code).timed)} />}
                <Field label={t('rec.submittedBy')} value={r.submitted_by ? pick(r.submitted_by, 'full_name') : null} />
                <Field label={t('rec.addressedTo')} value={r.addressed_to.map((u) => pick(u, 'full_name')).join(i18n.language === 'en' ? ', ' : '، ') || null} />
              </SimpleGrid>
              {r.description && <>
                {profile(r.record_type.code).custom.length > 0 && <Text size="xs" c="dimmed" mt="sm">{typeText(r.record_type.code, 'description', 'rec.description')}</Text>}
                <Text size="sm" mt={profile(r.record_type.code).custom.length ? 0 : 'sm'} style={{ whiteSpace: 'pre-wrap' }}>{r.description}</Text>
              </>}
              {profile(r.record_type.code).custom.filter((f) => f.kind === 'long' && r.custom[f.key]).map((f) => (
                <div key={f.key}>
                  <Text size="xs" c="dimmed" mt="sm">{fieldLabel(r.record_type.code, f.key)}</Text>
                  <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{r.custom[f.key]}</Text>
                </div>
              ))}
              {r.linked.length > 0 && (
                <Stack gap={4} mt="sm">
                  <Text size="xs" c="dimmed">{t('ir.linked')}</Text>
                  {r.linked.map((x) => (
                    <Group key={x.id} gap="xs">
                      <Anchor component={Link} to={`/records/${x.id}`} size="sm" dir="ltr">{x.number} R{x.rev_no}</Anchor>
                      <Text size="sm">{x.title}</Text>
                      <Badge size="xs" tt="none" variant="light" color={stateColor(x.state.color)}>{pick(x.state, 'name')}</Badge>
                    </Group>
                  ))}
                </Stack>
              )}
              {r.link_warning && (
                <Alert mt="sm" color="orange" variant="light" py={6}>{t(r.link_warning === 'no_link' ? 'ir.noLink' : 'ir.linkNotApproved')}</Alert>
              )}
            </Card>

            <Card withBorder>
              <Group justify="space-between" mb="sm">
                <Title order={5}>{t('rec.files')}</Title>
                <Group gap="xs">
                  {r.can_attach.map((kind) => (
                    <Group key={kind} gap={4}>
                      <FileButton multiple accept="image/*" onChange={(f) => f.length && upload.mutate({ files: f, kind })}>
                        {(props) => <Button {...props} size="xs" variant="light" color="teal" loading={upload.isPending}>{t('rec.addPhotos')} ({t(`rec.kind.${kind}`)})</Button>}
                      </FileButton>
                      <FileButton multiple onChange={(f) => f.length && upload.mutate({ files: f, kind })}>
                        {(props) => <Button {...props} size="xs" variant="light" loading={upload.isPending}>{t('rec.upload')} ({t(`rec.kind.${kind}`)})</Button>}
                      </FileButton>
                    </Group>
                  ))}
                </Group>
              </Group>
              <Photos items={r.attachments.filter(isPhoto)} canRemove={(a) => r.can_attach.includes(a.kind)} onRemove={(a) => detach.mutate(a.id)}
                onCaption={(a, text) => caption.mutate({ aid: a.id, text })} />
              <PdfViewer a={pdf} onClose={() => setPdf(null)} />
              {r.attachments.length === 0 ? <Text size="sm" c="dimmed">{t('rec.noFiles')}</Text> : r.attachments.some((a) => !isPhoto(a)) && (
                <Stack gap={6}>
                  {r.attachments.filter((a) => !isPhoto(a)).map((a) => (
                    <Group key={a.id} justify="space-between" wrap="nowrap">
                      <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
                        <Badge size="sm" tt="none" variant="outline" color={a.kind === 'response' ? 'teal' : a.kind === 'signed' ? 'grape' : 'gray'}>{t(`rec.kind.${a.kind}`)}</Badge>
                        <Anchor size="sm" dir="ltr" truncate onClick={() => (a.content_type === 'application/pdf' || a.filename.toLowerCase().endsWith('.pdf')
                          ? setPdf(a) : openProtected(`/files/${a.file_id}`, a.filename))}>
                          {a.filename}
                        </Anchor>
                        <Text size="xs" c="dimmed">{fmtSize(a.size)}</Text>
                        <ActionIcon size="sm" variant="subtle" aria-label={t('rec.download')} title={t('rec.download')}
                          onClick={() => openProtected(`/files/${a.file_id}`, a.filename)}>⤓</ActionIcon>
                      </Group>
                      {r.can_attach.includes(a.kind) && (
                        <ActionIcon variant="subtle" color="red" aria-label="remove" onClick={() => detach.mutate(a.id)}>×</ActionIcon>
                      )}
                    </Group>
                  ))}
                </Stack>
              )}
            </Card>

            <Card withBorder>
              <Title order={5} mb="sm">{t('rec.comments')}</Title>
              <Stack gap="sm">
                {r.comments.map((c) => (
                  <div key={c.id}>
                    <Group gap="xs">
                      <Text size="sm" fw={600}>{pick(c.author, 'full_name')}</Text>
                      <Text size="xs" c="dimmed">{t(`party.${c.party_kind}`)} · {fmtDate(c.created_at, true)}</Text>
                      {c.visibility === 'internal' && <Badge size="xs" color="yellow" tt="none">{t('rec.internalBadge')}</Badge>}
                    </Group>
                    <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{c.body}</Text>
                  </div>
                ))}
                <Textarea placeholder={t('rec.addComment')} autosize minRows={2} value={comment} onChange={(e) => setComment(e.currentTarget.value)} />
                <Group justify="space-between">
                  <Switch size="sm" label={t('rec.internal')} checked={internal} onChange={(e) => setInternal(e.currentTarget.checked)} />
                  <Button size="xs" disabled={!comment.trim()} loading={addComment.isPending} onClick={() => addComment.mutate()}>{t('rec.send')}</Button>
                </Group>
              </Stack>
            </Card>
          </Stack>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: wide ? 12 : 4 }}>
          <Stack>
            {r.revisions.length > 1 && (
              <Card withBorder>
                <Title order={5} mb="sm">{t('rec.revisions')}</Title>
                <Stack gap={6}>
                  {r.revisions.map((v) => (
                    <Group key={v.id} justify="space-between">
                      <Anchor component={Link} to={`/records/${v.id}`} size="sm" fw={v.id === r.id ? 700 : 400}>R{v.rev_no}</Anchor>
                      <Badge size="sm" tt="none" variant="light" color={stateColor(v.state.color)}>{pick(v.state, 'name')}</Badge>
                    </Group>
                  ))}
                </Stack>
              </Card>
            )}
            <Card withBorder>
              <Title order={5} mb="sm">{t('rec.history')}</Title>
              <Timeline bulletSize={14} lineWidth={2} active={r.events.length}>
                {r.events.map((e) => (
                  <Timeline.Item key={e.id} title={<Text size="sm" fw={500}>{t(`rec.events.${e.action}`, { defaultValue: e.to_state ? pick(e.to_state, 'name') : e.action })}</Text>}>
                    <Text size="xs" c="dimmed">
                      {pick(e.actor, 'full_name')}{e.on_behalf_of ? ` (${t('rec.onBehalf')} ${pick(e.on_behalf_of, 'full_name')})` : ''}
                    </Text>
                    <Text size="xs" c="dimmed">{fmtDate(e.at, true)}</Text>
                    {e.comment && <Text size="xs" mt={2} style={{ whiteSpace: 'pre-wrap' }}>{e.comment}</Text>}
                    {e.stamp && <Text size="xs" c="dimmed" title={e.stamp}>{t('rec.stamp')}: <span dir="ltr">{e.stamp.slice(0, 16)}…</span></Text>}
                  </Timeline.Item>
                ))}
              </Timeline>
            </Card>
          </Stack>
        </Grid.Col>
      </Grid>

      <Modal opened={!!action} onClose={() => setAction(null)} title={action ? pick(action, 'name') : ''}>
        {action && <ActionForm rec={r} tr={action} onDone={(x) => { put(x); setAction(null); }} />}
      </Modal>
      <Modal opened={editing} onClose={() => setEditing(false)} title={t('rec.edit')} size="xl">
        {editing && <EditForm rec={r} onDone={(x) => { put(x); setEditing(false); }} />}
      </Modal>
    </Stack>
  );
}
