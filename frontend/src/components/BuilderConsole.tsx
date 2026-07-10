import { useState } from 'react'
import { Check, Copy, Download, FileText, ShieldCheck } from 'lucide-react'
import {
  VAL_ROWS,
  dryRows,
  type ConsoleTab,
  type DryStatus,
  type LocEdits,
} from './BuilderShared'

// Bottom console (README §6): a collapsed bar that expands to a tabbed pane —
// Validate (static typed checks, click-to-focus) · Diff (current locators vs last-Emit
// snapshot) · Dry run (locator resolution vs a mock run dir — paths only) — beside the live
// run_layout.yaml with Copy / Download. Diff + Dry run resolve client-side so the demo works
// offline; api.pipelineDiff / api.dryRunPipeline are the wired production seams.

const SEV: Record<'ok' | 'info', { c: string; bg: string }> = {
  ok: { c: '#1a854e', bg: '#e9f6ee' },
  info: { c: '#1f6feb', bg: 'var(--color-accent-weak)' },
}
const DRY_CHIP: Record<DryStatus, string> = {
  matched: 'text-proceed-fg bg-proceed-bg border-proceed-bd',
  ambiguous: 'text-hold-fg bg-hold-bg border-hold-bd',
  missing: 'text-escalate-fg bg-escalate-bg border-escalate-bd',
}

type ConsoleProps = {
  open: boolean
  tab: ConsoleTab
  profile: string
  yaml: string
  emitted: boolean
  isSarek: boolean
  envHint: string
  curLoc: Record<string, string>
  emittedSnap: Record<string, string> | null
  locEdits: LocEdits
  selected: string | null
  onToggle: () => void
  onTab: (t: ConsoleTab) => void
  onSelect: (id: string) => void
}

