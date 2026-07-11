import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Archive, Check, Copy, Loader2, Play, TriangleAlert, Upload, Wrench, X } from 'lucide-react'
import { api } from '../api'
import { FALLBACK_SUMMARY } from './ReviewRepairCard'
import { useToast } from './Toast'
import {
  AUTHOR_FLAGS,
  ICONS,
  ICON_CHOICES,
  RUN_STEPS,
  STAR_HELP,
  type IconKey,
} from './BuilderShared'
import type { AgentProposal, ArchiveDigest, MonitoringSignature } from '../types'

// Honest state when the advisory archivist index can't be reached (off-gate, non-critical). We show
// NO counts, manifest, or proposal — only that the librarian is unavailable. Nothing about the runs,
// the ledger, or the gate is affected. Mirrors ReviewRepairCard's FALLBACK_SUMMARY idiom.
const ARCHIVIST_UNAVAILABLE =
  'The archivist agent is unavailable, so no organizational index can be shown. No run, artifact, or verdict is affected — nothing here moves data.'

// Human-readable byte size (the backend's _human_size is not exposed on the wire).
function humanBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

// Advisory + hand-off modals for the builder. All share the 16px overlay, 16-radius card, and
// a soft pop shadow. None of them run a tool or touch a verdict: Run hands off to the engine;
// the three agents (node-author, pipeline-repair, archivist) are advisory and human-approved.

const OVERLAY = 'fixed inset-0 z-[60] flex items-center justify-center bg-[rgba(16,24,40,.34)] p-6'

function ModalShell({ width, onClose, children }: { width: number; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className={OVERLAY} onClick={onClose}>
      <div
        className="flex max-h-full flex-col overflow-hidden rounded-2xl border border-line-strong bg-card shadow-pop"
        style={{ width, maxWidth: '100%' }}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  )
}

function CloseBtn({ onClose }: { onClose: () => void }) {
  return (
    <button onClick={onClose} className="grid h-7 w-7 shrink-0 place-items-center rounded-md border border-line bg-card text-text-2 hover:bg-page">
      <X size={14} />
    </button>
  )
}

