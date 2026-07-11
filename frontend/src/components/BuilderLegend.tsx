import { useState, type CSSProperties } from 'react'
import { X } from 'lucide-react'

// Legend for the Pipeline-Builder card system (design mockup): port colour by data-kind, port state,
// and wire types — so a viewer can read what the coloured half-circles + wires mean. A dismissible
// bottom-right panel, collapsed to a small chip by default so it stays out of the way. Theme-aware:
// reads the SAME --k-* / --color-* tokens the cards + wires render with, so it never drifts.

const KIND_ROWS: { c: string; label: string; eg: string; outline?: boolean }[] = [
  { c: 'var(--k-reads)', label: 'Reads', eg: 'fastq' },
  { c: 'var(--k-align)', label: 'Alignment', eg: 'bam · bai' },
  { c: 'var(--k-var)', label: 'Variants', eg: 'vcf · filtered_vcf' },
  { c: 'var(--k-qc)', label: 'QC / metrics', eg: 'fastp_json · mosdepth' },
  { c: 'var(--k-ref)', label: 'Reference', eg: 'reference_fasta · panel_bed', outline: true },
]

// Port-state swatches mirror portVisualStyle (required solid / optional 40% fill / reserved dashed
// hollow / reference outlined), sampled on the alignment hue so the four states read side by side.
const STATE_ROWS: [string, CSSProperties][] = [
  ['required', { background: 'var(--k-align)', border: '1.5px solid var(--k-align)' }],
  ['optional', { background: 'color-mix(in srgb, var(--k-align) 40%, transparent)', border: '1.5px solid var(--k-align)' }],
  ['reserved', { background: 'transparent', border: '1.5px dashed var(--k-cfg)', opacity: 0.7 }],
  ['reference · outlined', { background: 'var(--color-card)', border: '1.5px solid var(--k-ref)' }],
]

const WIRE_ROWS: [string, string, boolean][] = [
  ['data · kind-coloured', 'var(--k-align)', false],
  ['QC fan-in', 'var(--k-qc)', false],
  ['reference', 'var(--k-ref)', true],
]

// The category-tag chips stamped on every in-card box row (refine pass) — one consistent set: REQ /
// REF / OPT / RSVD. Styles mirror RowTagChip so the key never drifts from the cards.
const TAG_ROWS: [string, CSSProperties][] = [
  ['REQ', { background: 'var(--color-card-2)', color: 'var(--color-text-2)' }],
  ['REF', { background: 'color-mix(in srgb, var(--k-ref) 18%, transparent)', color: 'var(--k-ref)' }],
  ['OPT', { background: 'var(--color-accent-weak)', color: 'var(--color-accent-strong)' }],
  ['RSVD', { background: 'var(--color-card-3)', color: 'var(--color-text-3)' }],
]

// The card's LEFT SPINE carries the run-status (batch 3a) — a coloured left bar, distinct from the
// small outlined port-number markers that now sit OUTSIDE the card. Reads the bound-run vstatus.
const STATUS_ROWS: [string, string][] = [
  ['passed', 'var(--color-proceed)'],
  ['needs attention', 'var(--color-hold)'],
  ['blocked', 'var(--color-escalate)'],
  ['not run', '#c6ced7'],
]

export function BuilderLegend({ edit }: { edit: boolean }) {
  const [open, setOpen] = useState(false)
  // Anchored TOP-LEFT of the canvas. In Edit mode the Connect / Tidy / Undo action cluster occupies
  // the very top-left corner, so drop the legend just below it; in View mode it hugs the corner.
  const top = edit ? 52 : 14
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="absolute z-[7] rounded-lg border border-line-strong bg-card px-2.5 py-1.5 text-[11px] font-medium text-text-2 shadow-card hover:border-line"
        style={{ left: 14, top }}
      >
        Legend
      </button>
    )
  }
  return (
    <div className="absolute z-[7] w-[214px] rounded-xl border border-line-strong bg-card p-3 shadow-pop" style={{ left: 14, top }}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[11px] font-bold uppercase tracking-[0.5px] text-text-2">Legend</span>
        <button
          type="button"
          onClick={() => setOpen(false)}
          title="Hide legend"
          className="grid h-5 w-5 place-items-center rounded text-text-3 hover:bg-page hover:text-text-2"
        >
          <X size={13} />
        </button>
      </div>

      <div className="mb-1 text-[8.5px] font-bold uppercase tracking-[0.4px] text-text-3">Port colour · data-kind</div>
      {KIND_ROWS.map((k) => (
        <div key={k.label} className="flex items-center gap-2 py-[2px]">
          <span
            className="h-[11px] w-[11px] shrink-0 rounded-full"
            style={k.outline ? { background: 'var(--color-card)', border: `1.5px solid ${k.c}` } : { background: k.c }}
          />
          <span className="text-[11px] text-text">{k.label}</span>
          <span className="ml-auto truncate pl-2 font-mono text-[8.5px] text-text-3">{k.eg}</span>
        </div>
      ))}

      <div className="mb-1 mt-2.5 text-[8.5px] font-bold uppercase tracking-[0.4px] text-text-3">Port state</div>
      {STATE_ROWS.map(([label, st]) => (
        <div key={label} className="flex items-center gap-2 py-[2px]">
          <span className="h-[11px] w-[11px] shrink-0 rounded-full" style={st} />
          <span className="text-[11px] text-text-2">{label}</span>
        </div>
      ))}

      <div className="mb-1 mt-2.5 text-[8.5px] font-bold uppercase tracking-[0.4px] text-text-3">Box row tags</div>
      <div className="flex flex-wrap items-center gap-1">
        {TAG_ROWS.map(([label, st]) => (
          <span key={label} className="rounded px-1 py-[1.5px] text-[7.5px] font-bold uppercase leading-none" style={st}>
            {label}
          </span>
        ))}
      </div>
      <div className="mt-1 text-[10px] text-text-3">one per port row · number · kind · dir · tag</div>

      <div className="mb-1 mt-2.5 text-[8.5px] font-bold uppercase tracking-[0.4px] text-text-3">Wires</div>
      {WIRE_ROWS.map(([label, c, dashed]) => (
        <div key={label} className="flex items-center gap-2 py-[2px]">
          <span className="h-0 w-6 shrink-0" style={{ borderTop: `2px ${dashed ? 'dashed' : 'solid'} ${c}` }} />
          <span className="text-[11px] text-text-2">{label}</span>
        </div>
      ))}

      <div className="mb-1 mt-2.5 text-[8.5px] font-bold uppercase tracking-[0.4px] text-text-3">Run status · left spine</div>
      {STATUS_ROWS.map(([label, c]) => (
        <div key={label} className="flex items-center gap-2 py-[2px]">
          <span className="ml-1 h-[13px] w-[3px] shrink-0 rounded-sm" style={{ background: c }} />
          <span className="text-[11px] text-text-2">{label}</span>
        </div>
      ))}
      <div className="mt-1.5 flex items-center gap-2">
        <span className="grid h-[13px] w-[13px] shrink-0 place-items-center rounded-full border border-text-3 bg-card text-[7px] font-bold leading-none text-text-2">3</span>
        <span className="text-[10px] text-text-3">port numbers — outside the port, keyed to the boxes</span>
      </div>
    </div>
  )
}