export function BuilderConsole(props: ConsoleProps) {
  const [copied, setCopied] = useState(false)
  const tabs: { k: ConsoleTab; l: string }[] = [
    { k: 'validate', l: 'Validate' },
    { k: 'diff', l: 'Diff' },
    { k: 'dryrun', l: 'Dry run' },
  ]

  const onCopy = () => {
    navigator.clipboard
      ?.writeText(props.yaml)
      .then(() => {
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1500)
      })
      .catch(() => {})
  }
  const onDownload = () => {
    const blob = new Blob([props.yaml], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'run_layout.yaml'
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  const dry = dryRows(props.locEdits)
  const dryStats = `matched ${dry.filter((r) => r.status === 'matched').length} · ambiguous ${
    dry.filter((r) => r.status === 'ambiguous').length
  } · missing ${dry.filter((r) => r.status === 'missing').length}`

  const snap = props.emittedSnap
  const diffRows = snap
    ? Object.keys(props.curLoc)
        .filter((k) => props.curLoc[k] !== snap[k])
        .map((k) => ({ kind: k, before: snap[k] ?? '(absent)', after: props.curLoc[k] }))
    : []

  return (
    <div className="shrink-0 border-t border-line bg-card">
      <button onClick={props.onToggle} className="flex h-9 w-full items-center gap-2 px-4 text-left">
        <ShieldCheck size={15} className="text-proceed" />
        <span className="text-[12.5px] font-semibold text-text">Validate &amp; emit console</span>
        <span className="rounded-full border border-proceed-bd bg-proceed-bg px-2.5 py-0.5 text-[11.5px] font-medium text-proceed-fg">
          {props.emitted ? 'Emitted' : 'Ready to emit'}
        </span>
        <span className="ml-auto font-mono text-[11px] text-text-3">{props.envHint}</span>
      </button>

      {props.open && (
        <div className="flex h-[240px] min-h-0 border-t border-line">
          {/* left — tabbed checks */}
          <div className="min-w-0 flex-1 overflow-y-auto border-r border-line px-4 py-3.5">
            <div className="mb-3 inline-flex gap-0.5 rounded-lg border border-line bg-card-2 p-0.5">
              {tabs.map((t) => (
                <button
                  key={t.k}
                  onClick={() => props.onTab(t.k)}
                  className={`rounded-md px-3 py-1 text-[11.5px] ${
                    props.tab === t.k ? 'bg-card font-semibold text-text shadow-card' : 'font-medium text-text-2 hover:text-text'
                  }`}
                >
                  {t.l}
                </button>
              ))}
            </div>

            {props.tab === 'validate' && (
              <div>
                <div className="mb-3 flex items-center gap-2 rounded-[9px] border border-proceed-bd bg-proceed-bg px-3 py-2.5">
                  <Check size={16} className="text-proceed" />
                  <span className="text-[12.5px] font-semibold text-proceed-fg">Typed I/O connects · config ready to emit</span>
                </div>
                <div className="flex flex-col gap-1.5">
                  {VAL_ROWS.map((v) => {
                    const st = SEV[v.sev]
                    const target = v.focus ?? props.selected ?? 'n_fastp'
                    const active = target === props.selected
                    return (
                      <button
                        key={v.code}
                        onClick={() => props.onSelect(target)}
                        title="Focus the referenced node"
                        className={`flex w-full items-start gap-2 rounded-lg border border-line bg-card px-2.5 py-2 text-left transition-colors hover:border-line-strong ${
                          active ? 'ring-1 ring-accent' : ''
                        }`}
                      >
                        <span className="shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px] font-bold" style={{ color: st.c, background: st.bg }}>
                          {v.code}
                        </span>
                        <span className="text-[11.5px] leading-snug text-text-2">{v.msg}</span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {props.tab === 'diff' &&
              (!snap ? (
                <div className="rounded-[9px] border border-dashed border-line-strong p-3.5 text-[12px] leading-relaxed text-text-2">
                  No emitted version yet. Click <strong className="text-text">Emit</strong> to snapshot the config, then edit a locator to see the diff.
                </div>
              ) : diffRows.length === 0 ? (
                <div className="flex items-center gap-2 rounded-[9px] border border-proceed-bd bg-proceed-bg px-3 py-2.5">
                  <Check size={15} className="text-proceed" />
                  <span className="text-[12px] font-medium text-proceed-fg">No changes since last emit.</span>
                </div>
              ) : (
                <div>
                  <div className="mb-2 text-[11px] text-text-3">{diffRows.length} locator(s) changed since the last emitted config</div>
                  <div className="flex flex-col gap-2">
                    {diffRows.map((d) => (
                      <div key={d.kind} className="rounded-[9px] border border-hold-bd bg-hold-bg px-3 py-2.5">
                        <div className="mb-1.5 font-mono text-[11.5px] font-semibold text-text">{d.kind}</div>
                        <div className="mb-0.5 font-mono text-[10px] text-escalate-fg line-through">{d.before}</div>
                        <div className="font-mono text-[10px] text-proceed-fg">{d.after}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}

            {props.tab === 'dryrun' && (
              <div>
                <div className="mb-2 text-[11px] text-text-3">
                  Locator resolution against a mock run dir · <span className="font-mono">{dryStats}</span>
                </div>
                <div className="flex flex-col">
                  {dry.map((d) => (
                    <div key={d.kind} className="flex items-center gap-2 border-b border-line py-2">
                      <span className="w-[132px] shrink-0 truncate font-mono text-[11px] text-text">{d.kind}</span>
                      <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.3px] ${DRY_CHIP[d.status]}`}>
                        {d.status}
                      </span>
                      <span className="min-w-0 flex-1 truncate font-mono text-[10px] text-text-3">{d.detail}</span>
                    </div>
                  ))}
                </div>
                <p className="mt-2.5 text-[10.5px] leading-relaxed text-text-3">
                  Dry-run resolves paths only — it reads no bytes and runs nothing. A real run dir is checked at ingest.
                </p>
              </div>
            )}
          </div>

          {/* right — the live YAML */}
          <div className="flex w-[47%] shrink-0 flex-col bg-card-2">
            <div className="flex items-center gap-2 border-b border-line bg-card px-3.5 py-2.5">
              <FileText size={14} className="text-text-2" />
              <span className="font-mono text-[12px] font-semibold text-text">run_layout.yaml</span>
              <div className="ml-auto flex gap-2">
                <button
                  onClick={onCopy}
                  className="inline-flex items-center gap-1 rounded-md border border-line-strong bg-card px-2 py-1 text-[11px] text-text-2 hover:text-text"
                >
                  <Copy size={12} /> {copied ? 'Copied' : 'Copy'}
                </button>
                <button
                  onClick={onDownload}
                  className="inline-flex items-center gap-1 rounded-md border border-line-strong bg-card px-2 py-1 text-[11px] text-text-2 hover:text-text"
                >
                  <Download size={12} /> Download
                </button>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-auto px-3.5 py-3">
              {props.isSarek && (
                <div className="mb-2.5 rounded-md border border-hold-bd bg-hold-bg px-2.5 py-1.5 text-[10.5px] text-hold-fg">
                  sarek profile is illustrative / target-state — not yet wired end-to-end.
                </div>
              )}
              <pre className="m-0 whitespace-pre font-mono text-[10.5px] leading-relaxed text-text">{props.yaml}</pre>
              {props.emitted && (
                <div className="mt-3 flex items-start gap-2 rounded-lg border border-proceed-bd bg-proceed-bg px-3 py-2.5 text-[11px] text-proceed-fg">
                  <Check size={14} className="mt-0.5 shrink-0" />
                  <span>
                    Wrote <span className="font-mono">src/pipeguard/layout/run_layout.yaml</span>. Emit writes the config only — no tool runs. The live
                    gate's consumption of an arbitrary layout is Phase 2.
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
