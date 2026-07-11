import { type ReactNode } from 'react'
import { ChevronRight, Database, Gavel, Layers, ShieldCheck, X } from 'lucide-react'
import { GATE_CHECKPOINTS } from './BuilderShared'

// (PASS-6 B) A READ-ONLY view of the DETERMINISTIC BOUNDARY, opened from the toolbar's ⋯ More menu. It shows
// the handoff from what the operator COMPOSES (the tool graph on the canvas) into the deterministic ingest →
// decision gate → verdict. This boundary is NOT part of the canvas: rules decide the verdict, it is not
// composable (ADR-0001). Neutral styling — NO verdict palette (the checkpoint dots are the gate's category
// colours, not the proceed/hold/escalate verdict palette). Always available (not linked-run-only).
export function DecisionBoundaryModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="w-[760px] max-w-full overflow-hidden rounded-2xl border border-line bg-card shadow-pop"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-line px-5 py-3.5">
          <div>
            <h2 className="font-serif text-[18px] font-medium text-text">Decision boundary</h2>
            <p className="mt-0.5 text-[12px] text-text-3">The deterministic handoff — rules decide; not part of what you compose.</p>
          </div>
          <button
            onClick={onClose}
            className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-text-2 hover:bg-page"
            aria-label="Close"
          >
            <X size={17} />
          </button>
        </div>

        <div className="px-5 py-5">
          {/* The handoff, left → right: what you compose → deterministic ingest → decision gate → verdict. */}
          <div className="flex items-stretch gap-1.5">
            <BoundaryStage icon={<Layers size={15} />} title="Composed pipeline" sub="what you build">
              <p className="text-[11px] leading-snug text-text-3">
                The tool graph you compose on the canvas (fastp → … → MultiQC / File output). Its terminus outputs are what a run produces.
              </p>
            </BoundaryStage>
            <Arrow />
            <BoundaryStage icon={<Database size={15} />} title="Deterministic ingest" sub="non-composable" dashed>
              <p className="font-mono text-[10.5px] text-text-2">write_run_dir → run/</p>
              <p className="mt-1 text-[11px] leading-snug text-text-3">Writes the run directory (5 CSVs) the gate reads. Automatic — not a card you place.</p>
            </BoundaryStage>
            <Arrow />
            <BoundaryStage icon={<ShieldCheck size={15} />} title="Decision gate" sub="terminal · reads run/" dashed>
              <p className="mb-1.5 text-[11px] leading-snug text-text-3">Checkpoints:</p>
              <div className="flex flex-col gap-1">
                {GATE_CHECKPOINTS.map((c) => (
                  <div key={c.label} className="flex items-center gap-1.5">
                    <span className="h-[7px] w-[7px] shrink-0 rounded-full" style={{ background: c.c }} />
                    <span className="text-[11px] text-text-2">{c.label}</span>
                  </div>
                ))}
              </div>
            </BoundaryStage>
            <Arrow />
            <BoundaryStage icon={<Gavel size={15} />} title="Verdict" sub="rules decide">
              <p className="text-[11px] leading-snug text-text-3">
                <span className="font-mono text-text-2">proceed · hold · rerun · escalate</span> — set by the deterministic rules, never by the LLM or by what you compose.
              </p>
            </BoundaryStage>
          </div>

          <div className="mt-4 rounded-lg border border-line bg-card-2 px-3.5 py-2.5">
            <p className="text-[12px] leading-relaxed text-text-2">
              This is the <span className="font-semibold text-text">deterministic boundary</span>: every run passes through ingest → gate automatically. The verdict is set by <span className="font-semibold">rules</span> — it is <span className="font-semibold">not</span> part of what you compose on the canvas. For a specific run's full gate story, open <span className="font-mono text-[11px]">Decision cards</span> or <span className="font-mono text-[11px]">Provenance</span> from ⋯ More.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

// One stage card in the boundary flow. `dashed` marks a non-composable deterministic stage (ingest / gate),
// echoing their canvas look; the composed-pipeline + verdict stages use a solid frame. Neutral throughout.
function BoundaryStage({ icon, title, sub, dashed, children }: { icon: ReactNode; title: string; sub: string; dashed?: boolean; children: ReactNode }) {
  return (
    <div className={`flex-1 rounded-xl border bg-card px-3 py-2.5 ${dashed ? 'border-dashed border-line-strong' : 'border-line'}`}>
      <div className="flex items-center gap-2">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-card-2 text-text-2">{icon}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[12px] font-bold text-text">{title}</span>
          <span className="block truncate font-mono text-[9.5px] text-text-3">{sub}</span>
        </span>
      </div>
      <div className="mt-2">{children}</div>
    </div>
  )
}

function Arrow() {
  return (
    <div className="flex shrink-0 items-center self-center text-text-3">
      <ChevronRight size={18} />
    </div>
  )
}