// ── Run hand-off (composes ≠ executes) ───────────────────────────────────────
export function RunHandoffModal({
  envHint,
  profile,
  yaml,
  curLoc,
  savedName,
  onEmit,
  onClose,
}: {
  envHint: string
  profile: string
  yaml: string
  curLoc: Record<string, string>
  savedName: string | null
  onEmit: () => void
  onClose: () => void
}) {
  const [copied, setCopied] = useState(false)
  // Copy the REAL composed layout; also fire the builder's compose-only Emit (logs it, runs nothing).
  const onCopy = () => {
    navigator.clipboard
      ?.writeText(yaml)
      .then(() => {
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1500)
      })
      .catch(() => {})
    onEmit()
  }
  return (
    <ModalShell width={560} onClose={onClose}>
      <div className="flex items-center gap-2.5 border-b border-line px-4 py-3.5">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent-weak text-accent-strong">
          <Play size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold text-text">Run this pipeline</div>
          <div className="text-[11.5px] text-text-3">
            a hand-off to the engine — <strong className="text-text-2">PipeGuard composes, it does not execute</strong>
          </div>
        </div>
        <CloseBtn onClose={onClose} />
      </div>
      <div className="px-4 py-4">
        <div className="mb-3.5 flex items-start gap-2 rounded-[9px] border border-hold-bd bg-hold-bg px-3 py-2.5 text-[11.5px] text-hold-fg">
          <TriangleAlert size={14} className="mt-0.5 shrink-0" />
          <span>
            No tool runs inside PipeGuard. This emits <span className="font-mono">run_layout.yaml</span> and hands it to your execution engine; the
            deterministic gate still decides the verdict afterward.
          </span>
        </div>
        {/* The REAL composed run_layout the builder emits (yamlFor(profile, locEdits)) — the same
            string the Emit console renders, derived from the profile's locators (not the canvas nodes). */}
        <div className="mb-3.5">
          <div className="mb-1.5 flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-[0.5px] text-text-3">Composed run_layout</span>
            <span className="font-mono text-[10px] text-text-3">
              profile {profile} · {Object.keys(curLoc).length} locators
            </span>
            {!savedName && <span className="ml-auto text-[10px] text-text-3">reflects your current draft</span>}
          </div>
          <pre className="m-0 max-h-[168px] overflow-auto whitespace-pre rounded-[9px] border border-line bg-card-2 p-3 font-mono text-[10px] leading-relaxed text-text-2">
            {yaml}
          </pre>
          <div className="mt-1 text-[10px] text-text-3">
            Derived from the <span className="font-mono">{profile}</span> profile’s locators — not from arbitrary canvas nodes.
          </div>
        </div>
        <div className="flex flex-col">
          {RUN_STEPS.map((s, i) => (
            <div key={s.title} className="flex items-start gap-3">
              <div className="flex shrink-0 flex-col items-center">
                <span
                  className={`grid h-[22px] w-[22px] place-items-center rounded-full text-[11px] font-semibold ${
                    i === 0 ? 'bg-accent text-white' : 'border border-line-strong bg-card-2 text-text-2'
                  }`}
                >
                  {i + 1}
                </span>
                {i < RUN_STEPS.length - 1 && <span className="min-h-[14px] w-0.5 flex-1 bg-line" />}
              </div>
              <div className="pb-3.5">
                <div className="text-[13px] font-semibold text-text">{s.title}</div>
                <div className="text-[11.5px] leading-snug text-text-2">{s.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-2.5 border-t border-line px-4 py-3">
        <span className="flex-1 font-mono text-[10.5px] text-text-3">{envHint}</span>
        <button onClick={onClose} className="rounded-lg border border-line bg-card px-3 py-1.5 text-[12.5px] text-text-2 hover:border-line-strong">
          Cancel
        </button>
        <button
          onClick={onCopy}
          className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-1.5 text-[12.5px] font-semibold text-white shadow-card hover:opacity-90"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? 'Copied run_layout.yaml' : 'Copy run_layout.yaml'}
        </button>
      </div>
    </ModalShell>
  )
}

// ── Author a tool node (advisory · roster #5) ────────────────────────────────
export function AuthorToolNodeModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('STAR')
  const [icon, setIcon] = useState<IconKey>('merge')
  const [flags, setFlags] = useState(() => AUTHOR_FLAGS.map((f) => ({ ...f })))

  const toggle = (flag: string) => setFlags((fs) => fs.map((f) => (f.flag === flag ? { ...f, on: !f.on } : f)))
  const setVal = (flag: string, value: string) => setFlags((fs) => fs.map((f) => (f.flag === flag ? { ...f, value } : f)))

  const inChip = 'inline-flex items-center gap-1.5 rounded-md border border-proceed-bd bg-proceed-bg px-2 py-0.5 font-mono text-[10.5px] text-proceed-fg'
  const unknownChip = 'inline-flex items-center gap-1.5 rounded-md border border-hold-bd bg-hold-bg px-2 py-0.5 font-mono text-[10.5px] text-hold-fg'

  return (
    <ModalShell width={840} onClose={onClose}>
      <div className="flex items-center gap-2.5 border-b border-line px-4 py-3.5">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent-weak text-accent-strong">
          <SparkleGlyph />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold text-text">Author a tool node</div>
          <div className="text-[11.5px] text-text-3">
            advisory agent proposes a typed node · <strong className="text-text-2">you review &amp; accept</strong> · it never wires an edge or touches a
            verdict
          </div>
        </div>
        <span className="shrink-0 whitespace-nowrap rounded-full border border-[#cfe0fb] bg-accent-weak px-2 py-0.5 text-[10px] font-semibold text-accent-strong">
          roster #5 · phase-2
        </span>
        <CloseBtn onClose={onClose} />
      </div>

      <div className="flex min-h-0 flex-1">
        {/* left — tool docs */}
        <div className="flex w-[45%] flex-col gap-2.5 overflow-y-auto border-r border-line p-4">
          <div className="text-[10px] font-bold uppercase tracking-[0.5px] text-text-3">Tool docs · input</div>
          <div className="rounded-xl border border-dashed border-line-strong bg-card-2 p-4 text-center">
            <Upload size={20} className="mx-auto text-text-3" />
            <div className="mt-1.5 text-[12px] text-text-2">
              Drop a Nextflow module, <span className="font-mono">--help</span>, or <span className="font-mono">nextflow_schema.json</span>
            </div>
          </div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.4px] text-text-3">Parsed · STAR --help</div>
          <pre className="m-0 whitespace-pre-wrap rounded-[9px] border border-line bg-card-2 p-3 font-mono text-[10px] leading-relaxed text-text-2">
            {STAR_HELP}
          </pre>
        </div>

        {/* right — proposed node */}
        <div className="flex flex-1 flex-col gap-2.5 overflow-y-auto bg-card-2 p-4">
          <div className="text-[10px] font-bold uppercase tracking-[0.5px] text-text-3">Proposed ToolNode · review</div>
          <div className="overflow-hidden rounded-xl border border-line bg-card">
            <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-card-2 text-text-2">{ICON_GLYPH(icon)}</span>
              <div className="min-w-0 flex-1">
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Tool node name"
                  className="w-full rounded-md border border-line-strong bg-card px-2 py-1 text-[13px] font-semibold text-text outline-none focus:border-accent"
                />
                <div className="mt-1 font-mono text-[10px] text-text-3">2.7.11b · align · suggested</div>
              </div>
              <span className="rounded bg-[#fceee2] px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-[0.3px] text-[#c1560f]">substitute</span>
            </div>
            <div className="flex flex-col gap-2.5 px-3 py-2.5">
              {/* icon picker */}
              <div>
                <div className="mb-1.5 text-[9.5px] font-semibold uppercase tracking-[0.3px] text-text-3">Icon</div>
                <div className="flex flex-wrap gap-1.5">
                  {ICON_CHOICES.map((k) => (
                    <button
                      key={k}
                      onClick={() => setIcon(k)}
                      className={`grid h-7 w-7 place-items-center rounded-lg border ${
                        icon === k ? 'border-accent bg-accent-weak text-accent-strong' : 'border-line bg-card text-text-2 hover:border-line-strong'
                      }`}
                    >
                      {ICON_GLYPH(k)}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <div className="mb-1.5 text-[9.5px] font-semibold uppercase tracking-[0.3px] text-text-3">Input ports</div>
                <div className="flex flex-wrap gap-1.5">
                  <span className={inChip}>
                    <Check size={11} /> fastq
                  </span>
                  <span className={inChip}>
                    <Check size={11} /> reference_fasta
                  </span>
                </div>
              </div>
              <div>
                <div className="mb-1.5 text-[9.5px] font-semibold uppercase tracking-[0.3px] text-text-3">Output ports</div>
                <div className="flex flex-wrap gap-1.5">
                  <span className={inChip}>
                    <Check size={11} /> bam
                  </span>
                  <span className={unknownChip}>SJ.out.tab → unknown ⚠</span>
                  <span className={unknownChip}>ReadsPerGene → salmon_quant? ⚠</span>
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-start gap-2 rounded-[9px] border border-hold-bd bg-hold-bg px-3 py-2.5 text-[11px] text-hold-fg">
            <TriangleAlert size={14} className="mt-0.5 shrink-0" />
            <span>
              <strong>2 kinds need your review.</strong> Unknown artifact-kinds are flagged, <strong>never invented</strong> — assign a kind from the{' '}
              <span className="font-mono">ArtifactKind</span> vocab or add a new one. A wrong kind is caught by typed wiring at compose time.
            </span>
          </div>

          <div className="text-[10px] font-bold uppercase tracking-[0.5px] text-text-3">Flags &amp; parameters · parsed from --help</div>
          <div className="-mt-1 text-[10.5px] leading-relaxed text-text-3">Tick the CLI flags this node should expose; set default values from the tool docs.</div>
          <div className="flex max-h-[158px] flex-col gap-1.5 overflow-y-auto pr-1">
            {flags.map((f) => (
              <div
                key={f.flag}
                className={`flex items-center gap-2.5 rounded-lg border px-2.5 py-2 ${
                  f.on ? 'border-[#cfe0fb] bg-accent-weak' : 'border-line bg-card-2'
                }`}
              >
                <button
                  onClick={() => toggle(f.flag)}
                  className={`grid h-4 w-4 shrink-0 place-items-center rounded ${f.on ? 'bg-accent' : 'border border-line-strong bg-card'}`}
                >
                  {f.on && <Check size={11} className="text-white" strokeWidth={3.2} />}
                </button>
                <div className="min-w-0 flex-1">
                  <div className="font-mono text-[11.5px] text-text">{f.flag}</div>
                  <div className="text-[9.5px] text-text-3">{f.help}</div>
                </div>
                <input
                  value={f.value}
                  onChange={(e) => setVal(f.flag, e.target.value)}
                  className={`w-[150px] rounded-md border border-line px-2 py-1 font-mono text-[11px] outline-none ${
                    f.on ? 'bg-card text-text' : 'bg-card-2 text-text-3'
                  }`}
                />
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2.5 border-t border-line px-4 py-3">
        <span className="flex-1 text-[10.5px] leading-snug text-text-3">
          Stub-first ($0), opt-in Claude for the kind mapping only. The agent proposes a card — it never draws an edge, places a node on the gate, or
          auto-adds.
        </span>
        <button onClick={onClose} className="rounded-lg border border-line bg-card px-3 py-1.5 text-[12.5px] text-text-2 hover:border-line-strong">
          Discard
        </button>
        <button onClick={onClose} className="rounded-lg bg-accent px-3.5 py-1.5 text-[12.5px] font-semibold text-white shadow-card hover:opacity-90">
          Review kinds &amp; add to palette
        </button>
      </div>
    </ModalShell>
  )
}

// ── Pipeline-repair (advisory) ───────────────────────────────────────────────
export function PipelineRepairModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const { toast } = useToast()
  const chip = 'rounded-md border border-line bg-card-2 px-2 py-1 font-mono text-[10px] text-text-2'
  const [sigs, setSigs] = useState<MonitoringSignature[] | null>(null) // null = loading, [] = empty
  const [sigsError, setSigsError] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [proposal, setProposal] = useState<AgentProposal | null>(null)
  const [pLoading, setPLoading] = useState(false)
  const [pError, setPError] = useState(false) // true → honest "agent unavailable"

  // 1) Load recurring signatures once; auto-pick the top-ranked (backend sorts by count desc).
  useEffect(() => {
    let alive = true
    api
      .monitoring('all', 25)
      .then((d) => {
        if (!alive) return
        setSigs(d.signatures)
        setSelected(d.signatures[0]?.signature ?? null)
      })
      .catch(() => alive && setSigsError(true))
    return () => {
      alive = false
    }
  }, [])

  // 2) Fetch the repair whenever the selected signature changes. The repair endpoint defaults to
  //    window='all' server-side, matching monitoring('all'), so a picked signature always resolves
  //    (no 404 in the happy path). On any failure we fall back to the honest FALLBACK_SUMMARY.
  useEffect(() => {
    if (!selected) return
    let alive = true
    setPLoading(true)
    setPError(false)
    setProposal(null)
    api
      .signatureRepair(selected)
      .then((p) => {
        if (!alive) return
        setProposal(p)
        setPLoading(false)
      })
      .catch(() => {
        if (!alive) return
        setPError(true)
        setPLoading(false)
      })
    return () => {
      alive = false
    }
  }, [selected])

  const selMeta = sigs?.find((s) => s.signature === selected) ?? null

  return (
    <ModalShell width={560} onClose={onClose}>
      <div className="flex items-center gap-2.5 border-b border-line px-4 py-3.5">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent-weak text-accent-strong">
          <Wrench size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold text-text">Pipeline-repair agent</div>
          <div className="text-[11.5px] text-text-3">
            advisory · roster #5 · <strong className="text-text-2">proposes fixes; a human approves</strong>
          </div>
        </div>
        <span className="shrink-0 rounded-full border border-[#cfe0fb] bg-accent-weak px-2 py-0.5 text-[10px] font-semibold text-accent-strong">phase-2</span>
        <CloseBtn onClose={onClose} />
      </div>
      <div className="max-h-[62vh] overflow-y-auto px-4 py-4">
        <p className="mb-3 text-[12.5px] leading-relaxed text-text-2">
          Watches recurring failure signatures across runs and drafts a fix for a human to review. It{' '}
          <strong className="text-text">never edits the pipeline or changes a verdict</strong> — off the critical path, like every agent here.
        </p>
        {sigs === null && !sigsError ? (
          <p className="inline-flex items-center gap-1.5 text-[12.5px] text-text-3">
            <Loader2 size={13} className="animate-spin" /> Loading recurring signatures…
          </p>
        ) : sigsError ? (
          <div className="flex items-start gap-2 rounded-[9px] border border-hold-bd bg-hold-bg px-3 py-2.5 text-[11.5px] text-hold-fg">
            <TriangleAlert size={14} className="mt-0.5 shrink-0" />
            <span>Could not load recurring signatures — the monitoring feed is unavailable. The gate is unaffected.</span>
          </div>
        ) : sigs && sigs.length === 0 ? (
          <p className="text-[12.5px] text-text-2">
            No recurring signatures across the served runs. The pipeline-repair agent has nothing to propose.
          </p>
        ) : (
          <>
            {sigs && sigs.length > 1 && (
              <select
                value={selected ?? ''}
                onChange={(e) => setSelected(e.target.value)}
                className="mb-2.5 w-full rounded-md border border-line-strong bg-card px-2 py-1.5 text-[12px] text-text outline-none focus:border-accent"
              >
                {sigs.map((s) => (
                  <option key={s.signature} value={s.signature}>
                    {s.rule_id} · {s.title} — {s.count}×
                  </option>
                ))}
              </select>
            )}
            <div className="overflow-hidden rounded-xl border border-line">
              <div className="flex items-center gap-2 border-b border-line bg-accent-weak px-3 py-2.5">
                <span className="text-[9px] font-bold uppercase tracking-[0.4px] text-accent-strong">Proposed fix</span>
                <span className="ml-auto font-mono text-[10px] text-text-3">
                  signature {proposal?.addresses_rule_id ?? selMeta?.rule_id ?? '—'} · seen{' '}
                  {proposal?.signature_count ?? selMeta?.count ?? 0}× across served runs
                </span>
              </div>
              <div className="px-3 py-3">
                {pLoading ? (
                  <p className="inline-flex items-center gap-1.5 text-[12px] text-text-3">
                    <Loader2 size={13} className="animate-spin" /> Asking the pipeline-repair agent…
                  </p>
                ) : pError ? (
                  <p className="text-[12px] leading-relaxed text-text-2">{FALLBACK_SUMMARY}</p>
                ) : proposal ? (
                  <>
                    <div className="text-[13px] font-semibold text-text">{selMeta?.title ?? 'Proposed remediation'}</div>
                    <div className="mt-1 text-[12px] leading-relaxed text-text-2">{proposal.summary}</div>
                    {proposal.rationale && (
                      <div className="mt-1.5 text-[11px] leading-relaxed text-text-3">{proposal.rationale}</div>
                    )}
                    <div className="mt-2.5 flex flex-wrap gap-1.5">
                      <span className={chip}>attachTo {proposal.attach_to ?? 'workflow-wide'}</span>
                      {proposal.scope && <span className={chip}>scope {proposal.scope}</span>}
                      <span className={chip}>{proposal.mode === 'claude' ? 'claude' : 'stub · $0'}</span>
                    </div>
                    {proposal.citations && proposal.citations.length > 0 && (
                      <div className="mt-2.5 flex flex-col gap-1 border-t border-line pt-2">
                        {proposal.citations.map((c, i) => (
                          <div key={`${c.ref}-${i}`} className="font-mono text-[10px] text-text-3">
                            {c.source_kind} · {c.ref}
                            {c.title ? ` — ${c.title}` : ''}
                            {c.score != null ? ` · ${(c.score * 100).toFixed(0)}% (heuristic)` : ''}
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                ) : null}
              </div>
            </div>
          </>
        )}
      </div>
      <div className="flex items-center gap-2.5 border-t border-line px-4 py-3">
        <span className="flex-1 text-[10.5px] leading-snug text-text-3">Advisory only — routing a fix to the queue still needs approver sign-off.</span>
        <button onClick={onClose} className="rounded-lg border border-line bg-card px-3 py-1.5 text-[12.5px] text-text-2 hover:border-line-strong">
          Dismiss
        </button>
        <button
          onClick={() => {
            onClose()
            navigate('/queue')
            toast(
              'Opened the review queue. Routing a signature-level fix to a specific ticket needs a sample-scoped ticket and approver sign-off.',
              'info',
            )
          }}
          className="rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12.5px] font-medium text-text hover:border-line"
        >
          Send to review queue
        </button>
      </div>
    </ModalShell>
  )
}

// ── Archivist (advisory) ─────────────────────────────────────────────────────
export function ArchivistModal({ onClose }: { onClose: () => void }) {
  const [digest, setDigest] = useState<ArchiveDigest | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  // The builder's Archivist button is generic (not run-scoped), so we fetch the cross-run index.
  useEffect(() => {
    let live = true
    api
      .archiveIndex()
      .then((d) => {
        if (!live) return
        setDigest(d)
        setLoading(false)
      })
      .catch(() => {
        if (!live) return
        setFailed(true)
        setLoading(false)
      })
    return () => {
      live = false
    }
  }, [])

  return (
    <ModalShell width={540} onClose={onClose}>
      <div className="flex items-center gap-2.5 border-b border-line px-4 py-3.5">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-card-2 text-text-2">
          <Archive size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold text-text">Archivist agent</div>
          <div className="text-[11.5px] text-text-3">
            advisory · <strong className="text-text-2">never deletes, never touches an active run</strong>
          </div>
        </div>
        <span className="shrink-0 rounded-full border border-[#cfe0fb] bg-accent-weak px-2 py-0.5 text-[10px] font-semibold text-accent-strong">phase-2</span>
        <CloseBtn onClose={onClose} />
      </div>
      <div className="max-h-[62vh] overflow-y-auto px-4 py-4">
        <p className="mb-3 text-[12.5px] leading-relaxed text-text-2">
          Indexes <strong className="text-text">released</strong> runs across the platform and proposes an
          organizational/archival action with a prepared manifest — it{' '}
          <strong className="text-text">never opens, moves, deletes, or relabels a file</strong>, and holds any run still
          running or in review.
        </p>
        {loading ? (
          <p className="inline-flex items-center gap-1.5 text-[12.5px] text-text-3">
            <Loader2 size={13} className="animate-spin" /> Asking the archivist agent…
          </p>
        ) : failed || !digest ? (
          <div className="flex items-start gap-2 rounded-[9px] border border-hold-bd bg-hold-bg px-3 py-2.5 text-[11.5px] text-hold-fg">
            <TriangleAlert size={14} className="mt-0.5 shrink-0" />
            <span>{ARCHIVIST_UNAVAILABLE}</span>
          </div>
        ) : (
          <ArchiveIndexBody d={digest} />
        )}
      </div>
      <div className="flex items-center gap-2.5 border-t border-line px-4 py-3">
        <span className="flex-1 text-[10.5px] leading-snug text-text-3">Advisory — the archive is queued for a human to confirm; nothing is moved automatically.</span>
        <button onClick={onClose} className="rounded-lg border border-line bg-card px-3 py-1.5 text-[12.5px] text-text-2 hover:border-line-strong">
          Dismiss
        </button>
        <button onClick={onClose} className="rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12.5px] font-medium text-text hover:border-line">
          Queue archive
        </button>
      </div>
    </ModalShell>
  )
}

// Renders the REAL cross-run ArchiveDigest. Organizational only — a neutral tally of already-decided
// runs; no verdict/confidence is derived or shown (ADR-0001). Origins are rendered verbatim (never
// relabelled). The index scope carries no per-artifact manifest, so size is n_artifacts + bytes.
function ArchiveIndexBody({ d }: { d: ArchiveDigest }) {
  const running = d.by_status.running ?? 0
  const inReview = d.by_status.needs_review ?? 0
  const held = running + inReview
  const stat = 'flex flex-col rounded-lg border border-line bg-card-2 px-2.5 py-1.5'
  return (
    <div className="flex flex-col gap-3">
      {/* Readiness — grounds the header's "never touches an active run" in real lifecycle counts. */}
      <div className="rounded-[9px] border border-line bg-card-2 px-3 py-2.5 text-[11.5px] text-text-2">
        {d.archive_ready
          ? `All ${d.n_runs} covered runs are released and archive-ready.`
          : `${d.n_archive_ready} of ${d.n_runs} runs released and archive-ready.`}
        {held > 0 && (
          <span className="text-text-3">
            {' '}
            {held} held from archival ({running} running · {inReview} in review).
          </span>
        )}
      </div>
      <div className="grid grid-cols-4 gap-2">
        <div className={stat}>
          <span className="text-[10px] text-text-3">Runs</span>
          <span className="text-[14px] font-semibold text-text">{d.n_runs}</span>
        </div>
        <div className={stat}>
          <span className="text-[10px] text-text-3">Samples</span>
          <span className="text-[14px] font-semibold text-text">{d.n_samples}</span>
        </div>
        <div className={stat}>
          <span className="text-[10px] text-text-3">Artifacts</span>
          <span className="text-[14px] font-semibold text-text">{d.n_artifacts}</span>
        </div>
        <div className={stat}>
          <span className="text-[10px] text-text-3">Size</span>
          <span className="text-[14px] font-semibold text-text">{humanBytes(d.total_size_bytes)}</span>
        </div>
      </div>
      {Object.keys(d.by_origin).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(d.by_origin).map(([o, n]) => (
            <span key={o} className="rounded-md border border-line bg-card px-2 py-0.5 font-mono text-[10px] text-text-2">
              {o} = {n}
            </span>
          ))}
        </div>
      )}
      <div className="rounded-xl border border-line px-3 py-2.5">
        <div className="text-[9px] font-bold uppercase tracking-[0.4px] text-text-3">Proposed action</div>
        <div className="mt-1 text-[12px] leading-relaxed text-text-2">{d.proposed_action || '—'}</div>
      </div>
      {d.recurring_signatures.length > 0 && (
        <div className="flex flex-col gap-1">
          <div className="text-[9px] font-bold uppercase tracking-[0.4px] text-text-3">Recurring signatures</div>
          {d.recurring_signatures.slice(0, 3).map((s) => (
            <div key={s.signature} className="flex items-center gap-2 text-[11px] text-text-2">
              <span className="min-w-0 flex-1 truncate">{s.title}</span>
              <span className="shrink-0 font-mono text-[10px] text-text-3">
                {s.gate} · {s.count}×
              </span>
            </div>
          ))}
        </div>
      )}
      {d.summary && <div className="text-[12px] leading-relaxed text-text-2">{d.summary}</div>}
      <div className="flex items-center gap-2 text-[10px] text-text-3">
        <span className="rounded border border-line bg-card-2 px-1.5 py-0.5 font-mono">
          {d.generated_by}
          {d.model ? ` · ${d.model}` : ''}
        </span>
      </div>
      {/* The real advisory disclaimer from the backend, verbatim. */}
      <div className="text-[10px] leading-snug text-text-3">{d.disclaimer}</div>
    </div>
  )
}

// The proposed-node header + icon-picker use the shared icon vocabulary.
function ICON_GLYPH(key: IconKey) {
  const Icon = ICONS[key]
  return <Icon size={15} />
}

function SparkleGlyph() {
  return (
    <svg width={17} height={17} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.4 2.4M15.3 15.3l2.4 2.4M17.7 6.3l-2.4 2.4M8.7 15.3l-2.4 2.4" />
    </svg>
  )
}
