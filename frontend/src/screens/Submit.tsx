import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  CircleCheck,
  ClipboardList,
  FileCheck,
  Info,
  Paperclip,
  Plus,
  RefreshCw,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { api } from '../api'
import { useConfirm } from '../components/ConfirmDialog'
import { PageHeader } from '../components/PageHeader'
import { SegmentedControl } from '../components/SegmentedControl'
import { useToast } from '../components/Toast'
import { clearHandoff, readHandoff } from '../lib/accession'
import { colIndex, splitCsv } from '../lib/csv'
import type { SampleRow, SubmitRunIn } from '../types'

// Submit samplesheet (§5.1) — the pipeline's front door: registers a run + its samples BEFORE
// processing. Compose ≠ execute: this screen only records run/sample metadata and hands off to
// the preflight gate; it never starts a tool. There is no backend endpoint that registers a run
// from a samplesheet (POST /api/pipelines is for pipeline graphs), so per the design this is a
// local-state mock — Save draft / Submit are client-only, faithful to "registration only."

type RunMeta = { runName: string; study: string; assay: string; platform: string }

// The four dual-barcode libraries seeded in the mock (dc.html): the GIAB trio + NA12878.
const SEED_SAMPLES: SampleRow[] = [
  { sample: 'HG002', type: 'Whole blood', i7: 'AGGCGAAG', i5: 'CTGATCGT', study: 'GIAB-QC' },
  { sample: 'HG003', type: 'Whole blood', i7: 'GAACCGCG', i5: 'TCTGATCG', study: 'GIAB-QC' },
  { sample: 'HG004', type: 'Saliva', i7: 'CTCACCAA', i5: 'GAGTCACT', study: 'GIAB-QC' },
  { sample: 'NA12878', type: 'Whole blood', i7: 'TCCGGAGA', i5: 'ACGTCCTG', study: 'GIAB-QC' },
]
const SEED_META: RunMeta = { runName: 'RUN-2026-07-09-A', study: 'GIAB-QC', assay: 'WES', platform: 'NovaSeq X' }

// Sample type cycles this fixed set on each chip click (design invariant: a controlled vocabulary,
// not free text).
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

// Per-sample metadata parsed from a sample_metadata.csv (the LIMS/subject sheet, distinct from the
// samplesheet). subject_id is intake identity — kept CLIENT-SIDE for now (POST /api/runs has no
// subject field yet; a labelled seam), tissue merges into the sample's type column.
type SampleMeta = { subject_id?: string; tissue?: string }
type ParsedSheet = { meta: Partial<RunMeta>; samples: SampleRow[] }

