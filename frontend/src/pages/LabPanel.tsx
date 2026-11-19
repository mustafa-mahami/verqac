import {
  ActionIcon, Alert, Badge, Button, Card, Grid, Group, Loader, Modal, NumberInput, ScrollArea, SegmentedControl, Select, SimpleGrid, Stack, Table,
  Tabs, Text, Textarea, TextInput, Title,
} from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError, fetchBlob, type RecordDetail } from '../api';
import { fmtDate } from '../format';
import i18n, { pick } from '../i18n';
import {
  blankLine, DECISIONS, labPayload, linesFromTemplate, saveLab, type ConcreteClass, type LabData, type LabLine, type LabOut,
  type LabTemplate,
} from '../lab';

const errText = (e: unknown) => i18n.t(`errors.${e instanceof ApiError ? e.code : 'generic'}`, { defaultValue: i18n.t('errors.generic') });
const resColor = { pass: 'green', fail: 'red', na: 'gray' } as const;
const num = (v: string | number) => (v === '' || v === null || v === undefined ? null : Number(v));

/** Result lines: sample, parameter, value, limits, and the line's result. */
function LinesTable({ lines, onChange, editable, review, fck, addRole }: {
  lines: LabLine[]; onChange: (l: LabLine[]) => void; editable: boolean; review?: boolean; fck?: number | null;
  addRole?: LabLine['role'];
}) {
  const strength = lines.some((x) => x.role);
  const { t } = useTranslation();
  const set = (i: number, p: Partial<LabLine>) => onChange(lines.map((x, j) => (j === i ? { ...x, ...p } : x)));
  return (
    <Stack gap={4}>
      <ScrollArea>
        <Table withTableBorder verticalSpacing={2} horizontalSpacing={4} fz="sm" miw={720}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={80}>{t('lab.sample')}</Table.Th><Table.Th>{t('lab.parameter')}</Table.Th>
              <Table.Th w={110}>{t('lab.value')}</Table.Th><Table.Th w={70}>{t('lab.unit')}</Table.Th>
              <Table.Th w={80}>{t('lab.min')}</Table.Th><Table.Th w={80}>{t('lab.max')}</Table.Th>
              {strength && <Table.Th w={80}>{t('lab.pct')}</Table.Th>}
              <Table.Th w={90}>{t('lab.result')}</Table.Th>{editable && <Table.Th w={30} />}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {lines.map((x, i) => (
              <Table.Tr key={i} bg={review && !x.legible ? 'var(--mantine-color-orange-0)' : undefined}>
                <Table.Td>{editable ? <TextInput size="xs" dir="ltr" value={x.sample ?? ''} onChange={(e) => set(i, { sample: e.currentTarget.value || null })} /> : <Text size="sm" dir="ltr">{x.sample}</Text>}</Table.Td>
                <Table.Td>{editable ? <TextInput size="xs" dir="ltr" value={x.parameter} onChange={(e) => set(i, { parameter: e.currentTarget.value })} />
                  : <Text size="sm" dir="ltr">{x.parameter}{x.age && !x.parameter.includes('day') ? ` (${x.age} d)` : ''}</Text>}</Table.Td>
                <Table.Td>
                  {x.kind === 'okng'
                    ? (editable ? <Select size="xs" value={x.text} clearable data={['OK', 'NOK']} onChange={(v) => set(i, { text: v })} /> : <Text size="sm">{x.text}</Text>)
                    : (editable ? <NumberInput size="xs" hideControls value={x.value ?? ''} decimalScale={3}
                        onChange={(v) => set(i, { value: num(v), legible: true })} /> : <Text size="sm" fw={600}>{x.value ?? ''}</Text>)}
                  {review && !x.legible && <Text size="xs" c="orange.8">{t('lab.unsure')}</Text>}
                </Table.Td>
                <Table.Td><Text size="sm" dir="ltr">{x.unit}</Text></Table.Td>
                <Table.Td>{editable && x.kind === 'number' ? <NumberInput size="xs" hideControls value={x.min ?? ''} onChange={(v) => set(i, { min: num(v) })} /> : <Text size="sm">{x.min ?? ''}</Text>}</Table.Td>
                <Table.Td>{editable && x.kind === 'number' ? <NumberInput size="xs" hideControls value={x.max ?? ''} onChange={(v) => set(i, { max: num(v) })} /> : <Text size="sm">{x.max ?? ''}</Text>}</Table.Td>
                {strength && <Table.Td><Text size="sm">{x.role && fck && x.value ? `${Math.round((1000 * x.value) / fck) / 10}%` : ''}</Text></Table.Td>}
                <Table.Td>{x.result && x.result !== 'na' && <Badge size="sm" tt="none" variant="light" color={resColor[x.result]}>{t(`lab.r.${x.result}`)}</Badge>}</Table.Td>
                {editable && <Table.Td><ActionIcon size="sm" variant="subtle" color="red" aria-label="remove" onClick={() => onChange(lines.filter((_, j) => j !== i))}>×</ActionIcon></Table.Td>}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea>
      {editable && <Group><Button size="compact-xs" variant="subtle" onClick={() => onChange([...lines, blankLine(addRole === 'strength7'
        ? { parameter: 'Compressive strength 7-day', unit: 'MPa', age: 7, role: 'strength7' } : {})])}>+ {t('lab.addLine')}</Button></Group>}
    </Stack>
  );
}

/** 28-day results and other parameters, and 7-day results in their own tab (as in the certificate). */
export function LinesTabs({ lines, onChange, editable, review, fck }: {
  lines: LabLine[]; onChange: (l: LabLine[]) => void; editable: boolean; review?: boolean; fck?: number | null;
}) {
  const { t } = useTranslation();
  const main = lines.filter((x) => x.role !== 'strength7');
  const seven = lines.filter((x) => x.role === 'strength7');
  if (!seven.length) return <LinesTable lines={lines} onChange={onChange} editable={editable} review={review} fck={fck} />;
  const unsure = (l: LabLine[]) => (review ? l.filter((x) => !x.legible).length : 0);
  return (
    <Tabs defaultValue="main" keepMounted={false}>
      <Tabs.List mb="xs">
        <Tabs.Tab value="main">{t('lab.tab28', { count: main.length })}{unsure(main) ? ' ⚠' : ''}</Tabs.Tab>
        <Tabs.Tab value="seven">{t('lab.tab7', { count: seven.length })}{unsure(seven) ? ' ⚠' : ''}</Tabs.Tab>
      </Tabs.List>
      <Tabs.Panel value="main"><LinesTable lines={main} onChange={(l) => onChange([...l, ...seven])} editable={editable} review={review} fck={fck} /></Tabs.Panel>
      <Tabs.Panel value="seven"><LinesTable lines={seven} onChange={(l) => onChange([...main, ...l])} editable={editable} review={review} fck={fck} addRole="strength7" /></Tabs.Panel>
    </Tabs>
  );
}

/** Certificate details (lab, report no., dates, concrete class, element ...). */
function HeaderFields({ d, set, editable, classes }: {
  d: LabData; set: (p: Partial<LabData>) => void; editable: boolean; classes: ConcreteClass[];
}) {
  const { t } = useTranslation();
  const txt = (k: keyof LabData, label: string, ltr = false) => (
    <TextInput size="xs" label={label} disabled={!editable} dir={ltr ? 'ltr' : undefined} value={(d[k] as string | null) ?? ''}
      onChange={(e) => set({ [k]: e.currentTarget.value || null } as Partial<LabData>)} />
  );
  const dt = (k: 'sampling_date' | 'test_date' | 'report_date', label: string) => (
    <TextInput size="xs" type="date" label={label} disabled={!editable} value={d[k] ?? ''} onChange={(e) => set({ [k]: e.currentTarget.value || null })} />
  );
  const concrete = d.acceptance === 'concrete';
  return (
    <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="xs">
      {txt('lab_name', t('lab.labName'))}
      {txt('lab_report_no', t('lab.reportNo'), true)}
      {dt('sampling_date', t('lab.samplingDate'))}
      {dt('report_date', t('lab.reportDate'))}
      {concrete && (
        <Select size="xs" label={t('lab.class')} disabled={!editable} clearable value={d.class_id}
          data={classes.filter((k) => k.is_active).map((k) => ({ value: k.id!, label: `${k.grade} · ${Number(k.fck)} MPa${k.name ? ` · ${k.name}` : ''}` }))}
          onChange={(v) => set({ class_id: v })} />
      )}
      {concrete && <NumberInput size="xs" label={t('lab.fck')} disabled={!editable || !!d.class_id} value={d.fck ?? ''} onChange={(v) => set({ fck: num(v) })} />}
      {txt('grade', t('lab.grade'), true)}
      {txt('element', t('lab.element'))}
      <NumberInput size="xs" label={t('lab.quantity')} disabled={!editable} value={d.quantity ?? ''} onChange={(v) => set({ quantity: num(v) })} />
      {txt('quantity_uom', t('lab.uom'), true)}
      {txt('specification', t('lab.spec'), true)}
      <Select size="xs" label={t('lab.labConclusion')} disabled={!editable} clearable value={d.lab_conclusion}
        data={[{ value: 'pass', label: t('lab.r.pass') }, { value: 'fail', label: t('lab.r.fail') }]}
        onChange={(v) => set({ lab_conclusion: v as LabData['lab_conclusion'] })} />
    </SimpleGrid>
  );
}

function ResultLine({ lab }: { lab: LabOut }) {
  const { t } = useTranslation();
  if (!lab.result) return <Text size="sm" c="dimmed">{t('lab.noResult')}</Text>;
  return (
    <Stack gap={4}>
      <Group gap="sm">
        <Badge size="lg" tt="none" color={resColor[lab.result]}>{t(`lab.r.${lab.result}`)}</Badge>
        {lab.note && <Text size="sm" dir="ltr">{lab.note}</Text>}
        {lab.strength_avg !== null && <Text size="sm" c="dimmed">{t('lab.avgLow', { avg: lab.strength_avg, low: lab.strength_min })}</Text>}
      </Group>
      {lab.conflict && <Alert color="orange" variant="light" py={6}>{t('lab.conflict', { lab: t(`lab.r.${lab.lab_conclusion}`) })}</Alert>}
    </Stack>
  );
}

/** The AI review: the certificate next to the values read; nothing is saved until "Apply". */
function AiReview({ rec, lab, classes, onDone }: { rec: RecordDetail; lab: LabOut; classes: ConcreteClass[]; onDone: (l: LabOut) => void }) {
  const { t } = useTranslation();
  type Draft = NonNullable<LabOut['ai_draft']>;
  // one draft per certificate in the PDF (older answers hold a single one)
  const certs: Draft[] = (lab.ai_draft as { certificates?: Draft[] }).certificates ?? [lab.ai_draft!];
  const [ci, setCi] = useState(0);
  const [all, setAll] = useState<LabData[]>(() => certs.map((x) => ({ ...lab, ...x, template_id: lab.template_id, material: lab.material } as LabData)));
  const draft = certs[ci];
  const d = all[ci];
  const setD = (x: LabData) => setAll(all.map((y, j) => (j === ci ? x : y)));
  // choosing a class in the review fixes fck, the rule and the 28-day minimums, as on the test
  const setHeader = (p: Partial<LabData>) => {
    const k = p.class_id ? classes.find((c) => c.id === p.class_id) : null;
    setD(k ? { ...d, ...p, fck: Number(k.fck), grade: k.grade, mean_margin: Number(k.mean_margin), individual_rule: k.individual_rule,
      individual_margin: Number(k.individual_margin), lines: d.lines.map((x) => (x.role === 'strength28' ? { ...x, min: Number(k.fck) } : x)) }
      : { ...d, ...p });
  };
  const [pdf, setPdf] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let url: string | null = null;
    if (lab.ai_file_id) fetchBlob(`/files/${lab.ai_file_id}`).then((b) => { url = URL.createObjectURL(b); setPdf(url); }).catch(() => undefined);
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [lab.ai_file_id]);
  const apply = useMutation({ mutationFn: () => saveLab(rec.id, { ...labPayload(d), ai_applied: true }), onSuccess: onDone, onError: (e) => setError(errText(e)) });
  const discard = useMutation({ mutationFn: () => api<LabOut>(`/records/${rec.id}/lab/ai-discard`, { method: 'POST' }), onSuccess: onDone });
  const unsure = d.lines.filter((x) => !x.legible).length;
  return (
    <Grid gutter="md">
      <Grid.Col span={{ base: 12, md: 5 }}>
        {pdf ? <iframe src={pdf} title="certificate" style={{ width: '100%', height: '75vh', border: '1px solid var(--mantine-color-gray-3)' }} /> : <Loader />}
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 7 }}>
        <Stack gap="sm">
          <Alert color="blue" variant="light" py={6}>{t('lab.reviewHint')}</Alert>
          {certs.length > 1 && (
            <Stack gap={4}>
              <Text size="sm" fw={600}>{t('lab.certs', { count: certs.length })}</Text>
              <SegmentedControl value={String(ci)} onChange={(v) => setCi(Number(v))}
                data={certs.map((c, i) => ({ value: String(i), label: `${t('lab.page')} ${c.page ?? i + 1} · ${c.lab_report_no ?? '?'}` }))} />
              <Text size="xs" c="dimmed">{t('lab.certsHint')}</Text>
            </Stack>
          )}
          {unsure > 0 && <Alert color="orange" variant="light" py={6}>{t('lab.unsureCount', { count: unsure })}</Alert>}
          {d.acceptance === 'concrete' && (draft as { grade_unknown?: boolean }).grade_unknown && (
            <Alert color="red" variant="light" py={6}>{t('lab.gradeUnknown', { grade: draft.cert_grade })}</Alert>
          )}
          {d.acceptance === 'concrete' && draft.cert_strength && d.fck && Math.abs(draft.cert_strength - d.fck) > 0.01 && (
            <Alert color="orange" variant="light" py={6}>{t('lab.strengthDiff', { grade: draft.cert_grade ?? '', cert: draft.cert_strength, fck: d.fck })}</Alert>
          )}
          {d.acceptance === 'concrete' && (
            <Text size="sm">{draft.class_match ? t(`lab.match.${draft.class_match}`, { grade: d.grade }) : t('lab.match.none')}
              {draft.cert_grade ? ` · ${t('lab.certGrade')}: ${draft.cert_grade}` : ''}</Text>
          )}
          {error && <Alert color="red">{error}</Alert>}
          <HeaderFields d={d} set={setHeader} editable classes={classes} />
          <LinesTabs lines={d.lines} onChange={(l) => setD({ ...d, lines: l })} editable review fck={d.fck} />
          {draft.remarks && <Text size="xs" c="dimmed">{t('lab.aiRemarks')}: {draft.remarks}</Text>}
          <Group justify="flex-end">
            <Button variant="default" loading={discard.isPending} onClick={() => discard.mutate()}>{t('lab.discard')}</Button>
            <Button loading={apply.isPending} onClick={() => apply.mutate()}>{t('lab.apply')}</Button>
          </Group>
        </Stack>
      </Grid.Col>
    </Grid>
  );
}

