import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRight,
  CircleCheck,
  ClipboardList,
  FileCheck,
  History,
  Info,
  Paperclip,
  Plus,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { api } from '../api'
import { useConfirm } from '../components/ConfirmDialog'
import { PageHeader } from '../components/PageHeader'
import { Pager, type PerPage } from '../components/Pager'
import { SegmentedControl } from '../components/SegmentedControl'
import { useToast } from '../components/Toast'
import { useRole } from '../context/RoleContext'
import { useRangeSelect } from '../hooks/useRangeSelect'
import {
  type JoinStatus,
  type SubmitAuditEntry,
  appendSubmitAudit,
  clearHandoff,
  computeIdentityJoin,
  joinSignature,
  readHandoff,
  readSubmitAudit,
} from '../lib/accession'
import { colIndex, splitCsv } from '../lib/csv'
import type { SampleRow, SubmitRunIn } from '../types'

// Submit samplesheet (§5.1) — the pipeline's front door: registers a run + its samples BEFORE
// processing. Compose ≠ execute: this screen only records run/sample metadata and hands off to
// the preflight gate; it never starts a tool. Submit now TRIGGERS the real POST /api/runs boundary
// (the API drives the pipeline; the core still never runs a tool). Its gate: sample_metadata is
// REQUIRED and the samplesheet ⋈ metadata identity join must be human-approved first (UIC-11).

type RunMeta = { runName: string; study: string; assay: string; platform: string }

// The four dual-barcode libraries seeded in the mock (dc.html): the GIAB trio + NA12878.
const SEED_SAMPLES: SampleRow[] = [
  { sample: 'HG002', type: 'Whole blood', i7: 'AGGCGAAG', i5: 'CTGATCGT', study: 'GIAB-QC' },
  { sample: 'HG003', type: 'Whole blood', i7: 'GAACCGCG', i5: 'TCTGATCG', study: 'GIAB-QC' },
  { sample: 'HG004', type: 'Saliva', i7: 'CTCACCAA', i5: 'GAGTCACT', study: 'GIAB-QC' },
  { sample: 'NA12878', type: 'Whole blood', i7: 'TCCGGAGA', i5: 'ACGTCCTG', study: 'GIAB-QC' },
]
const SEED_META: RunMeta = { runName: 'RUN-2026-07-09-A', study: 'GIAB-QC', assay: 'WES', platform: 'NovaSeq X' }

// Per-sample metadata parsed from a sample_metadata.csv (the LIMS/subject sheet, distinct from the
// samplesheet). subject_id is intake identity — kept CLIENT-SIDE for now (POST /api/runs has no
// subject field yet; a labelled seam), tissue is the corroborating column for the identity join.
type SampleMeta = { subject_id?: string; tissue?: string }
type ParsedSheet = { meta: Partial<RunMeta>; samples: SampleRow[] }

// Demo seed metadata paired with SEED_SAMPLES so the out-of-box join is clean + approvable (each
// tissue corroborates the sample's type). Clearly labelled as seeded — a real run attaches its own.
const SEED_SAMPLE_META: Record<string, SampleMeta> = {
  HG002: { subject_id: 'SUBJ-24001', tissue: 'Whole blood' },
  HG003: { subject_id: 'SUBJ-24002', tissue: 'Whole blood' },
  HG004: { subject_id: 'SUBJ-24003', tissue: 'Saliva' },
  NA12878: { subject_id: 'SUBJ-24004', tissue: 'Whole blood' },
}

// Sample type controlled vocabulary (design invariant: a controlled vocab, not free text).
const SAMPLE_TYPES = ['Whole blood', 'Saliva', 'FFPE', 'Buccal swab']

const BASE_REGIONS = ['US · bh.basespace.illumina.com', 'EU · euw2.sh.basespace.illumina.com']

// Importable runs listed once BaseSpace is connected. Import is wired to reveal the seeded GIAB
// set (the mock has no real per-run payload); the selected row is cosmetic for the demo.
const BASE_RUNS = [
  { id: '20260709_NB551_0042', proj: 'GIAB-QC', samples: 4, date: 'Jul 9, 2026' },
  { id: '20260708_NB551_0041', proj: 'Cardio-panel', samples: 28, date: 'Jul 8, 2026' },
  { id: '20260706_MS_0193', proj: 'Onco-heme', samples: 12, date: 'Jul 6, 2026' },
]

const RUN_FIELDS: { key: keyof RunMeta; label: string; hint: string }[] = [
  { key: 'runName', label: 'Run name', hint: 'unique per flow cell' },
  { key: 'study', label: 'Study / project', hint: 'propagates to every sample' },
  { key: 'assay', label: 'Assay', hint: 'WES · WGS · panel' },
  { key: 'platform', label: 'Sequencer', hint: 'instrument model' },
]

const INPUT_CLS =
  'w-full rounded-[7px] border border-line bg-card px-[9px] py-[7px] font-mono text-[12px] text-text outline-none focus:border-accent'

// Identity-join status → token styles (verdict/gate palette; never a hardcoded hex). Matched reads
// proceed, weak reads hold, everything ambiguous reads escalate so a mixup is impossible to miss.
const JOIN_STATUS_META: Record<JoinStatus, { label: string; cls: string; dot: string }> = {
  matched: { label: 'Matched', cls: 'border-proceed-bd bg-proceed-bg text-proceed-fg', dot: 'bg-proceed' },
  conflict: { label: 'Conflict', cls: 'border-escalate-bd bg-escalate-bg text-escalate-fg', dot: 'bg-escalate' },
  duplicate: { label: 'Duplicate', cls: 'border-escalate-bd bg-escalate-bg text-escalate-fg', dot: 'bg-escalate' },
  unmatched: { label: 'Unmatched', cls: 'border-escalate-bd bg-escalate-bg text-escalate-fg', dot: 'bg-escalate' },
  weak: { label: 'Weak match', cls: 'border-hold-bd bg-hold-bg text-hold-fg', dot: 'bg-hold' },
}
const JOIN_STATUS_ORDER: JoinStatus[] = ['matched', 'conflict', 'duplicate', 'unmatched', 'weak']

// splitCsv / colIndex live in lib/csv.ts, shared with the Accession screen (one tolerant parser
// instead of a private copy per screen). parseSamplesheet / parseMetadata below use the imports.

