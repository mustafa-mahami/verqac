import {
  ActionIcon, Alert, Anchor, Badge, Button, Card, FileButton, Grid, Group, Modal, Select, SimpleGrid, Stack, Switch,
  Text, Textarea, TextInput, Timeline, Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  api, ApiError, openProtected, type Place, type RecordDetail, type RecordMeta, type Team, type Transition,
} from '../api';
import { daysUntil, fmtDate, fmtSize, requiredColor, stateColor } from '../format';
import i18n, { pick } from '../i18n';
import BackButton from './BackButton';
import { PlacePicker, useStructure } from './Structure';

const DETAIL_KEYS = ['submittal_kind', 'item', 'manufacturer', 'supplier', 'drawing_ref', 'spec_ref', 'boq_ref', 'quantity', 'unit'] as const;
const LTR = new Set(['drawing_ref', 'spec_ref', 'boq_ref']);
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
function ResponsePanel({ rec, transitions, onDone }: { rec: RecordDetail; transitions: Transition[]; onDone: (r: RecordDetail) => void }) {
  const { t } = useTranslation();
  const key = `verqac.resp.${rec.id}`;
  const [text, setText] = useState(() => { try { return localStorage.getItem(key) ?? ''; } catch { return ''; } });
  const [onBehalf, setOnBehalf] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
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
        method: 'POST', body: JSON.stringify({ action: tr.action, comment: text.trim() || null, on_behalf_of: onBehalf }),
      });
    },
    onSuccess: (r) => { try { localStorage.removeItem(key); } catch { /* ignore */ } onDone(r); },
    onError: (e) => setError(errText(e)),
  });
  return (
    <Card withBorder style={{ borderColor: 'var(--mantine-color-verqac-3)' }}>
      <Group justify="space-between" align="flex-start" mb="xs">
        <div>
          <Title order={5}>{t('resp.title')}</Title>
          <Text size="xs" c="dimmed">{t('resp.hint')}</Text>
        </div>
        {rec.can_assign && (
          <Select size="xs" w={240} label={t('assign.label')} placeholder={t('assign.none')} clearable
            value={rec.assigned_to?.id ?? null} disabled={assign.isPending}
            data={rec.assign_candidates.map((u) => ({ value: u.id, label: pick(u, 'full_name') }))}
            onChange={(v) => assign.mutate(v)} />
        )}
      </Group>
      {error && <Alert color="red" mb="sm" withCloseButton onClose={() => setError(null)}>{error}</Alert>}
      <Textarea placeholder={t('resp.placeholder')} autosize minRows={6} maxRows={20} value={text}
        onChange={(e) => keep(e.currentTarget.value)} />
      {rec.can_act_on_behalf && colleagues.length > 1 && (
        <Select mt="sm" label={t('rec.onBehalfOf')} clearable placeholder={t('rec.myself')} value={onBehalf} onChange={setOnBehalf}
          data={colleagues.map((m) => ({ value: m.user.id, label: `${pick(m.user, 'full_name')} · ${pick(m.role, 'name')}` }))} />
      )}
      <Group gap="xs" mt="md">
        {transitions.map((tr) => (
          <Button key={tr.action} color={btnColor[tr.style] ?? 'verqac'} loading={go.isPending && go.variables?.action === tr.action}
            onClick={() => { setError(null); go.mutate(tr); }}>{pick(tr, 'name')}</Button>
        ))}
      </Group>
    </Card>
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
            <TextInput type="date" label={t('rec.requiredBy')} value={day} onChange={(e) => setDay(e.currentTarget.value)} />
            <TextInput flex={1} miw={220} label={t('rec.requiredByNote')} maxLength={300} value={note} onChange={(e) => setNote(e.currentTarget.value)} />
          </Group>
          <Text size="xs" c="dimmed">{t('rec.requiredByHint')}</Text>
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
      title={open ? `${t('rec.requiredBy')}: ${fmtDate(rec.required_by)} — ${when}` : t('rec.requiredByWas', { date: fmtDate(rec.required_by) })}>
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
  const meta = useQuery({ queryKey: ['recMeta', rec.project_id], queryFn: () => api<RecordMeta>(`/projects/${rec.project_id}/records/meta?type=submittal`) });
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
          details: Object.fromEntries(DETAIL_KEYS.map((k) => [k, blank(v[k])])),
          ...place,
        }),
      });
    },
    onSuccess: onDone, onError: (e) => setError(errText(e)),
  });
  return (
    <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
      <Stack>
        {error && <Alert color="red">{error}</Alert>}
        {structure.data
          ? <PlacePicker structure={structure.data} value={place} onChange={setPlace} keep={initialPlace}
              title={form.values.title} onTitle={(x) => form.setFieldValue('title', x)} />
          : <TextInput label={t('rec.title')} required {...form.getInputProps('title')} />}
        <Select label={t('rec.discipline')} allowDeselect={false}
          data={(meta.data?.disciplines ?? []).map((x) => ({ value: x.id, label: pick(x, 'name') }))} {...form.getInputProps('discipline_id')} />
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Select label={t('rec.f.submittal_kind')} allowDeselect={false} data={kindOptions} {...form.getInputProps('submittal_kind')} />
          {DETAIL_KEYS.filter((k) => k !== 'submittal_kind').map((k) => <TextInput key={k} label={t(`rec.f.${k}`)} dir={LTR.has(k) ? 'ltr' : undefined} {...form.getInputProps(k)} />)}
        </SimpleGrid>
        <Textarea label={t('rec.description')} autosize minRows={2} {...form.getInputProps('description')} />
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
  const [internal, setInternal] = useState(false);
  const rec = useQuery({ queryKey: ['record', id], queryFn: () => api<RecordDetail>(`/records/${id}`) });
  const put = (r: RecordDetail) => {
    qc.setQueryData(['record', r.id], r);
    qc.invalidateQueries({ queryKey: ['records', r.project_id] });
  };
  const upload = useMutation({
    mutationFn: ({ file, kind }: { file: File; kind: string }) => {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('kind', kind);
      return api<RecordDetail>(`/records/${id}/attachments`, { method: 'POST', body: fd });
    },
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

  return (
    <Stack maw={1200} mx="auto">
      <BackButton to={`/projects/${r.project_id}?tab=submittals`} label={t('back.submittals')} />
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
      <RequiredBy key={`${r.id}-${r.required_by}-${r.required_by_note}`} rec={r} onDone={put} />

      {(others.length > 0 || r.can_edit || r.can_revise) && (
        <Group gap="xs">
          {others.map((tr) => (
            <Button key={tr.action} color={btnColor[tr.style] ?? 'verqac'} variant={tr.style === 'subtle' ? 'subtle' : 'filled'}
              onClick={() => setAction(tr)}>{pick(tr, 'name')}</Button>
          ))}
          {r.can_edit && <Button variant="light" onClick={() => setEditing(true)}>{t('rec.edit')}</Button>}
          {r.can_revise && <Button variant="light" loading={revise.isPending} onClick={() => revise.mutate()}>{t('rec.newRevision')}</Button>}
        </Group>
      )}

      <Grid gutter="md">
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Stack>
            {responses.length > 0 && <ResponsePanel rec={r} transitions={responses} onDone={put} />}
            {r.answered_at && (
              <Card withBorder style={{ borderInlineStartWidth: 4, borderInlineStartColor: `var(--mantine-color-${stateColor(r.state.color)}-6)` }}>
                <Text fw={600} mb={4}>{t('rec.response')}: {pick(r.state, 'name')}</Text>
                {r.response_comment && <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{r.response_comment}</Text>}
                <Text size="xs" c="dimmed" mt="xs">
                  {t('rec.answeredBy')}: {r.answered_by ? pick(r.answered_by, 'full_name') : ''}
                  {r.answered_on_behalf_of ? ` (${t('rec.onBehalf')} ${pick(r.answered_on_behalf_of, 'full_name')})` : ''} · {fmtDate(r.answered_at, true)}
                </Text>
              </Card>
            )}

            <Card withBorder>
              <Title order={5} mb="sm">{t('rec.details')}</Title>
              <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
                {r.stage && <Field label={t('structure.stage')} value={pick(r.stage, 'name')} />}
                {(r.all_locations || r.locations.length > 0) && (
                  <Field label={t('structure.location')}
                    value={r.all_locations ? t('structure.wholeProject') : r.locations.map((x) => pick(x, 'name')).join(i18n.language === 'en' ? ', ' : '، ')} />
                )}
                {DETAIL_KEYS.filter((k) => k !== 'unit').map((k) => (
                  <Field key={k} label={t(`rec.f.${k}`)} ltr={LTR.has(k)}
                    value={k === 'quantity' && det.quantity != null ? `${Number(det.quantity)} ${det.unit ?? ''}`
                      : k === 'submittal_kind' && r.submittal_kind_name ? pick({ n_ar: r.submittal_kind_name.ar, n_en: r.submittal_kind_name.en }, 'n')
                      : (det[k] as string | null)} />
                ))}
                <Field label={t('rec.submitted')} value={fmtDate(r.submitted_at, true)} />
                <Field label={t('rec.due')} value={fmtDate(r.due_at)} />
                {r.answered_at && <Field label={t('rec.answered')} value={fmtDate(r.answered_at, true)} />}
                {r.answered_by && <Field label={t('rec.answeredBy')} value={`${pick(r.answered_by, 'full_name')}${r.answered_on_behalf_of ? ` (${t('rec.onBehalf')} ${pick(r.answered_on_behalf_of, 'full_name')})` : ''}`} />}
                {r.resubmit_due_at && <Field label={t('resubmit.byShort')} value={fmtDate(r.resubmit_due_at)} />}
                <Field label={t('rec.submittedBy')} value={r.submitted_by ? pick(r.submitted_by, 'full_name') : null} />
                <Field label={t('rec.addressedTo')} value={r.addressed_to.map((u) => pick(u, 'full_name')).join(i18n.language === 'en' ? ', ' : '، ') || null} />
              </SimpleGrid>
              {r.description && <Text size="sm" mt="sm" style={{ whiteSpace: 'pre-wrap' }}>{r.description}</Text>}
            </Card>

            <Card withBorder>
              <Group justify="space-between" mb="sm">
                <Title order={5}>{t('rec.files')}</Title>
                <Group gap="xs">
                  {r.can_attach.map((kind) => (
                    <FileButton key={kind} onChange={(f) => f && upload.mutate({ file: f, kind })}>
                      {(props) => <Button {...props} size="xs" variant="light" loading={upload.isPending}>{t('rec.upload')} ({t(`rec.kind.${kind}`)})</Button>}
                    </FileButton>
                  ))}
                </Group>
              </Group>
              {r.attachments.length === 0 ? <Text size="sm" c="dimmed">{t('rec.noFiles')}</Text> : (
                <Stack gap={6}>
                  {r.attachments.map((a) => (
                    <Group key={a.id} justify="space-between" wrap="nowrap">
                      <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
                        <Badge size="sm" tt="none" variant="outline" color={a.kind === 'response' ? 'teal' : 'gray'}>{t(`rec.kind.${a.kind}`)}</Badge>
                        <Anchor size="sm" dir="ltr" truncate onClick={() => openProtected(`/files/${a.file_id}`, a.filename, a.content_type === 'application/pdf')}>
                          {a.filename}
                        </Anchor>
                        <Text size="xs" c="dimmed">{fmtSize(a.size)}</Text>
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

        <Grid.Col span={{ base: 12, md: 4 }}>
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
