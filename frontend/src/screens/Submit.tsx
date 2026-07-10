import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  ChevronDown,
  CircleCheck,
  FileCheck,
  Info,
  Plus,
  RefreshCw,
  Trash2,
  Upload,
} from 'lucide-react'
import { api } from '../api'
import { PageHeader } from '../components/PageHeader'
import { SegmentedControl } from '../components/SegmentedControl'
import { useToast } from '../components/Toast'
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

export function Submit() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [submitting, setSubmitting] = useState(false)
  const [method, setMethod] = useState<'upload' | 'basespace'>('upload')
  const [meta, setMeta] = useState<RunMeta>(SEED_META)
  const [samples, setSamples] = useState<SampleRow[]>(SEED_SAMPLES)

  // BaseSpace connect flow. `imported` gates whether run details + samples are populated in
  // BaseSpace mode — blank until Import, per the design. Upload mode is always populated.
  const [baseConnected, setBaseConnected] = useState(false)
  const [baseRegion, setBaseRegion] = useState(BASE_REGIONS[0])
  const [baseToken, setBaseToken] = useState('')
  const [selectedRun, setSelectedRun] = useState(BASE_RUNS[0].id)
  const [imported, setImported] = useState(false)

  const loaded = method === 'upload' || imported
  const count = loaded ? samples.length : 0

  function setField(key: keyof RunMeta, value: string) {
    setMeta((m) => ({ ...m, [key]: value }))
  }
  function patchSample(i: number, patch: Partial<SampleRow>) {
    setSamples((rows) => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  }
  function cycleType(i: number) {
    const idx = SAMPLE_TYPES.indexOf(samples[i].type)
    patchSample(i, { type: SAMPLE_TYPES[(idx + 1) % SAMPLE_TYPES.length] })
  }
  function addSample() {
    setSamples((rows) => [...rows, { sample: '', type: SAMPLE_TYPES[0], i7: '', i5: '', study: meta.study }])
  }
  function removeSample(i: number) {
    setSamples((rows) => rows.filter((_, j) => j !== i))
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
      const skip = ack.skipped_samples.length
        ? ` Skipped ${ack.skipped_samples.join(', ')} — no reads on disk for this demo.`
        : ''
      toast(`Processing ${ack.processed_samples.join(', ')} through the pipeline…${skip}`, 'info')
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

      {/* UPLOAD panel — drop zone + parsed chip (visual mock; no real file parse) */}
      {method === 'upload' && (
        <>
          <div className="mt-[14px] flex items-center gap-[18px] rounded-[14px] border-[1.5px] border-dashed border-line-strong bg-card p-[26px]">
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
              className="whitespace-nowrap rounded-[9px] border border-line-strong bg-card px-[15px] py-[9px] text-[13px] font-medium text-accent-strong"
            >
              Browse files
            </button>
          </div>
          <div className="mt-[10px] flex items-center gap-[11px] rounded-[11px] border border-proceed-bd bg-proceed-bg px-[14px] py-[11px]">
            <FileCheck size={18} strokeWidth={1.9} className="shrink-0 text-proceed" />
            <div className="min-w-0 flex-1">
              <div className="font-mono text-[12.5px] font-semibold text-proceed-fg">SampleSheet_2026-07-09.csv</div>
              <div className="text-[11.5px] text-text-2">
                Parsed 4 samples · detected run <span className="font-mono text-text">RUN-2026-07-09-A</span> · study{' '}
                <span className="font-mono text-text">GIAB-QC</span>. Review below before submitting.
              </div>
            </div>
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
            <button
              type="button"
              onClick={addSample}
              className="inline-flex items-center gap-[6px] rounded-lg border border-line-strong bg-card px-3 py-[7px] text-[12.5px] font-medium text-accent-strong"
            >
              <Plus size={14} strokeWidth={2} />
              Add sample
            </button>
          )}
        </div>
        <div className="grid grid-cols-[34px_1.4fr_1.2fr_1fr_1fr_1.1fr_34px] gap-[9px] border-b border-line bg-card-2 px-4 py-[9px] text-[9.5px] font-bold uppercase tracking-[.4px] text-text-3">
          <div>#</div>
          <div>Sample name</div>
          <div>Sample type</div>
          <div>i7 (index)</div>
          <div>i5 (index2)</div>
          <div>Study</div>
          <div />
        </div>
        {count === 0 ? (
          <div className="px-4 py-[26px] text-center">
            <div className="mx-auto max-w-[380px] text-[12.5px] leading-relaxed text-text-2">
              No samples yet. Import a run from BaseSpace above — its samples (names, types, and barcodes) populate here
              for review.
            </div>
          </div>
        ) : (
          samples.map((s, i) => (
            <div
              key={i}
              className="grid grid-cols-[34px_1.4fr_1.2fr_1fr_1fr_1.1fr_34px] items-center gap-[9px] border-b border-line px-4 py-[9px]"
            >
              <div className="font-mono text-[11.5px] text-text-3">{i + 1}</div>
              <input value={s.sample} onChange={(e) => patchSample(i, { sample: e.target.value })} className={INPUT_CLS} />
              <button
                type="button"
                onClick={() => cycleType(i)}
                className="flex w-full items-center justify-between gap-1.5 rounded-[7px] border border-line-strong bg-card-2 px-[10px] py-[6px] font-mono text-[11.5px] text-text-2"
              >
                {s.type}
                <ChevronDown size={12} strokeWidth={2} className="text-text-3" />
              </button>
              <input value={s.i7} onChange={(e) => patchSample(i, { i7: e.target.value })} className={INPUT_CLS} />
              <input value={s.i5} onChange={(e) => patchSample(i, { i5: e.target.value })} className={INPUT_CLS} />
              <input value={s.study} onChange={(e) => patchSample(i, { study: e.target.value })} className={INPUT_CLS} />
              <button
                type="button"
                onClick={() => removeSample(i)}
                title="Remove sample"
                className="flex h-7 w-7 items-center justify-center rounded-[7px] border border-line bg-card text-text-3"
              >
                <Trash2 size={13} strokeWidth={1.9} />
              </button>
            </div>
          ))
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
