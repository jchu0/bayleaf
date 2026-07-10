import { useState } from 'react'
import { Archive, ArrowRight, Check, Play, TriangleAlert, Upload, Wrench, X } from 'lucide-react'
import {
  AUTHOR_FLAGS,
  ICONS,
  ICON_CHOICES,
  RUN_STEPS,
  STAR_HELP,
  type IconKey,
} from './BuilderShared'

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
export function RunHandoffModal({ envHint, onClose }: { envHint: string; onClose: () => void }) {
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
        <button onClick={onClose} className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-1.5 text-[12.5px] font-semibold text-white shadow-card hover:opacity-90">
          <ArrowRight size={14} />
          Hand off to Nextflow
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
  const chip = 'rounded-md border border-line bg-card-2 px-2 py-1 font-mono text-[10px] text-text-2'
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
      <div className="px-4 py-4">
        <p className="mb-3 text-[12.5px] leading-relaxed text-text-2">
          Watches recurring failure signatures across runs and drafts a fix for a human to review. It{' '}
          <strong className="text-text">never edits the pipeline or changes a verdict</strong> — off the critical path, like every agent here.
        </p>
        <div className="overflow-hidden rounded-xl border border-line">
          <div className="flex items-center gap-2 border-b border-line bg-accent-weak px-3 py-2.5">
            <span className="text-[9px] font-bold uppercase tracking-[0.4px] text-accent-strong">Proposed fix</span>
            <span className="ml-auto font-mono text-[10px] text-text-3">signature PROV-001 · seen 3×/14d</span>
          </div>
          <div className="px-3 py-3">
            <div className="text-[13px] font-semibold text-text">Add an index-distance guard to demux</div>
            <div className="mt-1 text-[12px] leading-relaxed text-text-2">
              Enforce min Hamming ≥ 3 between declared indices and fail closed on i5 collisions. Prevents the barcode/index mismatch class seen in
              S4/S5.
            </div>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              <span className={chip}>attachTo demux</span>
              <span className={chip}>scope preflight</span>
              <span className={chip}>stub · $0</span>
            </div>
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2.5 border-t border-line px-4 py-3">
        <span className="flex-1 text-[10.5px] leading-snug text-text-3">Advisory only — routing a fix to the queue still needs approver sign-off.</span>
        <button onClick={onClose} className="rounded-lg border border-line bg-card px-3 py-1.5 text-[12.5px] text-text-2 hover:border-line-strong">
          Dismiss
        </button>
        <button onClick={onClose} className="rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12.5px] font-medium text-text hover:border-line">
          Send to review queue
        </button>
      </div>
    </ModalShell>
  )
}

// ── Archivist (advisory) ─────────────────────────────────────────────────────
export function ArchivistModal({ onClose }: { onClose: () => void }) {
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
      <div className="px-4 py-4">
        <p className="mb-3 text-[12.5px] leading-relaxed text-text-2">
          Proposes moving a <strong className="text-text">released</strong> run's <span className="font-mono">run/</span> directory to cold storage with
          a signed manifest, so the provenance ledger stays intact after the working copy ages out.
        </p>
        <div className="rounded-xl border border-line px-3 py-3">
          <div className="font-mono text-[12px] font-semibold text-text">RUN-2026-07-06-A · run/ → cold storage</div>
          <div className="mt-1 text-[11.5px] leading-relaxed text-text-2">
            Manifest of the 5 <span className="font-mono">run/</span> CSVs + sha256; original left read-only until the archive is verified.
          </div>
          <div className="mt-2 font-mono text-[10px] text-text-3">s3://pipeguard-cold/2026/07/RUN-2026-07-06-A/</div>
        </div>
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
