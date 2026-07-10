import { useState } from 'react'
import { Check, Copy, Download, FileText, Play, ShieldCheck } from 'lucide-react'
import type { DiffResult, DryRunResult } from '../types'
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
  // Backend seams: once the pipeline is Saved, Dry-run/Diff can resolve against the REAL endpoints
  // (POST /{name}/dry-run, GET /{name}/diff) instead of only the client-side preview.
  savedName: string | null
  dryRun: DryRunResult | null
  dryRunBusy: boolean
  onDryRun: (runId: string) => void
  diff: DiffResult | null
  diffBusy: boolean
  onDiff: () => void
}

const RESOLVE_CHIP: Record<string, string> = {
  matched: 'text-proceed-fg bg-proceed-bg border-proceed-bd',
  ambiguous: 'text-hold-fg bg-hold-bg border-hold-bd',
  missing: 'text-escalate-fg bg-escalate-bg border-escalate-bd',
  invalid: 'text-escalate-fg bg-escalate-bg border-escalate-bd',
}

export function BuilderConsole(props: ConsoleProps) {
  const [copied, setCopied] = useState(false)
  const [runId, setRunId] = useState('mock_run_01') // the run dir Dry-run resolves against
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

            {props.tab === 'diff' && (
              <div>
                {/* Backend diff (GET /{name}/diff) once saved; else the client-side vs-last-Emit preview. */}
                <div className="mb-2 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={props.onDiff}
                    disabled={!props.savedName || props.diffBusy}
                    className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-card px-2.5 py-1 text-[11px] font-medium text-text-2 hover:border-line disabled:opacity-50"
                    title={props.savedName ? 'Diff the saved graph vs its approved baseline' : 'Save the pipeline first'}
                  >
                    Diff vs approved baseline
                  </button>
                  <span className="text-[10.5px] text-text-3">
                    {props.savedName ? (props.diffBusy ? 'diffing…' : `saved: ${props.savedName}`) : 'client-side preview — Save to diff against the store'}
                  </span>
                </div>
                {props.diff ? (
                  props.diff.added.length + props.diff.removed.length + props.diff.changed.length === 0 ? (
                    <div className="flex items-center gap-2 rounded-[9px] border border-proceed-bd bg-proceed-bg px-3 py-2.5">
                      <Check size={15} className="text-proceed" />
                      <span className="text-[12px] font-medium text-proceed-fg">
                        {props.diff.has_baseline ? 'No drift from the approved baseline.' : 'No emitted baseline yet — nothing to diff.'}
                      </span>
                    </div>
                  ) : (
                    <div className="flex flex-col gap-2">
                      <div className="text-[11px] text-text-3">
                        vs v{props.diff.emitted_version ?? '—'} · {props.diff.added.length} added · {props.diff.changed.length} changed · {props.diff.removed.length} removed · {props.diff.unchanged_count} unchanged
                      </div>
                      {[...props.diff.added.map((d) => ['added', d] as const), ...props.diff.changed.map((d) => ['changed', d] as const), ...props.diff.removed.map((d) => ['removed', d] as const)].map(([kind, d]) => (
                        <div key={`${kind}-${d.key}`} className="rounded-[9px] border border-line px-3 py-2">
                          <div className="mb-1 flex items-center gap-2 font-mono text-[11.5px] font-semibold text-text">
                            {d.kind}
                            <span className={`rounded-full border px-1.5 py-px text-[9px] font-semibold uppercase ${kind === 'added' ? 'text-proceed-fg bg-proceed-bg border-proceed-bd' : kind === 'removed' ? 'text-escalate-fg bg-escalate-bg border-escalate-bd' : 'text-hold-fg bg-hold-bg border-hold-bd'}`}>
                              {kind}
                            </span>
                          </div>
                          {d.before && <div className="font-mono text-[10px] text-escalate-fg line-through">{JSON.stringify(d.before)}</div>}
                          {d.after && <div className="font-mono text-[10px] text-proceed-fg">{JSON.stringify(d.after)}</div>}
                        </div>
                      ))}
                    </div>
                  )
                ) : !snap ? (
                  <div className="rounded-[9px] border border-dashed border-line-strong p-3.5 text-[12px] leading-relaxed text-text-2">
                    No emitted version yet. Click <strong className="text-text">Emit</strong> to snapshot the config, then edit a locator to see the diff — or Save + diff against the approved baseline.
                  </div>
                ) : diffRows.length === 0 ? (
                  <div className="flex items-center gap-2 rounded-[9px] border border-proceed-bd bg-proceed-bg px-3 py-2.5">
                    <Check size={15} className="text-proceed" />
                    <span className="text-[12px] font-medium text-proceed-fg">No changes since last emit.</span>
                  </div>
                ) : (
                  <div className="flex flex-col gap-2">
                    <div className="text-[11px] text-text-3">{diffRows.length} locator(s) changed since the last emitted config (preview)</div>
                    {diffRows.map((d) => (
                      <div key={d.kind} className="rounded-[9px] border border-hold-bd bg-hold-bg px-3 py-2.5">
                        <div className="mb-1.5 font-mono text-[11.5px] font-semibold text-text">{d.kind}</div>
                        <div className="mb-0.5 font-mono text-[10px] text-escalate-fg line-through">{d.before}</div>
                        <div className="font-mono text-[10px] text-proceed-fg">{d.after}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {props.tab === 'dryrun' && (
              <div>
                {/* Backend dry-run (POST /{name}/dry-run?run_id=…) once saved; else client-side preview. */}
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <input
                    value={runId}
                    onChange={(e) => setRunId(e.target.value)}
                    placeholder="run id"
                    className="w-[150px] rounded-md border border-line bg-card px-2 py-1 font-mono text-[11px] text-text outline-none focus:border-accent"
                  />
                  <button
                    type="button"
                    onClick={() => props.onDryRun(runId.trim())}
                    disabled={!props.savedName || props.dryRunBusy || !runId.trim()}
                    className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-card px-2.5 py-1 text-[11px] font-medium text-text-2 hover:border-line disabled:opacity-50"
                    title={props.savedName ? 'Resolve the saved graph against this run dir' : 'Save the pipeline first'}
                  >
                    <Play size={11} /> Resolve against run
                  </button>
                  <span className="text-[10.5px] text-text-3">
                    {props.savedName ? (props.dryRunBusy ? 'resolving…' : `saved: ${props.savedName}`) : 'client-side preview — Save to resolve against a real run dir'}
                  </span>
                </div>
                {props.dryRun ? (
                  <>
                    <div className="mb-2 text-[11px] text-text-3">
                      v{props.dryRun.version} vs run <span className="font-mono">{props.dryRun.run_id}</span> ·{' '}
                      <span className="font-mono">
                        matched {props.dryRun.summary.matched ?? 0} · ambiguous {props.dryRun.summary.ambiguous ?? 0} · missing {props.dryRun.summary.missing ?? 0} · invalid {props.dryRun.summary.invalid ?? 0}
                      </span>
                    </div>
                    <div className="flex flex-col">
                      {props.dryRun.locators.map((l, i) => (
                        <div key={`${l.kind}-${i}`} className="flex items-center gap-2 border-b border-line py-2">
                          <span className="w-[132px] shrink-0 truncate font-mono text-[11px] text-text">{l.kind}</span>
                          <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.3px] ${RESOLVE_CHIP[l.status] ?? RESOLVE_CHIP.missing}`}>
                            {l.status}
                          </span>
                          <span className="min-w-0 flex-1 truncate font-mono text-[10px] text-text-3">
                            {l.paths.length ? l.paths.join(', ') : l.pattern}
                          </span>
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="mb-2 text-[11px] text-text-3">
                      Locator resolution against a mock run dir (preview) · <span className="font-mono">{dryStats}</span>
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
                  </>
                )}
                <p className="mt-2.5 text-[10.5px] leading-relaxed text-text-3">
                  Dry-run resolves paths only — it reads no bytes and runs nothing (compose ≠ execute). A real run dir is checked at ingest.
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
