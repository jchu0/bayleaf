import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Archive,
  Check,
  Copy,
  Download,
  FileCode,
  Loader2,
  Play,
  TriangleAlert,
  Wrench,
  X,
} from 'lucide-react'
import { api } from '../api'
import { FALLBACK_SUMMARY } from './ReviewRepairCard'
import { useToast } from './Toast'
import type {
  AgentProposal,
  ArchiveDigest,
  CompiledNextflow,
  MonitoringSignature,
  NextflowGraphBody,
  NodePortSpec,
  NodeProposal,
  RunInputsCatalog,
} from '../types'

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

// ── Author a tool node (advisory · agent #6) ─────────────────────────────────
// Wired to the REAL node-authoring agent (GET /api/builder/node-proposal). A natural-language
// request → an advisory NodeProposal the operator reviews. It renders the proposal VERBATIM — typed
// ports (live vs reserved), pinned version, suggested locators, cited rationale, and the four
// version coordinates. It never auto-adds a card, wires an edge, or touches a verdict (ADR-0001);
// the runnable script:/stub: body is authored by a human in the ProcessSpec catalog, never here
// (compose ≠ execute). Accepting a proposal into the palette is a labelled next slice.
const NODE_SEED_REQUEST = 'add a tool that trims adapters and does read QC'