// splitCsv / colIndex now live in lib/csv.ts, shared with the Accession screen (one tolerant parser
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
  const [submitting, setSubmitting] = useState(false)
  const [method, setMethod] = useState<'upload' | 'basespace'>('upload')
  const [meta, setMeta] = useState<RunMeta>(SEED_META)
  const [samples, setSamples] = useState<SampleRow[]>(SEED_SAMPLES)
  // Real file parsing (was a hardcoded mock): the parsed samplesheet name + the sample_metadata
  // sheet (subject/tissue) keyed by sample id. Sample-table pagination scales past a demo handful.
  const [uploadName, setUploadName] = useState<string | null>(null)
  const [sampleMeta, setSampleMeta] = useState<Record<string, SampleMeta>>({})
  const [metaName, setMetaName] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [page, setPage] = useState(1)
  // Sample multi-select (S2) keyed by global row index, and the bulk-add count (S3).
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [addCount, setAddCount] = useState('1')
  const sheetInput = useRef<HTMLInputElement>(null)
  const metaInput = useRef<HTMLInputElement>(null)
  const PER = 25 // sample rows per page (scale-aware — a mixed flowcell is routinely 100+ samples)

  // BaseSpace connect flow. `imported` gates whether run details + samples are populated in
  // BaseSpace mode — blank until Import, per the design. Upload mode is always populated.
  const [baseConnected, setBaseConnected] = useState(false)
  const [baseRegion, setBaseRegion] = useState(BASE_REGIONS[0])
  const [baseToken, setBaseToken] = useState('')
  const [selectedRun, setSelectedRun] = useState(BASE_RUNS[0].id)
  const [imported, setImported] = useState(false)

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
    toast(`Loaded ${n} subjects from Sample accessioning — subject ids held client-side.`, 'info')
  }, [toast])

  const loaded = method === 'upload' || imported
  const count = loaded ? samples.length : 0
  // Paginate the sample table so a 100+ sample flowcell stays navigable (scale-aware UI rule).
  const pages = Math.max(1, Math.ceil(samples.length / PER))
  const curPage = Math.min(page, pages)
  const pageStart = (curPage - 1) * PER
  const pagedSamples = samples.slice(pageStart, pageStart + PER)

  function setField(key: keyof RunMeta, value: string) {
    setMeta((m) => ({ ...m, [key]: value }))
  }
  function patchSample(i: number, patch: Partial<SampleRow>) {
    setSamples((rows) => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  }
  // S3: append N blank rows in one action (a 100-sample plate shouldn't be 100 clicks). Bounded so a
  // fat-fingered count can't lock the tab.
  function addSamples(n: number) {
    const k = Math.max(1, Math.min(500, Math.floor(n) || 1))
    setSamples((rows) => [
      ...rows,
      ...Array.from({ length: k }, () => ({ sample: '', type: SAMPLE_TYPES[0], i7: '', i5: '', study: meta.study })),
    ])
  }
  // S2: checkbox multi-select + select-all, replacing per-row trashing.
  function toggleSampleSel(i: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })
  }
  function toggleAllSel() {
    setSelected((prev) => (prev.size === samples.length ? new Set() : new Set(samples.map((_, i) => i))))
  }
  async function removeSelected() {
    const n = selected.size
    if (n === 0) return
    const ok = await confirm({
      title: `Remove ${n} sample${n === 1 ? '' : 's'} from this draft?`,
      body: 'Removed from this submission draft only — nothing is deleted downstream.',
      confirmLabel: 'Remove',
      tone: 'danger',
    })
    if (!ok) return
    setSamples((rows) => rows.filter((_, j) => !selected.has(j)))
    setSelected(new Set())
  }

  // Parse a dropped/selected samplesheet for real (replaces the old hardcoded "Parsed 4 samples"
  // mock). Merges any already-loaded sample_metadata tissue onto the fresh rows.
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
      setSelected(new Set())
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
      toast(`Attached metadata for ${n} samples from ${file.name}.`, 'success')
    } catch (e) {
      toast(`Couldn't read ${file.name} — ${e instanceof Error ? e.message : String(e)}`, 'error')
    }
  }

  function clearMetadata() {
    setSampleMeta({})
    setMetaName(null)
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
    setSelected(new Set())
  }

  // Submit registers the run, then hands off to the execution boundary (POST /api/runs) — the
  // API triggers the pipeline driver (the core still never runs a tool). We poll intake-status and
  // navigate to the run once processing completes. Only samples with reads on disk are processed.
  async function submit() {
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
      // Scale-aware summary: a 100-sample flowcell can't dump every name into a toast (surfaced by
      // the 100-sample test) — list up to 5, else summarize the count.
      const summarize = (arr: string[]) => (arr.length <= 5 ? arr.join(', ') : `${arr.length} samples`)
      const procMsg = ack.processed_samples.length
        ? `Processing ${summarize(ack.processed_samples)}`
        : 'No samples with reads on disk to process'
      const skip = ack.skipped_samples.length ? ` · skipped ${summarize(ack.skipped_samples)} (no reads on disk for this demo)` : ''
      toast(`${procMsg} through the pipeline…${skip}`, 'info')
      const poll = async (): Promise<void> => {
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
      }
      void poll()
    } catch (e) {
      toast(`Couldn't submit run — ${e instanceof Error ? e.message : String(e)}`, 'error')
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-[1080px]">
      <PageHeader
        eyebrow="Intake"
        title="New submission"
        subtitle={
          <>
            Register a run and its samples <strong className="text-text">before processing</strong>. This drives
            sample names, run name, sample type, barcodes, and study for every downstream stage and gate.
          </>
        }
      />

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

      {/* UPLOAD panel — real file parse (samplesheet + optional sample_metadata.csv) */}
      {method === 'upload' && (
        <>
          {/* Hidden real inputs; the drop zone / buttons trigger them. Reset value on change so the
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
          {/* sample_metadata.csv (LIMS/subject sheet) — distinct from the samplesheet (G2). */}
          <div className="mt-[10px] flex flex-wrap items-center gap-[11px] rounded-[11px] border border-line bg-card px-[14px] py-[11px]">
            <Paperclip size={16} strokeWidth={1.9} className="shrink-0 text-text-3" />
            <div className="min-w-0 flex-1">
              {metaName ? (
                <>
                  <div className="font-mono text-[12px] font-semibold text-text">{metaName}</div>
                  <div className="text-[11px] text-text-2">
                    {Object.keys(sampleMeta).length} subjects mapped · tissue merged into Sample type.{' '}
                    <span className="text-text-3">Subject ids held client-side (not yet sent — a labelled seam).</span>
                  </div>
                </>
              ) : (
                <div className="text-[12px] text-text-2">
                  <strong className="text-text">Sample metadata</strong> (optional) — a{' '}
                  <span className="font-mono">sample_metadata.csv</span> (Sample_ID, Subject_ID, Tissue) enriches
                  subject &amp; tissue.
                </div>
              )}
            </div>
            {metaName ? (
              <button
                type="button"
                onClick={clearMetadata}
                className="inline-flex items-center gap-1 rounded-[8px] border border-line-strong bg-card px-3 py-1.5 text-[12px] text-text-2 hover:border-line"
              >
                <X size={12} /> Remove
              </button>
            ) : (
              <button
                type="button"
                onClick={() => metaInput.current?.click()}
                className="whitespace-nowrap rounded-[8px] border border-line-strong bg-card px-3 py-1.5 text-[12px] font-medium text-accent-strong"
              >
                Attach metadata
              </button>
            )}
          </div>
          {/* Cross-link: subject metadata is authored upstream in the CRM/accessioning screen. */}
          <div className="mt-1.5 flex items-center gap-1.5 px-1 text-[11px] text-text-3">
            <ClipboardList size={12} strokeWidth={1.9} className="shrink-0" />
            <span>
              Subject metadata is authored in{' '}
              <Link to="/accession" className="font-medium text-accent-strong hover:underline">
                Sample accessioning
              </Link>{' '}
              — send it here to pre-attach subject &amp; tissue.
            </span>
          </div>
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
            <div className="text-[14.5px] font-semibold text-text">Samples · {count}</div>
            <div className="mt-0.5 text-[12px] text-text-2">
              Sample name, type, and dual barcodes resolve each library at demux and intake.
            </div>
          </div>
          {method === 'upload' && (
            <div className="flex items-center gap-2">
              {/* S2: bulk-remove the checkbox selection (confirmed), replacing per-row trashing. */}
              {selected.size > 0 && (
                <button
                  type="button"
                  onClick={() => void removeSelected()}
                  className="inline-flex items-center gap-[6px] rounded-lg border border-escalate-bd bg-escalate-bg px-3 py-[7px] text-[12.5px] font-medium text-escalate-fg transition-[filter] hover:brightness-95"
                >
                  <Trash2 size={14} strokeWidth={1.9} />
                  Remove {selected.size}
                </button>
              )}
              {/* S3: add N samples at once. */}
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
                aria-label="Select all samples"
                checked={samples.length > 0 && selected.size === samples.length}
                ref={(el) => {
                  if (el) el.indeterminate = selected.size > 0 && selected.size < samples.length
                }}
                onChange={toggleAllSel}
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
          // patch/remove/cycle so edits land on the right row across pages.
          pagedSamples.map((s, li) => {
            const i = pageStart + li
            const subject = sampleMeta[s.sample]?.subject_id
            return (
              <div
                key={i}
                className={`grid grid-cols-[26px_30px_1.4fr_1.2fr_1fr_1fr_1.1fr] items-center gap-[9px] border-b border-line px-4 py-[9px] transition-colors ${
                  selected.has(i) ? 'bg-accent-weak/40' : ''
                }`}
              >
                <div className="flex items-center">
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5 accent-accent"
                    aria-label={`Select ${s.sample || `sample ${i + 1}`}`}
                    checked={selected.has(i)}
                    onChange={() => toggleSampleSel(i)}
                  />
                </div>
                <div className="font-mono text-[11.5px] text-text-3">{i + 1}</div>
                <div className="min-w-0">
                  <input value={s.sample} onChange={(e) => patchSample(i, { sample: e.target.value })} className={INPUT_CLS} />
                  {subject && (
                    <div className="mt-0.5 truncate font-mono text-[9.5px] text-text-3" title={`Subject ${subject}`}>
                      subject {subject}
                    </div>
                  )}
                </div>
                {/* S1: a real dropdown (was a cycle-on-click button that read as a Next control). The
                    current value is always an option even if a parsed tissue is outside the vocab. */}
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
        {count > PER && (
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-[11px] text-[11.5px] text-text-2">
            <span>
              Showing {pageStart + 1}–{Math.min(pageStart + PER, count)} of {count} samples
            </span>
            {pages > 1 && (
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setPage(Math.max(1, curPage - 1))}
                  className="h-7 min-w-[28px] rounded-[7px] border border-line bg-card text-[13px] text-text-2 hover:border-line-strong"
                  aria-label="Previous page"
                >
                  ‹
                </button>
                {Array.from({ length: pages }, (_, k) => k + 1).map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setPage(n)}
                    className={`h-7 min-w-[28px] rounded-[7px] px-2 text-[12px] ${
                      n === curPage ? 'bg-accent font-semibold text-white' : 'border border-line bg-card text-text-2 hover:border-line-strong'
                    }`}
                  >
                    {n}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => setPage(Math.min(pages, curPage + 1))}
                  className="h-7 min-w-[28px] rounded-[7px] border border-line bg-card text-[13px] text-text-2 hover:border-line-strong"
                  aria-label="Next page"
                >
                  ›
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* FOOTER — guardrail note + inert Save draft + Submit (registration/navigation only) */}
      <div className="mt-4 flex flex-wrap items-center gap-[14px]">
        <div className="flex items-center gap-2 text-[12px] text-text-2">
          <Info size={15} strokeWidth={1.9} className="text-info" />
          Barcodes are checked for collisions at the preflight gate — not here.
        </div>
        <div className="flex-1" />
        <button
          type="button"
          className="rounded-[9px] border border-line-strong bg-card px-4 py-[9px] text-[13px] font-medium text-text-2"
        >
          Save draft
        </button>
        <button
          type="button"
          onClick={submit}
          disabled={submitting || count === 0}
          className="inline-flex items-center gap-2 rounded-[9px] bg-accent px-[18px] py-2.5 text-[13px] font-semibold text-white transition-opacity disabled:opacity-60"
        >
          <ArrowRight size={15} strokeWidth={2} />
          {submitting ? 'Processing…' : 'Submit to pipeline'}
        </button>
      </div>
    </div>
  )
}