// Parse an Illumina v2 SampleSheet ([Header] key-values + a [*_Data] section) OR a plain CSV
// (Sample_ID,Sample_Type,index,index2,Study). A missing field is a signal, not a crash (boundary
// tolerance) — an unrecognized column just yields empty/defaulted cells.
function parseSamplesheet(text: string): ParsedSheet {
  const lines = text.split(/\r?\n/)
  const meta: Partial<RunMeta> = {}
  let header: string[] = []
  let dataStart = -1
  let inHeader = false
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i].trim()
    if (!raw) continue
    if (/^\[header\]/i.test(raw)) {
      inHeader = true
      continue
    }
    if (/^\[.*data\]/i.test(raw)) {
      header = splitCsv(lines[i + 1] ?? '')
      dataStart = i + 2
      break
    }
    if (/^\[/.test(raw)) {
      inHeader = false
      continue
    }
    if (inHeader) {
      const [k, v] = splitCsv(raw)
      const key = (k ?? '').toLowerCase()
      if (v) {
        if (['run name', 'experiment name', 'run_name'].includes(key)) meta.runName = v
        else if (key === 'assay') meta.assay = v
        else if (['instrument type', 'instrument platform', 'platform'].includes(key)) meta.platform = v
      }
    }
  }
  // Plain-CSV fallback: no [Data] section → the first non-empty line is the column header.
  if (dataStart === -1) {
    const first = lines.findIndex((l) => l.trim())
    header = splitCsv(lines[first] ?? '')
    dataStart = first + 1
  }
  const cSample = colIndex(header, ['sample_id', 'sample', 'sampleid', 'sample name'])
  const cType = colIndex(header, ['sample_type', 'type', 'tissue', 'library_type'])
  const cI7 = colIndex(header, ['index', 'i7_index_id', 'i7', 'index1'])
  const cI5 = colIndex(header, ['index2', 'i5_index_id', 'i5'])
  const cStudy = colIndex(header, ['study', 'sample_project', 'project'])
  const samples: SampleRow[] = []
  for (let i = dataStart; i < lines.length; i++) {
    const raw = lines[i]
    if (!raw || !raw.trim()) continue
    if (/^\[/.test(raw.trim())) break // next section — stop
    const parts = splitCsv(raw)
    const sample = (cSample >= 0 ? parts[cSample] : parts[0]) ?? ''
    if (!sample) continue
    samples.push({
      sample,
      type: (cType >= 0 ? parts[cType] : '') || 'Whole blood',
      i7: cI7 >= 0 ? (parts[cI7] ?? '') : '',
      i5: cI5 >= 0 ? (parts[cI5] ?? '') : '',
      study: (cStudy >= 0 ? parts[cStudy] : '') || '',
    })
  }
  if (!meta.study && samples[0]?.study) meta.study = samples[0].study
  return { meta, samples }
}

// Parse a sample_metadata.csv → per-sample subject_id + tissue, keyed by sample id.
function parseMetadata(text: string): Record<string, SampleMeta> {
  const lines = text.split(/\r?\n/).filter((l) => l.trim())
  if (!lines.length) return {}
  const header = splitCsv(lines[0])
  const cSample = colIndex(header, ['sample_id', 'sample', 'sampleid'])
  const cSubject = colIndex(header, ['subject_id', 'subject', 'patient_id', 'individual'])
  const cTissue = colIndex(header, ['tissue', 'sample_type', 'source'])
  const out: Record<string, SampleMeta> = {}
  for (let i = 1; i < lines.length; i++) {
    const parts = splitCsv(lines[i])
    const sample = (cSample >= 0 ? parts[cSample] : parts[0]) ?? ''
    if (!sample) continue
    out[sample] = {
      subject_id: cSubject >= 0 ? parts[cSubject] || undefined : undefined,
      tissue: cTissue >= 0 ? parts[cTissue] || undefined : undefined,
    }
  }
  return out
}