export function AuthorToolNodeModal({ onClose }: { onClose: () => void }) {
  const { toast } = useToast()
  const [draft, setDraft] = useState(NODE_SEED_REQUEST) // the text box (editable)
  const [request, setRequest] = useState(NODE_SEED_REQUEST) // the submitted request we fetch for
  const [proposal, setProposal] = useState<NodeProposal | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false) // true → honest "agent unavailable"

  // Fetch the advisory proposal whenever the SUBMITTED request changes (Propose / Enter). On any
  // failure we show an honest "agent unavailable" — the gate, the runs, and the canvas are unaffected.
  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(false)
    setProposal(null)
    api
      .nodeProposal(request)
      .then((p) => {
        if (!alive) return
        setProposal(p)
        setLoading(false)
      })
      .catch(() => {
        if (!alive) return
        setError(true)
        setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [request])

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setRequest(draft.trim())
  }
  const copyProposal = () => {
    if (!proposal) return
    navigator.clipboard?.writeText(JSON.stringify(proposal, null, 2)).catch(() => {})
    toast('Copied the proposal JSON. Adding it to the palette is a confirm-gated next slice — the agent never auto-adds.', 'info')
  }

  const liveChip = 'inline-flex items-center gap-1 rounded-md border border-proceed-bd bg-proceed-bg px-2 py-0.5 font-mono text-[10.5px] text-proceed-fg'
  const reservedChip = 'inline-flex items-center gap-1 rounded-md border border-hold-bd bg-hold-bg px-2 py-0.5 font-mono text-[10.5px] text-hold-fg'
  const portRow = (ports: NodePortSpec[]) =>
    ports.length === 0 ? (
      <span className="text-[10.5px] text-text-3">none</span>
    ) : (
      ports.map((p, i) => (
        <span key={`${p.kind}-${i}`} className={p.known ? liveChip : reservedChip} title={p.note ?? undefined}>
          {p.known ? <Check size={11} /> : <TriangleAlert size={10} />} {p.kind}
          {!p.required && <span className="opacity-60">?</span>}
        </span>
      ))
    )

  return (
    <ModalShell width={640} onClose={onClose}>
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
          roster #6 · advisory
        </span>
        <CloseBtn onClose={onClose} />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto bg-card-2 p-4">
        {/* Request — a natural-language ask or a bare tool name. The agent retrieves over a curated
            corpus; it cannot onboard a genuinely new tool (a labelled limit — no doc-drop parser). */}
        <form onSubmit={submit} className="flex items-center gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Describe a tool by name or function — e.g. 'mosdepth' or 'call variants'"
            aria-label="Tool request"
            className="min-w-0 flex-1 rounded-lg border border-line-strong bg-card px-3 py-2 text-[12.5px] text-text outline-none focus:border-accent"
          />
          <button
            type="submit"
            className="shrink-0 rounded-lg bg-accent px-3.5 py-2 text-[12.5px] font-semibold text-white shadow-card hover:opacity-90"
          >
            Propose
          </button>
        </form>
        <div className="mt-1.5 text-[10px] text-text-3">
          Retrieves a match from an 11-card curated corpus (this pipeline's tools + reference nodes). Stub-first ($0); flip to Claude to rephrase the prose only.
        </div>

        <div className="mt-3.5">
          {loading ? (
            <p className="inline-flex items-center gap-1.5 text-[12.5px] text-text-3">
              <Loader2 size={13} className="animate-spin" /> Asking the node-authoring agent…
            </p>
          ) : error ? (
            <div className="flex items-start gap-2 rounded-[9px] border border-hold-bd bg-hold-bg px-3 py-2.5 text-[11.5px] text-hold-fg">
              <TriangleAlert size={14} className="mt-0.5 shrink-0" />
              <span>The node-authoring agent is unavailable, so no proposal can be shown. Nothing about the runs, the canvas, or the gate is affected.</span>
            </div>
          ) : proposal && !proposal.matched ? (
            // No corpus match → the conservative defer-to-human proposal (fabricates no tool/ports).
            <div className="rounded-xl border border-line bg-card px-3.5 py-3">
              <div className="text-[12.5px] font-semibold text-text">No tool-card matched</div>
              <p className="mt-1 text-[12px] leading-relaxed text-text-2">{proposal.summary}</p>
              <p className="mt-1.5 text-[11px] leading-relaxed text-text-3">{proposal.rationale}</p>
            </div>
          ) : proposal ? (
            <div className="flex flex-col gap-2.5">
              <div className="text-[10px] font-bold uppercase tracking-[0.5px] text-text-3">Proposed ToolNode · review</div>
              {/* The proposed node card — tool/version/stage + typed ports, all from the corpus. */}
              <div className="overflow-hidden rounded-xl border border-line bg-card">
                <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px] font-semibold text-text">{proposal.tool}</div>
                    <div className="mt-0.5 font-mono text-[10px] text-text-3">
                      {proposal.version} · {proposal.stage ?? 'stage —'} · suggested
                    </div>
                  </div>
                  <span className="shrink-0 rounded bg-card-2 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-[0.3px] text-text-3">advisory</span>
                </div>
                <div className="flex flex-col gap-2.5 px-3 py-2.5">
                  <div>
                    <div className="mb-1.5 text-[9.5px] font-semibold uppercase tracking-[0.3px] text-text-3">Input ports</div>
                    <div className="flex flex-wrap gap-1.5">{portRow(proposal.inputs)}</div>
                  </div>
                  <div>
                    <div className="mb-1.5 text-[9.5px] font-semibold uppercase tracking-[0.3px] text-text-3">Output ports</div>
                    <div className="flex flex-wrap gap-1.5">{portRow(proposal.outputs)}</div>
                  </div>
                </div>
              </div>

              {proposal.reserved_kinds.length > 0 && (
                <div className="flex items-start gap-2 rounded-[9px] border border-hold-bd bg-hold-bg px-3 py-2.5 text-[11px] text-hold-fg">
                  <TriangleAlert size={14} className="mt-0.5 shrink-0" />
                  <span>
                    <strong>{proposal.reserved_kinds.length} reserved kind{proposal.reserved_kinds.length === 1 ? '' : 's'}</strong> (
                    <span className="font-mono">{proposal.reserved_kinds.join(', ')}</span>) — a real-but-unregistered I/O, surfaced{' '}
                    <strong>never invented</strong> and never wired. Registering one is a governed change to the{' '}
                    <span className="font-mono">ArtifactKind</span> vocabulary, not a fabrication.
                  </span>
                </div>
              )}

              {/* Summary + rationale (the model's only prose on the live path; corpus-grounded on the stub). */}
              <div className="rounded-xl border border-line bg-card px-3.5 py-2.5">
                <div className="text-[12.5px] leading-relaxed text-text-2">{proposal.summary}</div>
                <div className="mt-1.5 text-[11px] leading-relaxed text-text-3">{proposal.rationale}</div>
              </div>

              {proposal.locators.length > 0 && (
                <div>
                  <div className="mb-1 text-[9.5px] font-semibold uppercase tracking-[0.3px] text-text-3">Suggested locators</div>
                  <div className="flex flex-col gap-1">
                    {proposal.locators.map((l, i) => (
                      <div key={`${l.kind}-${i}`} className="flex items-center gap-2 font-mono text-[10px] text-text-3">
                        <span className="rounded border border-line bg-card-2 px-1.5 py-0.5 text-text-2">{l.kind}</span>
                        <span className="min-w-0 truncate">{l.field}: {l.loc}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {proposal.citations.length > 0 && (
                <div className="flex flex-col gap-1 border-t border-line pt-2">
                  {proposal.citations.map((c, i) => (
                    <div key={`${c.ref}-${i}`} className="font-mono text-[10px] text-text-3">
                      {c.source_kind} · {c.ref}
                      {c.title ? ` — ${c.title}` : ''}
                      {c.score != null ? ` · ${(c.score * 100).toFixed(0)}% (heuristic)` : ''}
                    </div>
                  ))}
                </div>
              )}

              <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-text-3">
                <span className="rounded border border-line bg-card-2 px-1.5 py-0.5 font-mono">{proposal.mode === 'claude' ? `claude · ${proposal.model}` : 'stub · $0'}</span>
                <span className="rounded border border-line bg-card-2 px-1.5 py-0.5 font-mono">
                  corpus {proposal.corpus_version} · schema v{proposal.schema_version} · platform {proposal.platform_version}
                </span>
              </div>

              <div className="text-[10px] leading-snug text-text-3">{proposal.disclaimer}</div>
            </div>
          ) : null}
        </div>
      </div>

      <div className="flex items-center gap-2.5 border-t border-line px-4 py-3">
        <span className="flex-1 text-[10.5px] leading-snug text-text-3">
          Advisory · stub-first ($0). The agent proposes a card — it never draws an edge, places a node on the gate, or auto-adds.
        </span>
        <button onClick={onClose} className="rounded-lg border border-line bg-card px-3 py-1.5 text-[12.5px] text-text-2 hover:border-line-strong">
          Discard
        </button>
        <button
          onClick={copyProposal}
          disabled={!proposal || !proposal.matched}
          className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-1.5 text-[12.5px] font-semibold text-white shadow-card hover:opacity-90 disabled:opacity-50"
        >
          <Copy size={14} /> Copy proposal
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
        <span className="shrink-0 whitespace-nowrap rounded-full border border-[#cfe0fb] bg-accent-weak px-2 py-0.5 text-[10px] font-semibold text-accent-strong">advisory · read-only</span>
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
          Open review queue
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
        <span className="shrink-0 whitespace-nowrap rounded-full border border-[#cfe0fb] bg-accent-weak px-2 py-0.5 text-[10px] font-semibold text-accent-strong">advisory · read-only</span>
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
        <span className="flex-1 text-[10.5px] leading-snug text-text-3">Advisory — this previews the archival manifest; PipeGuard has no archive-write endpoint, so nothing is queued or moved.</span>
        <button onClick={onClose} className="rounded-lg border border-line bg-card px-3 py-1.5 text-[12.5px] text-text-2 hover:border-line-strong">
          Dismiss
        </button>
        <button onClick={onClose} className="rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12.5px] font-medium text-text hover:border-line">
          Close (preview only)
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

function SparkleGlyph() {
  return (
    <svg width={17} height={17} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.4 2.4M15.3 15.3l2.4 2.4M17.7 6.3l-2.4 2.4M8.7 15.3l-2.4 2.4" />
    </svg>
  )
}

// ── Export to Nextflow (compose → a runnable DSL2 pipeline; ADR-0003) ─────────
// Compiles the CURRENT Builder card graph into a real nf-core-style Nextflow pipeline via
// POST /api/pipelines/compile. It COMPOSES — the backend emits text, it never runs a tool or
// touches a verdict (compose ≠ execute). Preview main.nf + download the full .zip bundle.
export function NextflowExportModal({ graph, onClose }: { graph: NextflowGraphBody; onClose: () => void }) {
  const { toast } = useToast()
  const [result, setResult] = useState<CompiledNextflow | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    let live = true
    setResult(null)
    setError(null)
    api
      .compileNextflow(graph)
      .then((r) => live && setResult(r))
      .catch((e) => live && setError(e instanceof Error ? e.message : String(e)))
    return () => {
      live = false
    }
  }, [graph])

  const copy = () => {
    if (!result) return
    navigator.clipboard?.writeText(result.main_nf)
    setCopied(true)
    setTimeout(() => setCopied(false), 1400)
  }
  const download = async () => {
    setDownloading(true)
    try {
      const blob = await api.compileNextflowZip(graph)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${result?.name ?? 'pipeline'}-nextflow.zip`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), 'error')
    } finally {
      setDownloading(false)
    }
  }

  const moduleCount = result
    ? Object.keys(result.files).filter((f) => f.startsWith('modules/')).length
    : 0

  return (
    <ModalShell width={780} onClose={onClose}>
      <div className="flex items-start gap-3 border-b border-line px-5 py-4">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-accent-weak text-accent-strong">
          <FileCode size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold text-text">Export to Nextflow</div>
          <div className="mt-0.5 text-[12px] leading-relaxed text-text-2">
            PipeGuard compiles these cards into a runnable nf-core-style DSL2 pipeline. Download it to
            run anywhere, or use <strong>Run</strong> to execute it here (only AI agents stay off the
            tools — operators run pipelines). Validate with{' '}
            <code className="rounded bg-card-2 px-1 py-px font-mono">nextflow run main.nf -stub-run</code>.
          </div>
        </div>
        <CloseBtn onClose={onClose} />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {error ? (
          <div className="flex items-center gap-2 rounded-lg border border-escalate-bd bg-escalate-bg px-3 py-2.5 text-[12.5px] text-escalate-fg">
            <TriangleAlert size={15} className="shrink-0" /> Couldn't compile: {error}
          </div>
        ) : !result ? (
          <div className="flex items-center gap-2 py-10 text-[12.5px] text-text-3">
            <Loader2 size={15} className="animate-spin" /> Compiling…
          </div>
        ) : (
          <>
            <div className="mb-3 flex flex-wrap items-center gap-1.5">
              {result.steps.map((s, i) => (
                <span key={s} className="inline-flex items-center gap-1.5">
                  {i > 0 && <span className="text-text-3">→</span>}
                  <span className="rounded-md border border-line bg-card-2 px-2 py-0.5 font-mono text-[11px] text-text-2">
                    {s}
                  </span>
                </span>
              ))}
            </div>
            <div className="mb-2 text-[11.5px] text-text-3">
              {Object.keys(result.files).length} files · {moduleCount} process modules + main.nf +
              nextflow.config
            </div>
            <div className="mb-1.5 font-mono text-[10.5px] uppercase tracking-wide text-text-3">main.nf</div>
            <pre className="max-h-[320px] overflow-auto rounded-lg border border-line bg-card-2 p-3 font-mono text-[11px] leading-relaxed text-text-2">
              {result.main_nf}
            </pre>
          </>
        )}
      </div>

      <div className="flex items-center justify-end gap-2 border-t border-line px-5 py-3">
        <button
          onClick={copy}
          disabled={!result}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-card px-3 py-1.5 text-[12.5px] text-text-2 hover:border-line-strong disabled:opacity-50"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? 'Copied' : 'Copy main.nf'}
        </button>
        <button
          onClick={download}
          disabled={!result || downloading}
          className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-1.5 text-[12.5px] font-semibold text-white hover:opacity-90 disabled:opacity-50"
        >
          <Download size={14} />
          {downloading ? 'Preparing…' : 'Download .zip'}
        </button>
      </div>
    </ModalShell>
  )
}

// ── Run pipeline (REAL execution; operator picks inputs; ADR-0003) ────────────
// PipeGuard COMPOSES the pipeline; Nextflow EXECUTES it. A human operator absolutely can run it —
// the compose≠execute guardrail is about AI *agents* (advisory, never run a tool/set a verdict) and
// the decision *core* (framework-agnostic), not about operators. Compiles the current graph, runs it
// via `POST /api/pipelines/run` against the operator's chosen inputs, polls to a gate-able run.
const _REF_KINDS = new Set(['reference_fasta', 'panel_bed', 'truth_vcf'])
const _KIND_CAT: Record<string, 'reads' | 'reference' | 'panel_bed'> = {
  fastq: 'reads',
  reference_fasta: 'reference',
  panel_bed: 'panel_bed',
}
function requiredCategories(g: NextflowGraphBody): ('reads' | 'reference' | 'panel_bed')[] {
  const isSource = (n: NextflowGraphBody['nodes'][number]) =>
    n.ins.length === 0 && n.outs.length > 0 && n.outs.every((o) => _REF_KINDS.has(o))
  const byId = new Map(g.nodes.map((n) => [n.id, n]))
  const incoming = new Map<string, { node: string; idx: number }>()
  for (const e of g.edges) incoming.set(`${e.to.node}:${e.to.idx}`, e.from)
  const cats = new Set<'reads' | 'reference' | 'panel_bed'>()
  for (const n of g.nodes) {
    if (isSource(n)) continue
    n.ins.forEach((kind, i) => {
      const from = incoming.get(`${n.id}:${i}`)
      const external = !from || (byId.get(from.node) ? isSource(byId.get(from.node)!) : false)
      if (external && _KIND_CAT[kind]) cats.add(_KIND_CAT[kind])
    })
  }
  return (['reads', 'reference', 'panel_bed'] as const).filter((c) => cats.has(c))
}

const _CAT_LABEL: Record<string, string> = {
  reads: 'Reads (fastq)',
  reference: 'Reference FASTA',
  panel_bed: 'Panel BED',
}

export function RunPipelineModal({
  graph,
  name,
  version,
  onClose,
}: {
  // `graph` (the live canvas) drives the input picker only; the run itself executes the APPROVED
  // stored baseline named by `name` (+ optional pinned `version`), resolved server-side — the run
  // affordance is gated to `approved`, so the live graph IS the approved one (ADR-0014).
  graph: NextflowGraphBody
  name: string
  version?: number
  onClose: () => void
}) {
  const nav = useNavigate()
  const { toast } = useToast()
  const [cat, setCat] = useState<RunInputsCatalog | null>(null)
  const [choice, setChoice] = useState<Record<string, string>>({})
  const [runId, setRunId] = useState('')
  const [sample, setSample] = useState('HG002')
  const [phase, setPhase] = useState<'form' | 'running' | 'complete' | 'failed'>('form')
  const [err, setErr] = useState<string | null>(null)
  const needed = requiredCategories(graph)

  useEffect(() => {
    api
      .runInputs()
      .then((c) => {
        setCat(c)
        // Auto-pick the only option per needed category.
        const pre: Record<string, string> = {}
        for (const k of needed) if (c[k].length === 1) pre[k] = c[k][0].key
        setChoice((prev) => ({ ...pre, ...prev }))
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
    // A stable, human default run id; the operator can edit it.
    const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '')
    setRunId(`PIPE-${stamp}`)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const missing = needed.filter((k) => !choice[k])
  const canRun = phase === 'form' && runId.trim() !== '' && missing.length === 0

  const poll = (id: string) => {
    const tick = () =>
      api
        .runStatus(id)
        .then((s) => {
          if (s.status === 'complete') setPhase('complete')
          else if (s.status === 'failed') {
            setErr(s.error ?? 'run failed')
            setPhase('failed')
          } else window.setTimeout(tick, 2500)
        })
        .catch((e) => {
          // A 404 / network drop is TERMINAL, not a retry: the in-memory job registry lost this run
          // (a backend restart or blip), so polling forever would spin "Running…" with no honest
          // failure (P1-5). Stop, surface it, and point the operator at the durable Runs list.
          const detail = e instanceof Error ? e.message : String(e)
          setErr(`Lost track of this run — check the Runs list. (${detail})`)
          setPhase('failed')
          toast('Lost track of the run — check the Runs list', 'error')
        })
    tick()
  }

  const run = async () => {
    setPhase('running')
    setErr(null)
    try {
      // Run the APPROVED baseline by name (+ pinned version) — the backend resolves + compiles the
      // stored approved graph, never this posted one (the approval gate, ADR-0014).
      const ack = await api.runPipeline({
        name,
        ...(version != null ? { version } : {}),
        run_id: runId.trim(),
        sample: sample.trim() || 'HG002',
        inputs: choice,
      })
      poll(ack.run_id)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
      setPhase('failed')
    }
  }

  return (
    <ModalShell width={620} onClose={onClose}>
      <div className="flex items-start gap-3 border-b border-line px-5 py-4">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-accent-weak text-accent-strong">
          <Play size={17} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold text-text">Run pipeline</div>
          <div className="mt-0.5 text-[12px] leading-relaxed text-text-2">
            Runs the <strong>approved version</strong> of this pipeline (the current canvas graph,
            once approved) against your chosen inputs → a gate-able run. PipeGuard composes;{' '}
            <strong>Nextflow executes</strong> (only AI agents stay off the tools — operators run
            pipelines).
          </div>
        </div>
        <CloseBtn onClose={onClose} />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {phase === 'complete' ? (
          <div className="flex flex-col items-start gap-3 py-4">
            <div className="flex items-center gap-2 text-[13px] font-semibold text-proceed-fg">
              <Check size={16} /> Run complete — the pipeline executed and the gate decided.
            </div>
            <button
              onClick={() => nav(`/runs/${encodeURIComponent(runId.trim())}`)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-1.5 text-[12.5px] font-semibold text-white hover:opacity-90"
            >
              View decision card →
            </button>
          </div>
        ) : phase === 'failed' ? (
          <div className="flex flex-col gap-3">
            <div className="flex items-start gap-2 rounded-lg border border-escalate-bd bg-escalate-bg px-3 py-2.5 text-[12.5px] text-escalate-fg">
              <TriangleAlert size={15} className="mt-px shrink-0" />
              <span className="break-words">{err ?? 'The run failed.'}</span>
            </div>
            <button
              onClick={() => setPhase('form')}
              className="w-fit rounded-lg border border-line bg-card px-3 py-1.5 text-[12.5px] text-text-2 hover:border-line-strong"
            >
              Back
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-3.5">
            <div className="grid grid-cols-2 gap-3">
              <label className="text-[11.5px] text-text-3">
                Run id
                <input
                  value={runId}
                  onChange={(e) => setRunId(e.target.value)}
                  disabled={phase === 'running'}
                  className="mt-1 w-full rounded-lg border border-line bg-card px-2.5 py-1.5 font-mono text-[12px] text-text outline-none focus:border-accent"
                />
              </label>
              <label className="text-[11.5px] text-text-3">
                Sample id
                <input
                  value={sample}
                  onChange={(e) => setSample(e.target.value)}
                  disabled={phase === 'running'}
                  className="mt-1 w-full rounded-lg border border-line bg-card px-2.5 py-1.5 font-mono text-[12px] text-text outline-none focus:border-accent"
                />
              </label>
            </div>
            {needed.length === 0 && (
              <div className="text-[12px] text-text-3">This graph needs no external inputs.</div>
            )}
            {needed.map((k) => {
              const opts = cat?.[k] ?? []
              return (
                <label key={k} className="text-[11.5px] text-text-3">
                  {_CAT_LABEL[k]}
                  <select
                    value={choice[k] ?? ''}
                    onChange={(e) => setChoice((p) => ({ ...p, [k]: e.target.value }))}
                    disabled={phase === 'running'}
                    className="mt-1 w-full rounded-lg border border-line bg-card px-2.5 py-1.5 text-[12.5px] text-text outline-none focus:border-accent"
                  >
                    <option value="">{opts.length ? 'Choose…' : 'none available on server'}</option>
                    {opts.map((o) => (
                      <option key={o.key} value={o.key}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </label>
              )
            })}
            <div className="text-[11px] text-text-3">
              Inputs are the real files present on the server (operator uploads are a labelled seam).
            </div>
          </div>
        )}
      </div>

      {phase !== 'complete' && phase !== 'failed' && (
        <div className="flex items-center justify-end gap-2 border-t border-line px-5 py-3">
          <button
            onClick={onClose}
            className="rounded-lg border border-line bg-card px-3 py-1.5 text-[12.5px] text-text-2 hover:border-line-strong"
          >
            Cancel
          </button>
          <button
            onClick={run}
            disabled={!canRun}
            className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-1.5 text-[12.5px] font-semibold text-white hover:opacity-90 disabled:opacity-50"
          >
            {phase === 'running' ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            {phase === 'running' ? 'Running…' : 'Run pipeline'}
          </button>
        </div>
      )}
    </ModalShell>
  )
}