export default function LabPanel({ rec }: { rec: RecordDetail }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['lab', rec.id], queryFn: () => api<LabOut>(`/records/${rec.id}/lab`),
    refetchInterval: (query) => (query.state.data?.ai_state === 'reading' ? 3000 : false),
  });
  const classes = useQuery({ queryKey: ['concreteClasses', rec.project_id], queryFn: () => api<ConcreteClass[]>(`/projects/${rec.project_id}/concrete-classes`) });
  const templates = useQuery({ queryKey: ['labTemplates', rec.project_id], queryFn: () => api<LabTemplate[]>(`/projects/${rec.project_id}/lab-templates`) });
  const [d, setD] = useState<LabData | null>(null);
  const [dirty, setDirty] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pdfId, setPdfId] = useState<string | null>(null);
  const [specimens, setSpecimens] = useState<number | ''>(3);
  const [decision, setDecision] = useState<{ d: string | null; note: string }>({ d: null, note: '' });
  useEffect(() => {
    if (q.data && !dirty) setD(q.data);
    if (q.data) setDecision({ d: q.data.decision, note: q.data.decision_note ?? '' });
  }, [q.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const put = (l: LabOut) => { qc.setQueryData(['lab', rec.id], l); setD(l); setDirty(false); qc.invalidateQueries({ queryKey: ['records', rec.project_id] }); };
  const save = useMutation({ mutationFn: () => saveLab(rec.id, labPayload(d!)), onSuccess: (l) => { put(l); setMsg({ ok: true, text: t('settings.saved') }); }, onError: (e) => setMsg({ ok: false, text: errText(e) }) });
  const read = useMutation({
    mutationFn: async (fileId: string) => {
      if (dirty) await saveLab(rec.id, labPayload(d!));
      return api<LabOut>(`/records/${rec.id}/lab/ai-read`, { method: 'POST', body: JSON.stringify({ file_id: fileId }) });
    },
    onSuccess: put, onError: (e) => setMsg({ ok: false, text: errText(e) }),
  });
  const decide = useMutation({
    mutationFn: () => api<LabOut>(`/records/${rec.id}/lab/decision`, { method: 'PUT', body: JSON.stringify({ decision: decision.d, note: decision.note }) }),
    onSuccess: (l) => { put(l); qc.invalidateQueries({ queryKey: ['record', rec.id] }); setMsg({ ok: true, text: t('settings.saved') }); },
    onError: (e) => setMsg({ ok: false, text: errText(e) }),
  });
  const lab = q.data;
  if (!lab || !d) return null;
  const set = (p: Partial<LabData>) => { setD({ ...d, ...p }); setDirty(true); };
  const tpl = templates.data?.find((x) => x.id === d.template_id);
  const pdfs = rec.attachments.filter((a) => a.content_type === 'application/pdf');
  const cls = classes.data ?? [];
  const chosenPdf = pdfId ?? (pdfs.length === 1 ? pdfs[0].file_id : null);
  const loadTemplate = (id: string | null) => {
    const x = templates.data?.find((y) => y.id === id);
    if (!x) return set({ template_id: null });
    const k = cls.find((c) => c.id === d.class_id);
    set({ template_id: x.id, material: x.material, acceptance: x.acceptance, specification: d.specification ?? x.standard,
      lines: linesFromTemplate(x, { specimens: Number(specimens) || 0, fck: k?.fck ?? d.fck }) });
  };

  return (
    <Card withBorder style={{ borderColor: 'var(--mantine-color-verqac-3)' }}>
      <Group justify="space-between" mb="xs">
        <Title order={5}>{t('lab.title')}</Title>
        <ResultLine lab={lab} />
      </Group>
      {msg && <Alert mb="sm" color={msg.ok ? 'green' : 'red'} withCloseButton onClose={() => setMsg(null)}>{msg.text}</Alert>}

      {lab.can_edit && lab.ai_enabled && (
        <Card withBorder bg="var(--mantine-color-gray-0)" mb="sm" p="sm">
          <Text fw={600} size="sm">{t('lab.aiTitle')}</Text>
          <Text size="xs" c="dimmed" mb={6}>{t('lab.aiHint')}</Text>
          {lab.ai_state === 'reading' ? (
            <Group gap="xs"><Loader size="sm" /><Text size="sm">{t('lab.reading')}</Text></Group>
          ) : pdfs.length === 0 ? <Text size="sm" c="dimmed">{t('lab.noPdf')}</Text> : (
            <Group gap="xs" align="flex-end">
              <Select size="xs" w={300} placeholder={t('lab.choosePdf')} value={chosenPdf}
                data={pdfs.map((a) => ({ value: a.file_id, label: a.filename }))} onChange={setPdfId} />
              <Button size="xs" loading={read.isPending} disabled={!chosenPdf} onClick={() => chosenPdf && read.mutate(chosenPdf)}>{t('lab.read')}</Button>
            </Group>
          )}
          {lab.ai_state === 'error' && <Alert mt="xs" color="red" variant="light" py={6}>{t('lab.aiError')}: {lab.ai_message}</Alert>}
        </Card>
      )}
      <Modal opened={lab.ai_state === 'ready' && !!lab.ai_draft && lab.can_edit} onClose={() => undefined} withCloseButton={false}
        fullScreen title={t('lab.reviewTitle')}>
        {lab.ai_state === 'ready' && lab.ai_draft && <AiReview rec={rec} lab={lab} classes={cls} onDone={put} />}
      </Modal>

      {lab.can_edit && (
        <Group gap="xs" align="flex-end" mb="sm">
          <Select size="xs" w={340} label={t('lab.template')} searchable clearable value={d.template_id}
            data={(templates.data ?? []).map((x) => ({ value: x.id!, label: pick(x, 'name') }))} onChange={loadTemplate} />
          {tpl?.acceptance === 'concrete' && (
            <>
              <NumberInput size="xs" w={150} label={t('lab.specimensManual')} min={1} max={100} value={specimens} onChange={(v) => setSpecimens(v === '' ? '' : Number(v))} />
              <Button size="xs" variant="light" onClick={() => loadTemplate(d.template_id)}>{t('lab.generate')}</Button>
            </>
          )}
        </Group>
      )}
      {!lab.can_edit && tpl && <Text size="sm" mb="xs">{t('lab.template')}: {pick(tpl, 'name')}</Text>}
      <HeaderFields d={d} set={set} editable={lab.can_edit} classes={cls} />
      <Text fw={600} size="sm" mt="md" mb={4}>{t('lab.lines')}</Text>
      <LinesTabs lines={d.lines} onChange={(l) => set({ lines: l })} editable={lab.can_edit} fck={d.fck} />
      {lab.can_edit && <Button mt="sm" loading={save.isPending} disabled={!dirty} onClick={() => save.mutate()}>{t('lab.save')}</Button>}

      {(lab.can_decide || lab.decision) && (
        <Card withBorder mt="md" p="sm" bg="var(--mantine-color-red-0)">
          <Text fw={600} size="sm">{t('lab.decisionTitle')}</Text>
          {lab.can_decide ? (
            <Stack gap="xs" mt={6}>
              <Select size="xs" w={300} clearable value={decision.d} data={DECISIONS.map((x) => ({ value: x, label: t(`lab.d.${x}`) }))}
                onChange={(v) => setDecision({ ...decision, d: v })} />
              <Textarea size="xs" autosize minRows={2} placeholder={t('lab.decisionNote')} value={decision.note}
                onChange={(e) => setDecision({ ...decision, note: e.currentTarget.value })} />
              <Group><Button size="xs" loading={decide.isPending} onClick={() => decide.mutate()}>{t('lab.saveDecision')}</Button></Group>
            </Stack>
          ) : (
            <Text size="sm">{t(`lab.d.${lab.decision}`)}{lab.decision_note ? ` — ${lab.decision_note}` : ''}
              {lab.decision_at ? <Text span size="xs" c="dimmed"> · {fmtDate(lab.decision_at, true)}</Text> : null}</Text>
          )}
        </Card>
      )}
    </Card>
  );
}