export function Submit() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const confirm = useConfirm()
  const { session, actor } = useRole()
  const [submitting, setSubmitting] = useState(false)
  const [method, setMethod] = useState<'upload' | 'basespace'>('upload')
  const [meta, setMeta] = useState<RunMeta>(SEED_META)
  const [samples, setSamples] = useState<SampleRow[]>(SEED_SAMPLES)
  // Real file parsing: the parsed samplesheet name + the sample_metadata sheet (subject/tissue)
  // keyed by sample id. Seeded metadata pairs the seeded samples so the default join is clean.
  const [uploadName, setUploadName] = useState<string | null>(null)
  const [sampleMeta, setSampleMeta] = useState<Record<string, SampleMeta>>(SEED_SAMPLE_META)
  const [metaName, setMetaName] = useState<string | null>('seeded demo metadata · 4 subjects')
  const [dragging, setDragging] = useState(false)
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState<PerPage>('25') // UIC-11a: real 25/50/100 per-page control
  const [addCount, setAddCount] = useState('1')
  const sheetInput = useRef<HTMLInputElement>(null)
  const metaInput = useRef<HTMLInputElement>(null)

  // BaseSpace connect flow. `imported` gates whether run details + samples are populated in
  // BaseSpace mode — blank until Import, per the design. Upload mode is always populated.
  const [baseConnected, setBaseConnected] = useState(false)
  const [baseRegion, setBaseRegion] = useState(BASE_REGIONS[0])
  const [baseToken, setBaseToken] = useState('')
  const [selectedRun, setSelectedRun] = useState(BASE_RUNS[0].id)
  const [imported, setImported] = useState(false)

  const loaded = method === 'upload' || imported
  const count = loaded ? samples.length : 0
  // The rows shown before any real samplesheet is parsed are the demo seed (SEED_SAMPLES), not
  // parsed data — flag it so the Samples header can label the count "seeded demo" instead of
  // passing it off as a parsed count (mirrors the seeded metadata label). A real parse
  // (onSheetFile) sets uploadName, which clears the flag.
  const seeded = method === 'upload' && uploadName == null
  // Paginate the sample table so a 100+ sample flowcell stays navigable (scale-aware UI rule).
  const per = Number(perPage)
  const pages = Math.max(1, Math.ceil(samples.length / per))
  const curPage = Math.min(page, pages)
  const pageStart = (curPage - 1) * per
  const pagedSamples = samples.slice(pageStart, pageStart + per)

  // Sample multi-select via the shared range-select model (UIC-3): ids are the flat render-order
  // index strings; a plain click toggles one, a shift-click extends a contiguous range.
  const allIds = useMemo(() => samples.map((_, i) => String(i)), [samples])
  const sel = useRangeSelect(allIds)
  const pageIds = pagedSamples.map((_, li) => String(pageStart + li))
  const pageSelCount = pageIds.filter((id) => sel.isSelected(id)).length

  // Client-side identity audit (localStorage) — the join, its edits, and the human approval land
  // here, shaped like the Admin Activity feed. A labelled seam (no backend subject field).
  const [audit, setAudit] = useState<SubmitAuditEntry[]>(() => readSubmitAudit())
  const [auditOpen, setAuditOpen] = useState(false)
  const actorId = session?.id ?? actor.id
  const logAudit = useCallback(
    (action: string, detail: string) => {
      setAudit(appendSubmitAudit({ at: new Date().toISOString(), actor: actorId, action, detail }))
    },
    [actorId],
  )

  // Sample identity join (UIC-11): samplesheet ⋈ sample_metadata, corroborated on Sample_ID + tissue.
  const join = useMemo(() => computeIdentityJoin(samples, sampleMeta), [samples, sampleMeta])
  const sig = useMemo(() => joinSignature(join), [join])
  // Approval is bound to the join SIGNATURE, so any edit (a sample type, a re-attached metadata sheet,
  // an added/removed row) auto-invalidates it — a human re-confirms identity after any change.
  const [approvedSig, setApprovedSig] = useState<string | null>(null)
  const joinApproved = approvedSig !== null && approvedSig === sig
  const [joinFilter, setJoinFilter] = useState<'attention' | 'all'>('attention')
  const [joinPage, setJoinPage] = useState(1)
  const [joinPer, setJoinPer] = useState<PerPage>('25')
  useEffect(() => setJoinPage(1), [joinFilter])
  const joinRows = joinFilter === 'attention' ? join.rows.filter((r) => r.status !== 'matched') : join.rows
  const joinPerN = Number(joinPer)
  const joinPages = Math.max(1, Math.ceil(joinRows.length / joinPerN))
  const joinCurPage = Math.min(joinPage, joinPages)
  const joinPageRows = joinRows.slice((joinCurPage - 1) * joinPerN, (joinCurPage - 1) * joinPerN + joinPerN)

  const canSubmit = count > 0 && join.metadataPresent && joinApproved
  const submitBlockedReason = !join.metadataPresent
    ? 'Attach sample metadata first'
    : join.blocking > 0
      ? `Resolve ${join.blocking} identity issue${join.blocking === 1 ? '' : 's'}`
      : !joinApproved
        ? 'Approve the identity join'
        : ''

  // Accession → Submit handoff: if the Sample accessioning screen sent subject/tissue metadata,
  // pre-attach it here (the same client-side merge an uploaded sample_metadata.csv gets) and clear
  // the one-shot courier. subject_id stays client-side — the POST /api/runs body is unchanged.
  useEffect(() => {
    const handoff = readHandoff()
    if (!handoff) return
    const n = Object.keys(handoff).length
    if (!n) return
    setSampleMeta(handoff)
    setMetaName(`from Sample accessioning · ${n} subjects`)
    setSamples((rows) => rows.map((r) => (handoff[r.sample]?.tissue ? { ...r, type: handoff[r.sample].tissue as string } : r)))
    clearHandoff()
    logAudit('attach-metadata', `Loaded ${n} subjects from Sample accessioning (client-side)`)
    toast(`Loaded ${n} subjects from Sample accessioning — subject ids held client-side.`, 'info')
  }, [toast, logAudit])

  function setField(key: keyof RunMeta, value: string) {
    setMeta((m) => ({ ...m, [key]: value }))
  }
  function patchSample(i: number, patch: Partial<SampleRow>) {
    setSamples((rows) => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  }
  // Append N blank rows in one action (a 100-sample plate shouldn't be 100 clicks). Bounded so a
  // fat-fingered count can't lock the tab.
  function addSamples(n: number) {
    const k = Math.max(1, Math.min(500, Math.floor(n) || 1))
    setSamples((rows) => [
      ...rows,
      ...Array.from({ length: k }, () => ({ sample: '', type: SAMPLE_TYPES[0], i7: '', i5: '', study: meta.study })),
    ])
  }
  async function removeSelected() {
    const idxs = [...sel.selected].map(Number).filter((n) => Number.isInteger(n))
    const n = idxs.length
    if (n === 0) return
    const ok = await confirm({
      title: `Remove ${n} sample${n === 1 ? '' : 's'} from this draft?`,
      body: 'Removed from this submission draft only — nothing is deleted downstream.',
      confirmLabel: 'Remove',
      tone: 'danger',
    })
    if (!ok) return
    const drop = new Set(idxs)
    setSamples((rows) => rows.filter((_, j) => !drop.has(j)))
    sel.clear()
  }

  // Adopt the metadata tissue onto the samplesheet type — the one-click resolution for a tissue
  // CONFLICT. Recomputes the join (auto-invalidating any stale approval) and is audited.
  function adoptMetadataTissue(sample: string, tissue: string) {
    setSamples((rows) => rows.map((r) => (r.sample === sample ? { ...r, type: tissue } : r)))
    logAudit('edit-join', `Set ${sample} sample type → "${tissue}" (adopt metadata tissue)`)
    toast(`${sample} sample type set to "${tissue}" from metadata.`, 'success')
  }

  // Parse a dropped/selected samplesheet for real. Merges any already-loaded sample_metadata tissue
  // onto the fresh rows so the identity join reflects the attached metadata immediately.
  async function onSheetFile(file: File) {
    try {
      const parsed = parseSamplesheet(await file.text())
      if (parsed.samples.length === 0) {
        toast(`No sample rows found in ${file.name}. Expected an Illumina v2 sheet or a CSV with Sample_ID/index columns.`, 'error')
        return
      }
      const merged = parsed.samples.map((s) => {
        const m = sampleMeta[s.sample]
        return m?.tissue ? { ...s, type: m.tissue } : s
      })
      setSamples(merged)
      setMeta((prev) => ({ ...prev, ...parsed.meta }))
      setUploadName(file.name)
      setPage(1)
      sel.clear()
      toast(`Parsed ${parsed.samples.length} samples from ${file.name}.`, 'success')
    } catch (e) {
      toast(`Couldn't read ${file.name} — ${e instanceof Error ? e.message : String(e)}`, 'error')
    }
  }

  // Parse the sample_metadata.csv (LIMS/subject sheet, G2) and merge tissue onto matching samples.
  // subject_id is held client-side (a labelled seam — POST /api/runs carries no subject field yet).
  async function onMetaFile(file: File) {
    try {
      const map = parseMetadata(await file.text())
      const n = Object.keys(map).length
      if (n === 0) {
        toast(`No rows found in ${file.name}. Expected columns like Sample_ID, Subject_ID, Tissue.`, 'error')
        return
      }
      setSampleMeta(map)
      setMetaName(file.name)
      setSamples((rows) => rows.map((r) => (map[r.sample]?.tissue ? { ...r, type: map[r.sample].tissue as string } : r)))
      logAudit('attach-metadata', `Attached ${file.name} · ${n} subjects`)
      toast(`Attached metadata for ${n} samples from ${file.name}.`, 'success')
    } catch (e) {
      toast(`Couldn't read ${file.name} — ${e instanceof Error ? e.message : String(e)}`, 'error')
    }
  }

  function clearMetadata() {
    setSampleMeta({})
    setMetaName(null)
    logAudit('detach-metadata', 'Removed attached sample_metadata (identity join re-opened)')
  }

  // Approve the identity join — the explicit human confirmation gate before a run proceeds. Only
  // reachable when the join is clean (no blocking rows); a confirm dialog names the consequence.
  async function approveJoin() {
    if (join.blocking > 0 || joinApproved) return
    const ok = await confirm({
      title: 'Approve the sample-identity join?',
      body: `Confirms all ${join.rows.length} sample${join.rows.length === 1 ? '' : 's'} match sample_metadata on Sample_ID plus a corroborating column (tissue). Submit stays disabled until you approve; any later edit re-opens this gate. Recorded in the identity audit.`,
      confirmLabel: 'Approve join',
    })
    if (!ok) return
    setApprovedSig(sig)
    logAudit('approve-join', `Approved identity join · ${join.rows.length} samples · run ${meta.runName || '—'}`)
    toast('Sample-identity join approved — submit is now enabled.', 'success')
  }

  function connectBase() {
    if (baseToken.trim()) setBaseConnected(true)
  }
  function disconnectBase() {
    setBaseConnected(false)
    setBaseToken('')
    setImported(false)
  }
  function importRun(id: string) {
    // Reveal the seeded GIAB set as the imported payload (demo stand-in). No execution.
    setSelectedRun(id)
    setSamples(SEED_SAMPLES)
    setMeta(SEED_META)
    setImported(true)
    sel.clear()
  }

  // Submit registers the run, then hands off to the execution boundary (POST /api/runs) — the
  // API triggers the pipeline driver (the core still never runs a tool). Gated on an approved
  // identity join. We poll intake-status and navigate to the run once processing completes.
  async function submit() {
    if (!canSubmit) return
    setSubmitting(true)
    const body: SubmitRunIn = {
      run_name: meta.runName,
      study: meta.study,
      assay: meta.assay,
      platform: meta.platform,
      samples: samples.map((s) => ({ sample: s.sample, type: s.type, i7: s.i7, i5: s.i5, study: s.study })),
    }
    try {
      const ack = await api.submitRun(body)
      logAudit('submit', `Submitted run ${ack.run_id} · ${body.samples.length} samples (identity join approved)`)
      // Scale-aware summary: a 100-sample flowcell can't dump every name into a toast — list up to 5.
      const summarize = (arr: string[]) => (arr.length <= 5 ? arr.join(', ') : `${arr.length} samples`)
      const procMsg = ack.processed_samples.length
        ? `Processing ${summarize(ack.processed_samples)}`
        : 'No samples with reads on disk to process'
      const skip = ack.skipped_samples.length ? ` · skipped ${summarize(ack.skipped_samples)} (no reads on disk for this demo)` : ''
      toast(`${procMsg} through the pipeline…${skip}`, 'info')
      const poll = async (): Promise<void> => {
        try {
          const st = await api.intakeStatus(ack.run_id)
          if (st.status === 'complete') {
            toast(`Run ${ack.run_id} processed — opening decision cards.`, 'success')
            navigate(`/runs/${ack.run_id}`)
          } else if (st.status === 'failed') {
            toast(`Pipeline failed — ${st.error ?? 'unknown error'}`, 'error')
            setSubmitting(false)
          } else {
            setTimeout(() => void poll(), 2500)
          }
        } catch (e) {
          // A 404 (the in-memory job registry lost the run — e.g. an API restart) or a network
          // blip is terminal for this poller: without this catch the recursion rejects silently and
          // the button spins "Processing…" forever. Stop, clear the state, and surface it honestly.
          toast(
            `Lost track of run ${ack.run_id} — ${e instanceof Error ? e.message : String(e)}. Check the Runs list.`,
            'error',
          )
          setSubmitting(false)
        }
      }
      void poll()
    } catch (e) {
      toast(`Couldn't submit run — ${e instanceof Error ? e.message : String(e)}`, 'error')
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-[1080px]">
      {/* UIC-1: the left-nav names this page — no eyebrow/subtitle prose. The identity-required and
          guardrail notes below are explicit safety warnings and stay. */}
      <PageHeader title="New submission" />

      {/* method toggle */}
      <div className="mt-[18px]">
        <SegmentedControl<'upload' | 'basespace'>
          value={method}
          onChange={setMethod}
          options={[
            {
              value: 'upload',
              label: (
                <span className="inline-flex items-center gap-[7px]">
                  <Upload size={15} strokeWidth={1.8} />
                  Upload samplesheet
                </span>
              ),
            },
            {
              value: 'basespace',
              label: (
                <span className="inline-flex items-center gap-[7px]">
                  <RefreshCw size={15} strokeWidth={1.8} />
                  Pull from BaseSpace
                </span>
              ),
            },
          ]}
        />
      </div>

      {/* UPLOAD panel — real samplesheet parse (sample_metadata attaches in the identity section) */}
      {method === 'upload' && (
        <>
          {/* Hidden real input; the drop zone / buttons trigger it. Reset value on change so the
              same file can be re-selected. */}
          <input
            ref={sheetInput}
            type="file"
            accept=".csv,.txt,.tsv"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) void onSheetFile(f)
              e.target.value = ''
            }}
          />
          <div
            onClick={() => sheetInput.current?.click()}
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragging(false)
              const f = e.dataTransfer.files?.[0]
              if (f) void onSheetFile(f)
            }}
            className={`mt-[14px] flex cursor-pointer items-center gap-[18px] rounded-[14px] border-[1.5px] border-dashed p-[26px] transition-colors ${
              dragging ? 'border-accent bg-accent-weak' : 'border-line-strong bg-card hover:border-accent'
            }`}
          >
            <div className="flex h-[46px] w-[46px] shrink-0 items-center justify-center rounded-xl bg-accent-weak">
              <Upload size={23} strokeWidth={1.7} className="text-accent-strong" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[14px] font-semibold text-text">Drop a samplesheet CSV, or click to browse</div>
              <div className="mt-0.5 text-[12px] text-text-2">
                Illumina v2 sample sheet or a plain CSV with{' '}
                <span className="font-mono">Sample_ID, Sample_Type, index, index2, Study</span>. Run name &amp; study
                are auto-detected from the header.
              </div>
            </div>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                sheetInput.current?.click()
              }}
              className="whitespace-nowrap rounded-[9px] border border-line-strong bg-card px-[15px] py-[9px] text-[13px] font-medium text-accent-strong"
            >
              Browse files
            </button>
          </div>
          {/* Real parsed chip — appears only after a file is actually parsed. */}
          {uploadName && (
            <div className="mt-[10px] flex items-center gap-[11px] rounded-[11px] border border-proceed-bd bg-proceed-bg px-[14px] py-[11px]">
              <FileCheck size={18} strokeWidth={1.9} className="shrink-0 text-proceed" />
              <div className="min-w-0 flex-1">
                <div className="font-mono text-[12.5px] font-semibold text-proceed-fg">{uploadName}</div>
                <div className="text-[11.5px] text-text-2">
                  Parsed <strong className="text-text">{samples.length}</strong> samples
                  {meta.runName ? (
                    <>
                      {' '}
                      · detected run <span className="font-mono text-text">{meta.runName}</span>
                    </>
                  ) : null}
                  {meta.study ? (
                    <>
                      {' '}
                      · study <span className="font-mono text-text">{meta.study}</span>
                    </>
                  ) : null}
                  . Review below before submitting.
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* BASESPACE panel — connect card gates the importable run list */}
      {method === 'basespace' && (
        <div className="mt-[14px] overflow-hidden rounded-[14px] border border-line bg-card shadow-card">
          {!baseConnected ? (
            <div className="px-[18px] py-4">
              <div className="flex items-center gap-[11px]">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-weak">
                  <RefreshCw size={17} strokeWidth={1.8} className="text-accent-strong" />
                </div>
                <div className="flex-1">
                  <div className="text-[13.5px] font-semibold text-text">Connect to BaseSpace Sequence Hub</div>
                  <div className="mt-px text-[11.5px] text-text-2">
                    Authenticate to list and import runs from your account.
                  </div>
                </div>
                <span className="inline-flex shrink-0 items-center gap-[5px] text-[11px] text-text-3">
                  <span className="h-1.5 w-1.5 rounded-full bg-text-3" />
                  Not connected
                </span>
              </div>
              <div className="mt-[15px] flex flex-col gap-[13px]">
                <div>
                  <label className="mb-[5px] block text-[11px] font-semibold text-text-2">Region</label>
                  <select
                    value={baseRegion}
                    onChange={(e) => setBaseRegion(e.target.value)}
                    className="w-full cursor-pointer rounded-lg border border-line-strong bg-card px-[11px] py-2 text-[12.5px] text-text outline-none"
                  >
                    {BASE_REGIONS.map((rg) => (
                      <option key={rg} value={rg}>
                        {rg}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-[5px] block text-[11px] font-semibold text-text-2">Access token</label>
                  <input
                    type="password"
                    value={baseToken}
                    onChange={(e) => setBaseToken(e.target.value)}
                    placeholder="Paste a BaseSpace API access token"
                    className="w-full rounded-lg border border-line-strong bg-card px-[11px] py-2 font-mono text-[12.5px] text-text outline-none"
                  />
                  <div className="mt-[5px] text-[10px] text-text-3">
                    Held for this session only. Use a scoped token (read + run access) — never your account password.
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-[12px]">
                  <button
                    type="button"
                    onClick={connectBase}
                    disabled={!baseToken.trim()}
                    className={`inline-flex items-center gap-[7px] rounded-lg px-[15px] py-2 text-[12.5px] font-semibold ${
                      baseToken.trim()
                        ? 'cursor-pointer bg-accent text-white'
                        : 'cursor-not-allowed bg-card-3 text-text-3'
                    }`}
                  >
                    <CircleCheck size={14} strokeWidth={1.9} />
                    Connect
                  </button>
                  <span className="text-[11px] text-text-3">
                    or use single sign-on via your org&apos;s Illumina account
                  </span>
                </div>
              </div>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-[10px] border-b border-line px-4 py-[13px]">
                <div className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-lg bg-accent-weak">
                  <RefreshCw size={16} strokeWidth={1.8} className="text-accent-strong" />
                </div>
                <div className="flex-1">
                  <div className="text-[13px] font-semibold text-text">BaseSpace Sequence Hub</div>
                  <div className="mt-px flex items-center gap-[5px] text-[11.5px] text-proceed-fg">
                    <span className="h-1.5 w-1.5 rounded-full bg-proceed" />
                    Connected as <span className="font-mono">lab-ops@giab</span>
                  </div>
                </div>
                <button
                  type="button"
                  className="rounded-lg border border-line-strong bg-card px-[11px] py-1.5 text-[12px] text-text-2"
                >
                  Refresh
                </button>
                <button
                  type="button"
                  onClick={disconnectBase}
                  className="rounded-lg border border-line-strong bg-card px-[11px] py-1.5 text-[12px] text-text-2"
                >
                  Disconnect
                </button>
              </div>
              <div className="p-2">
                {BASE_RUNS.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => setSelectedRun(r.id)}
                    className="flex w-full items-center gap-[13px] rounded-[9px] px-3 py-[11px] text-left hover:bg-card-2"
                  >
                    <span className="flex h-[17px] w-[17px] shrink-0 items-center justify-center rounded-full border-2 border-line-strong">
                      {selectedRun === r.id && <span className="h-[9px] w-[9px] rounded-full bg-accent" />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block font-mono text-[12.5px] font-semibold text-text">{r.id}</span>
                      <span className="block text-[11px] text-text-3">
                        {r.proj} · {r.date}
                      </span>
                    </span>
                    <span className="whitespace-nowrap font-mono text-[11.5px] text-text-2">{r.samples} samples</span>
                    <span
                      role="button"
                      tabIndex={0}
                      onClick={(e) => {
                        e.stopPropagation()
                        importRun(r.id)
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          e.stopPropagation()
                          importRun(r.id)
                        }
                      }}
                      className="whitespace-nowrap rounded-[7px] border border-[#cfe0fb] bg-accent-weak px-3 py-1.5 text-[12px] font-medium text-accent-strong"
                    >
                      Import
                    </span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* RUN DETAILS — applies to every sample; blank until Import in BaseSpace mode */}
      <div className="mt-[14px] overflow-hidden rounded-[14px] border border-line bg-card shadow-card">
        <div className="border-b border-line px-[18px] py-[14px]">
          <div className="text-[14.5px] font-semibold text-text">Run details</div>
          <div className="mt-0.5 text-[12px] text-text-2">Applied to every sample in this submission.</div>
        </div>
        <div className="grid grid-cols-4 gap-[13px] px-[18px] py-4">
          {RUN_FIELDS.map((f) => (
            <div key={f.key}>
              <label className="mb-[5px] block text-[11px] font-semibold text-text-2">{f.label}</label>
              <input
                value={loaded ? meta[f.key] : ''}
                onChange={(e) => setField(f.key, e.target.value)}
                readOnly={!loaded}
                placeholder={loaded ? '' : 'Populates on import'}
                className={INPUT_CLS}
              />
              <div className="mt-1 text-[10px] text-text-3">{f.hint}</div>
            </div>
          ))}
        </div>
      </div>

      {/* SAMPLES — editable barcode table (empty until Import in BaseSpace mode) */}
      <div className="mt-[14px] overflow-hidden rounded-[14px] border border-line bg-card shadow-card">
        <div className="flex items-center gap-[10px] border-b border-line px-[18px] py-[14px]">
          <div className="flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[14.5px] font-semibold text-text">Samples · {count}</span>
              {seeded && (
                <span className="inline-flex items-center rounded-full border border-line-strong bg-card-2 px-2 py-0.5 text-[10.5px] font-medium text-text-3">
                  seeded demo — replace by uploading
                </span>
              )}
            </div>
            <div className="mt-0.5 text-[12px] text-text-2">
              Sample name, type, and dual barcodes resolve each library at demux and intake.
            </div>
          </div>
          {method === 'upload' && (
            <div className="flex items-center gap-2">
              {/* Bulk-remove the checkbox selection (confirmed). */}
              {sel.selected.size > 0 && (
                <button
                  type="button"
                  onClick={() => void removeSelected()}
                  className="inline-flex items-center gap-[6px] rounded-lg border border-escalate-bd bg-escalate-bg px-3 py-[7px] text-[12.5px] font-medium text-escalate-fg transition-[filter] hover:brightness-95"
                >
                  <Trash2 size={14} strokeWidth={1.9} />
                  Remove {sel.selected.size}
                </button>
              )}
              {/* Add N samples at once. */}
              <div className="flex items-center gap-1 rounded-lg border border-line-strong bg-card px-1.5 py-1">
                <input
                  type="number"
                  min={1}
                  max={500}
                  value={addCount}
                  onChange={(e) => setAddCount(e.target.value)}
                  className="w-11 rounded-[6px] bg-transparent px-1 py-1 text-center font-mono text-[12.5px] text-text outline-none"
                  aria-label="Number of samples to add"
                />
                <button
                  type="button"
                  onClick={() => addSamples(Number(addCount))}
                  className="inline-flex items-center gap-[6px] rounded-[7px] bg-accent-weak px-2.5 py-[6px] text-[12.5px] font-medium text-accent-strong"
                >
                  <Plus size={14} strokeWidth={2} />
                  Add
                </button>
              </div>
            </div>
          )}
        </div>
        <div className="grid grid-cols-[26px_30px_1.4fr_1.2fr_1fr_1fr_1.1fr] gap-[9px] border-b border-line bg-card-2 px-4 py-[9px] text-[9.5px] font-bold uppercase tracking-[.4px] text-text-3">
          <div className="flex items-center">
            {count > 0 && (
              <input
                type="checkbox"
                className="h-3.5 w-3.5 accent-accent"
                aria-label="Select all samples on this page"
                checked={pageIds.length > 0 && pageSelCount === pageIds.length}
                ref={(el) => {
                  if (el) el.indeterminate = pageSelCount > 0 && pageSelCount < pageIds.length
                }}
                onChange={() => sel.setMany(pageIds, pageSelCount !== pageIds.length)}
              />
            )}
          </div>
          <div>#</div>
          <div>Sample name</div>
          <div>Sample type</div>
          <div>i7 (index)</div>
          <div>i5 (index2)</div>
          <div>Study</div>
        </div>
        {count === 0 ? (
          <div className="px-4 py-[26px] text-center">
            <div className="mx-auto max-w-[380px] text-[12.5px] leading-relaxed text-text-2">
              No samples yet. Import a run from BaseSpace above — its samples (names, types, and barcodes) populate here
              for review.
            </div>
          </div>
        ) : (
          // Render only the current page; the global index `i` (not the page-local one) drives
          // patch/remove/select so edits land on the right row across pages.
          pagedSamples.map((s, li) => {
            const i = pageStart + li
            const id = String(i)
            const subject = sampleMeta[s.sample]?.subject_id
            const rowStatus = join.rows[i]?.status
            return (
              <div
                key={i}
                className={`grid grid-cols-[26px_30px_1.4fr_1.2fr_1fr_1fr_1.1fr] items-center gap-[9px] border-b border-line px-4 py-[9px] transition-colors ${
                  sel.isSelected(id) ? 'bg-accent-weak/40' : ''
                }`}
              >
                <div className="flex items-center">
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5 accent-accent"
                    aria-label={`Select ${s.sample || `sample ${i + 1}`}`}
                    checked={sel.isSelected(id)}
                    onChange={() => {}}
                    onClick={(e) => sel.toggle(id, e.shiftKey)}
                  />
                </div>
                <div className="font-mono text-[11.5px] text-text-3">{i + 1}</div>
                <div className="min-w-0">
                  <input value={s.sample} onChange={(e) => patchSample(i, { sample: e.target.value })} className={INPUT_CLS} />
                  <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                    {subject && (
                      <span className="truncate font-mono text-[9.5px] text-text-3" title={`Subject ${subject}`}>
                        subject {subject}
                      </span>
                    )}
                    {/* Per-row identity flag — surfaced inline for non-clean rows so a mixup is
                        impossible to miss even from the barcode table. */}
                    {rowStatus && rowStatus !== 'matched' && (
                      <span
                        className={`inline-flex items-center gap-1 rounded-full border px-1.5 py-px text-[9.5px] font-semibold ${JOIN_STATUS_META[rowStatus].cls}`}
                        title={join.rows[i]?.reason}
                      >
                        <span className={`h-1 w-1 rounded-full ${JOIN_STATUS_META[rowStatus].dot}`} />
                        {JOIN_STATUS_META[rowStatus].label}
                      </span>
                    )}
                  </div>
                </div>
                {/* A real dropdown; the current value is always an option even if a parsed tissue is
                    outside the vocab. */}
                <select
                  value={s.type}
                  onChange={(e) => patchSample(i, { type: e.target.value })}
                  className="w-full rounded-[7px] border border-line-strong bg-card-2 px-[9px] py-[7px] font-mono text-[11.5px] text-text-2 outline-none focus:border-accent"
                >
                  {[...new Set([...SAMPLE_TYPES, s.type])].filter(Boolean).map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <input value={s.i7} onChange={(e) => patchSample(i, { i7: e.target.value })} className={INPUT_CLS} />
                <input value={s.i5} onChange={(e) => patchSample(i, { i5: e.target.value })} className={INPUT_CLS} />
                <input value={s.study} onChange={(e) => patchSample(i, { study: e.target.value })} className={INPUT_CLS} />
              </div>
            )
          })
        )}
        {count > 0 && (
          <div className="px-4 pb-3">
            <Pager total={count} page={curPage} perPage={perPage} onPage={setPage} onPerPage={setPerPage} noun="samples" />
          </div>
        )}
      </div>

      {/* SAMPLE IDENTITY — the join gate (UIC-11). sample_metadata is REQUIRED and the samplesheet ⋈
          metadata identity join must be human-approved before submit. Sample-identity mixups are the
          highest-consequence error here, so every non-clean row blocks approval and is surfaced loudly. */}
      {count > 0 && (
        <div className="mt-[14px] overflow-hidden rounded-[14px] border border-line bg-card shadow-card">
          <div className="flex items-center gap-[10px] border-b border-line px-[18px] py-[14px]">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-weak">
              <ShieldCheck size={17} strokeWidth={1.8} className="text-accent-strong" />
            </div>
            <div className="flex-1">
              <div className="text-[14.5px] font-semibold text-text">Sample identity</div>
              <div className="mt-0.5 text-[12px] text-text-2">
                The samplesheet is joined to <span className="font-mono">sample_metadata</span> on{' '}
                <strong className="text-text">Sample_ID + a corroborating column</strong> (tissue) — never a
                single-column match. A human approves the join before the run proceeds.
              </div>
            </div>
          </div>

          {/* Hidden metadata file input, co-located with its Attach button (identity section only). */}
          <input
            ref={metaInput}
            type="file"
            accept=".csv,.txt"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) void onMetaFile(f)
              e.target.value = ''
            }}
          />

          {/* metadata attach status / required prompt */}
          <div className="px-[18px] py-[14px]">
            {metaName ? (
              <div className="flex flex-wrap items-center gap-[11px] rounded-[11px] border border-line bg-card-2 px-[14px] py-[11px]">
                <Paperclip size={16} strokeWidth={1.9} className="shrink-0 text-text-3" />
                <div className="min-w-0 flex-1">
                  <div className="font-mono text-[12px] font-semibold text-text">{metaName}</div>
                  <div className="text-[11px] text-text-2">
                    {Object.keys(sampleMeta).length} subjects mapped · tissue corroborates identity.{' '}
                    <span className="text-text-3">Subject ids held client-side (not sent — a labelled seam).</span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => metaInput.current?.click()}
                  className="whitespace-nowrap rounded-[8px] border border-line-strong bg-card px-3 py-1.5 text-[12px] font-medium text-accent-strong"
                >
                  Replace
                </button>
                <button
                  type="button"
                  onClick={clearMetadata}
                  className="inline-flex items-center gap-1 rounded-[8px] border border-line-strong bg-card px-3 py-1.5 text-[12px] text-text-2 hover:border-line"
                >
                  <X size={12} /> Remove
                </button>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-[11px] rounded-[11px] border border-hold-bd bg-hold-bg px-[14px] py-[11px] text-hold-fg">
                <ShieldAlert size={17} strokeWidth={1.9} className="shrink-0" />
                <div className="min-w-0 flex-1 text-[12px] leading-relaxed">
                  <strong>Sample metadata is required.</strong> A <span className="font-mono">sample_metadata.csv</span>{' '}
                  (Sample_ID, Subject_ID, Tissue) identifies each library to a subject — the run cannot proceed until it
                  is attached and the identity join is approved.
                </div>
                <button
                  type="button"
                  onClick={() => metaInput.current?.click()}
                  className="whitespace-nowrap rounded-[8px] border border-hold-bd bg-card px-3 py-1.5 text-[12px] font-semibold text-hold-fg"
                >
                  Attach metadata
                </button>
              </div>
            )}
            {/* Cross-link: subject metadata is authored upstream in the accessioning screen. */}
            <div className="mt-2 flex items-center gap-1.5 text-[11px] text-text-3">
              <ClipboardList size={12} strokeWidth={1.9} className="shrink-0" />
              <span>
                Subject metadata is authored in{' '}
                <Link to="/accession" className="font-medium text-accent-strong hover:underline">
                  Sample accessioning
                </Link>{' '}
                — send it here to pre-attach subject &amp; tissue.
              </span>
            </div>
          </div>

          {/* join review — only meaningful once metadata is attached */}
          {metaName && (
            <>
              {/* summary counts */}
              <div className="flex flex-wrap items-center gap-2 border-t border-line px-[18px] py-3">
                <span className="text-[11px] font-semibold uppercase tracking-[.4px] text-text-3">Join</span>
                {JOIN_STATUS_ORDER.filter((st) => join.counts[st] > 0).map((st) => (
                  <span
                    key={st}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11.5px] font-medium ${JOIN_STATUS_META[st].cls}`}
                  >
                    <span className={`h-1.5 w-1.5 rounded-full ${JOIN_STATUS_META[st].dot}`} />
                    {JOIN_STATUS_META[st].label} · {join.counts[st]}
                  </span>
                ))}
                {join.orphans.length > 0 && (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-line-strong bg-card-2 px-2.5 py-1 text-[11.5px] font-medium text-text-2">
                    <Info size={12} /> {join.orphans.length} not on this flowcell
                  </span>
                )}
              </div>

              {/* approval banner */}
              <div className="px-[18px]">
                {join.blocking > 0 ? (
                  <div className="flex items-start gap-2.5 rounded-[11px] border border-escalate-bd bg-escalate-bg px-[14px] py-3 text-[12.5px] leading-relaxed text-escalate-fg">
                    <AlertTriangle size={17} className="mt-px shrink-0" />
                    <div>
                      <strong>
                        {join.blocking} of {join.rows.length} sample{join.rows.length === 1 ? '' : 's'} need identity
                        resolution.
                      </strong>{' '}
                      Fix each flagged row (adopt the metadata tissue, correct the sample type, or attach the right
                      metadata) before this run can proceed. Mismatches cannot be approved past.
                    </div>
                  </div>
                ) : joinApproved ? (
                  <div className="flex items-start gap-2.5 rounded-[11px] border border-proceed-bd bg-proceed-bg px-[14px] py-3 text-[12.5px] leading-relaxed text-proceed-fg">
                    <ShieldCheck size={17} className="mt-px shrink-0" />
                    <div>
                      <strong>Identity join approved.</strong> All {join.rows.length} samples match on Sample_ID +
                      tissue. Submit is enabled; any edit re-opens this gate.
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start gap-2.5 rounded-[11px] border border-accent bg-accent-weak px-[14px] py-3 text-[12.5px] leading-relaxed text-accent-strong">
                    <Info size={17} className="mt-px shrink-0" />
                    <div>
                      <strong>All {join.rows.length} samples cleanly matched.</strong> Review the join, then approve to
                      confirm identity before submit.
                    </div>
                  </div>
                )}
              </div>

              {/* filter + join table */}
              <div className="mt-3 flex items-center gap-2 px-[18px]">
                <SegmentedControl<'attention' | 'all'>
                  value={joinFilter}
                  onChange={setJoinFilter}
                  options={[
                    { value: 'attention', label: `Needs attention · ${join.blocking}` },
                    { value: 'all', label: `All · ${join.rows.length}` },
                  ]}
                />
              </div>
              <div className="mt-2 overflow-x-auto px-[18px]">
                <div className="min-w-[720px] overflow-hidden rounded-[10px] border border-line">
                  <div className="grid grid-cols-[110px_1.2fr_1fr_1fr_1.6fr_96px] gap-[9px] border-b border-line bg-card-2 px-3 py-[8px] text-[9.5px] font-bold uppercase tracking-[.4px] text-text-3">
                    <div>Status</div>
                    <div>Sample</div>
                    <div>Sheet type</div>
                    <div>Meta tissue</div>
                    <div>Why</div>
                    <div>Resolve</div>
                  </div>
                  {joinRows.length === 0 ? (
                    <div className="px-3 py-[22px] text-center text-[12px] text-text-2">
                      No rows need attention — every sample is a clean Sample_ID + tissue match.
                    </div>
                  ) : (
                    joinPageRows.map((r, li) => {
                      const sMeta = JOIN_STATUS_META[r.status]
                      return (
                        <div
                          key={`${r.sample}-${(joinCurPage - 1) * joinPerN + li}`}
                          className="grid grid-cols-[110px_1.2fr_1fr_1fr_1.6fr_96px] items-center gap-[9px] border-b border-line px-3 py-[9px] last:border-b-0"
                        >
                          <div>
                            <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-semibold ${sMeta.cls}`}>
                              <span className={`h-1.5 w-1.5 rounded-full ${sMeta.dot}`} />
                              {sMeta.label}
                            </span>
                          </div>
                          <div className="min-w-0">
                            <div className="truncate font-mono text-[12px] text-text">{r.sample || '—'}</div>
                            {r.subjectId && (
                              <div className="truncate font-mono text-[9.5px] text-text-3" title={`Subject ${r.subjectId}`}>
                                subject {r.subjectId}
                              </div>
                            )}
                          </div>
                          <div className="truncate font-mono text-[11.5px] text-text-2">{r.sheetType || '—'}</div>
                          <div className="truncate font-mono text-[11.5px] text-text-2">{r.metaTissue || '—'}</div>
                          <div className="text-[11px] leading-snug text-text-2">{r.reason}</div>
                          <div>
                            {r.status === 'conflict' && r.metaTissue && (
                              <button
                                type="button"
                                onClick={() => adoptMetadataTissue(r.sample, r.metaTissue as string)}
                                className="whitespace-nowrap rounded-[7px] border border-line-strong bg-card px-2 py-1 text-[11px] font-medium text-accent-strong hover:border-accent"
                                title={`Set the samplesheet type to "${r.metaTissue}" to match the metadata`}
                              >
                                Use metadata
                              </button>
                            )}
                          </div>
                        </div>
                      )
                    })
                  )}
                </div>
                {joinRows.length > 0 && (
                  <Pager
                    total={joinRows.length}
                    page={joinCurPage}
                    perPage={joinPer}
                    onPage={setJoinPage}
                    onPerPage={setJoinPer}
                    noun="rows"
                  />
                )}
              </div>

              {/* orphans — metadata subjects not on this flowcell (loud info, never a hard block) */}
              {join.orphans.length > 0 && (
                <div className="mx-[18px] mt-2 rounded-[10px] border border-line bg-card-2 px-3 py-2.5 text-[11px] text-text-2">
                  <span className="font-semibold text-text-3">Not on this flowcell:</span>{' '}
                  {join.orphans.slice(0, 8).map((o) => o.sample).join(', ')}
                  {join.orphans.length > 8 ? ` +${join.orphans.length - 8} more` : ''} — metadata subjects with no
                  matching library here. Common when a metadata sheet spans several runs; surfaced, not blocked.
                </div>
              )}

              {/* approve action */}
              <div className="flex flex-wrap items-center gap-3 border-t border-line px-[18px] py-[14px]">
                <div className="flex-1 text-[12px] text-text-2">
                  {joinApproved
                    ? 'Identity confirmed by a human — recorded in the audit below.'
                    : join.blocking > 0
                      ? 'Resolve the flagged rows to enable approval.'
                      : 'Approve to confirm subject identity before the run proceeds.'}
                </div>
                <button
                  type="button"
                  onClick={() => void approveJoin()}
                  disabled={join.blocking > 0 || joinApproved}
                  className={`inline-flex items-center gap-2 rounded-[9px] px-4 py-2 text-[13px] font-semibold transition-opacity ${
                    joinApproved
                      ? 'border border-proceed-bd bg-proceed-bg text-proceed-fg'
                      : 'bg-accent text-white disabled:opacity-50'
                  }`}
                >
                  <ShieldCheck size={15} strokeWidth={2} />
                  {joinApproved ? 'Join approved' : 'Approve join'}
                </button>
              </div>

              {/* identity audit (client-side, this browser) */}
              <div className="border-t border-line">
                <button
                  type="button"
                  onClick={() => setAuditOpen((v) => !v)}
                  className="flex w-full items-center gap-2 px-[18px] py-2.5 text-left text-[12px] font-medium text-text-2 hover:bg-card-2"
                >
                  <History size={14} strokeWidth={1.9} className="text-text-3" />
                  Identity audit (this browser) · {audit.length}
                  <span className="ml-auto text-[11px] text-text-3">{auditOpen ? 'Hide' : 'Show'}</span>
                </button>
                {auditOpen && (
                  <div className="px-[18px] pb-3">
                    {audit.length === 0 ? (
                      <div className="rounded-[10px] border border-line bg-card-2 px-3 py-3 text-[11.5px] text-text-2">
                        No identity actions yet. Attaching metadata, adopting a tissue, and approving the join are
                        logged here (client-side only — a labelled seam).
                      </div>
                    ) : (
                      <div className="overflow-hidden rounded-[10px] border border-line">
                        {audit.slice(0, 25).map((a, k) => (
                          <div
                            key={`${a.at}-${k}`}
                            className="grid grid-cols-[130px_1fr] items-baseline gap-2 border-b border-line px-3 py-2 text-[11px] last:border-b-0"
                          >
                            <div className="font-mono text-text-3">{new Date(a.at).toLocaleString()}</div>
                            <div className="text-text-2">
                              <span className="font-semibold text-text">{a.action}</span>
                              {' — '}
                              {a.detail}
                              <span className="text-text-3"> · {a.actor}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* FOOTER — guardrail note + inert Save draft + Submit (gated on the approved identity join) */}
      <div className="mt-4 flex flex-wrap items-center gap-[14px]">
        <div className="flex items-center gap-2 text-[12px] text-text-2">
          <Info size={15} strokeWidth={1.9} className="text-info" />
          Barcodes are checked for collisions at the preflight gate — not here.
        </div>
        <div className="flex-1" />
        {!canSubmit && count > 0 && submitBlockedReason && (
          <span className="text-[12px] font-medium text-text-3">{submitBlockedReason}</span>
        )}
        <button
          type="button"
          className="rounded-[9px] border border-line-strong bg-card px-4 py-[9px] text-[13px] font-medium text-text-2"
        >
          Save draft
        </button>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={submitting || !canSubmit}
          className="inline-flex items-center gap-2 rounded-[9px] bg-accent px-[18px] py-2.5 text-[13px] font-semibold text-white transition-opacity disabled:opacity-60"
        >
          <ArrowRight size={15} strokeWidth={2} />
          {submitting ? 'Processing…' : 'Submit to pipeline'}
        </button>
      </div>
    </div>
  )
}
