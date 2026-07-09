import { type ReactNode, useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorBox, Loading } from '../components/States'
import type { MetricCatalog, QCThreshold, Runbook } from '../types'

// Runbook gates are stored in CANONICAL units (fraction for %-metrics, x for coverage);
// `unit` is only the display symbol. Convert to the display number an operator reads (an 85%
// gate is stored 0.85) — used both for read-out and to seed the editable threshold inputs.
function toDisplayNum(value: number, unit: string): number {
  const shown = unit === '%' ? value * 100 : value
  return Math.round(shown * 100) / 100
}

// Per-model list pricing is ILLUSTRATIVE ($ per million tokens, input / output) — shown to
// make the tiering tradeoff legible, not a live or contractual quote.
const MODELS = [
  { id: 'opus', name: 'Claude Opus 4.8', note: 'Highest capability', costIn: 15, costOut: 75 },
  { id: 'sonnet', name: 'Claude Sonnet 5', note: 'Balanced — default tier', costIn: 3, costOut: 15 },
  { id: 'haiku', name: 'Claude Haiku 4.5', note: 'Fastest / cheapest', costIn: 1, costOut: 5 },
] as const

function Section({ title, desc, children }: { title: string; desc?: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-line bg-card p-5 shadow-card">
      <h3 className="text-[15px] font-semibold text-text">{title}</h3>
      {desc && <p className="mt-0.5 text-[12.5px] text-text-2">{desc}</p>}
      <div className="mt-3">{children}</div>
    </section>
  )
}

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!on)}
      className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${on ? 'bg-accent' : 'bg-line-strong'}`}
      aria-pressed={on}
    >
      <span
        className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-all ${on ? 'left-[18px]' : 'left-0.5'}`}
      />
    </button>
  )
}

function NotClinical({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center rounded border border-hold-bd bg-hold-bg px-2 py-0.5 text-[10.5px] font-medium uppercase tracking-wide text-hold-fg">
      {label}
    </span>
  )
}

export function Settings() {
  const [runbook, setRunbook] = useState<Runbook | null>(null)
  const [catalog, setCatalog] = useState<MetricCatalog | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [profile, setProfile] = useState<'lean' | 'granular'>('granular')
  const [slackOn, setSlackOn] = useState(true)
  const [model, setModel] = useState<(typeof MODELS)[number]['id']>('sonnet')
  const [synth, setSynth] = useState<'stub' | 'claude'>('stub')
  // Local-only "what-if" edits to the QC thresholds (display units). Demo affordance — never
  // persisted to the runbook and never touches a verdict (rules decide; this is config-preview).
  const [edits, setEdits] = useState<Record<string, { gate: string; hard_fail: string }>>({})
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api
      .config()
      .then((rb) => {
        setRunbook(rb)
        // Seed the editable inputs from the live runbook, in display units.
        setEdits(
          Object.fromEntries(
            rb.qc_thresholds.map((t) => [
              t.metric,
              { gate: String(toDisplayNum(t.gate, t.unit)), hard_fail: String(toDisplayNum(t.hard_fail, t.unit)) },
            ]),
          ),
        )
      })
      .catch((e) => setError(String(e)))
    api.metricsRegistry().then(setCatalog).catch(() => setCatalog(null))
  }, [])

  if (error) return <ErrorBox message={error} />
  if (!runbook) return <Loading label="Loading config…" />

  const granular = profile === 'granular'

  function editThreshold(t: QCThreshold, field: 'gate' | 'hard_fail', value: string) {
    setEdits((prev) => ({
      ...prev,
      [t.metric]: { ...(prev[t.metric] ?? { gate: '', hard_fail: '' }), [field]: value },
    }))
    setSaved(false)
  }

  return (
    <div className="mx-auto max-w-[720px] space-y-4">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-text">Settings</h1>
        <p className="mt-1 text-[13px] text-text-2">
          Operator profile, notify channel, model tiering, and the QC runbook — mostly informational
          for the demo.
        </p>
      </div>

      <Section title="Operator profile" desc="Lean shows the essentials; Granular exposes every gate + metric.">
        <div className="flex w-fit overflow-hidden rounded-lg border border-line">
          {(['lean', 'granular'] as const).map((p) => (
            <button
              key={p}
              onClick={() => setProfile(p)}
              className={`px-3.5 py-1.5 text-[13px] capitalize ${
                profile === p ? 'bg-card-2 font-medium text-text' : 'bg-card text-text-2 hover:text-text'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </Section>

      <Section title="Notifications" desc="Actionable cards post to Slack — off by default; the live send is env-armed.">
        <div className="flex items-center justify-between">
          <span className="text-[13px] text-text">
            Slack <span className="font-mono text-[12px] text-text-3">#cc-ls-demo</span>
          </span>
          <Toggle on={slackOn} onChange={setSlackOn} />
        </div>
      </Section>

      <Section title="Model tiering" desc="Per-agent model; the deterministic gate needs no model. List pricing is illustrative $/Mtok.">
        <div className="space-y-1.5">
          {MODELS.map((m) => (
            <button
              key={m.id}
              onClick={() => setModel(m.id)}
              className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left transition-colors ${
                model === m.id ? 'border-accent bg-accent-weak' : 'border-line hover:border-line-strong'
              }`}
            >
              <span
                className={`grid h-4 w-4 shrink-0 place-items-center rounded-full border ${
                  model === m.id ? 'border-accent' : 'border-line-strong'
                }`}
              >
                {model === m.id && <span className="h-2 w-2 rounded-full bg-accent" />}
              </span>
              <span className="flex-1">
                <span className="block text-[13px] font-medium text-text">{m.name}</span>
                <span className="block text-[11.5px] text-text-3">{m.note}</span>
              </span>
              <span className="shrink-0 text-right">
                <span className="block font-mono text-[12px] text-text">
                  ${m.costIn} / ${m.costOut}
                </span>
                <span className="block text-[10px] uppercase tracking-wide text-text-3">in / out · per Mtok</span>
              </span>
            </button>
          ))}
        </div>
        <div className="mt-3 flex items-center justify-between border-t border-line pt-3">
          <span className="text-[13px] text-text">
            Narration synthesis{' '}
            <span className="text-text-3">— {synth === 'stub' ? 'rule-derived stub ($0)' : 'live Claude'}</span>
          </span>
          <div className="flex overflow-hidden rounded-lg border border-line">
            {(['stub', 'claude'] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSynth(s)}
                className={`px-2.5 py-1 text-[12px] capitalize ${
                  synth === s ? 'bg-card-2 font-medium text-text' : 'bg-card text-text-2 hover:text-text'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </Section>

      <Section
        title="QC thresholds"
        desc="The active runbook for the current profile (single profile shown). Edit a value for a local what-if — demo only, never persisted and never routes a verdict."
      >
        <div className="mb-3">
          <NotClinical label="Illustrative · configurable · not clinical" />
        </div>
        <div className="overflow-hidden rounded-lg border border-line">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="bg-card-2 text-left text-[10.5px] uppercase tracking-wide text-text-3">
                <th className="px-3 py-2 font-medium">Metric</th>
                {granular && <th className="px-3 py-2 font-medium">Unit</th>}
                <th className="px-3 py-2 font-medium">Gate</th>
                <th className="px-3 py-2 font-medium">Borderline</th>
                <th className="px-3 py-2 font-medium">Hard-fail</th>
                {granular && <th className="px-3 py-2 font-medium">Direction</th>}
              </tr>
            </thead>
            <tbody>
              {runbook.qc_thresholds.map((t) => {
                const edit = edits[t.metric] ?? {
                  gate: String(toDisplayNum(t.gate, t.unit)),
                  hard_fail: String(toDisplayNum(t.hard_fail, t.unit)),
                }
                // Borderline is derived from the (possibly edited) gate × band, so an edit to
                // the gate visibly moves the band — keeps the what-if internally consistent.
                const gateNum = parseFloat(edit.gate)
                const borderline = Number.isFinite(gateNum)
                  ? `±${Math.round(gateNum * t.borderline_band * 100) / 100}${t.unit}`
                  : '—'
                return (
                  <tr key={t.metric} className="border-t border-line">
                    <td className="px-3 py-2">
                      {t.label} <span className="font-mono text-[11px] text-text-3">{t.metric}</span>
                    </td>
                    {granular && (
                      <td className="px-3 py-2 font-mono text-[12px] text-text-2">{t.unit || '—'}</td>
                    )}
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1">
                        <input
                          type="number"
                          value={edit.gate}
                          onChange={(e) => editThreshold(t, 'gate', e.target.value)}
                          aria-label={`${t.label} gate threshold`}
                          className="w-16 rounded border border-line bg-card px-1.5 py-0.5 font-mono text-[12px] text-text focus:border-accent focus:outline-none"
                        />
                        {t.unit && <span className="font-mono text-[11px] text-text-3">{t.unit}</span>}
                      </span>
                    </td>
                    <td className="px-3 py-2 font-mono text-[12px] text-text-2">{borderline}</td>
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1">
                        <input
                          type="number"
                          value={edit.hard_fail}
                          onChange={(e) => editThreshold(t, 'hard_fail', e.target.value)}
                          aria-label={`${t.label} hard-fail threshold`}
                          className="w-16 rounded border border-line bg-card px-1.5 py-0.5 font-mono text-[12px] text-text focus:border-accent focus:outline-none"
                        />
                        {t.unit && <span className="font-mono text-[11px] text-text-3">{t.unit}</span>}
                      </span>
                    </td>
                    {granular && (
                      <td className="px-3 py-2 text-[12px] text-text-2">
                        {t.higher_is_better ? '≥ higher is better' : '≤ lower is better'}
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            onClick={() => setSaved(true)}
            className="rounded-lg border border-accent bg-accent px-3 py-1.5 text-[12.5px] font-medium text-white transition-colors hover:bg-accent-strong"
          >
            Save thresholds
          </button>
          {saved ? (
            <span className="text-[12px] font-medium text-proceed-fg">
              Saved locally · demo — not persisted to the runbook.
            </span>
          ) : (
            <span className="text-[12px] text-text-3">
              Local what-if only — edits stay in this browser session.
            </span>
          )}
        </div>

        <p className="mb-1.5 mt-4 text-[10.5px] font-semibold uppercase tracking-wide text-text-3">
          Required intake metadata
        </p>
        <div className="flex flex-wrap gap-1.5">
          {runbook.require_metadata_fields.map((f) => (
            <span key={f} className="rounded border border-line bg-card-2 px-2 py-1 font-mono text-[11px] text-text-2">
              {f}
            </span>
          ))}
        </div>
      </Section>

      {granular && catalog && (
        <Section
          title="Metric catalog"
          desc={`Registered metric vocabulary (registry v${catalog.metric_registry_version}) — ${catalog.n_gated} of ${catalog.n_registered} gated by the runbook today; the rest are vocabulary the gate can adopt without new code.`}
        >
          <div className="mb-3">
            <NotClinical label="Vocabulary · versioned · configurable · not clinical" />
          </div>
          <div className="overflow-hidden rounded-lg border border-line">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="bg-card-2 text-left text-[10.5px] uppercase tracking-wide text-text-3">
                  <th className="px-3 py-2 font-medium">Metric</th>
                  <th className="px-3 py-2 font-medium">Gate</th>
                  <th className="px-3 py-2 font-medium">Category</th>
                  <th className="px-3 py-2 font-medium">Unit</th>
                  <th className="px-3 py-2 text-right font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {catalog.entries.map((e) => (
                  <tr key={e.our_key} className="border-t border-line">
                    <td className="px-3 py-2">
                      {e.display_name} <span className="font-mono text-[11px] text-text-3">{e.our_key}</span>
                    </td>
                    <td className="px-3 py-2 font-mono text-[11px] text-text-2">{e.gate}</td>
                    <td className="px-3 py-2 text-[12px] text-text-2">{e.category}</td>
                    <td className="px-3 py-2 font-mono text-[11px] text-text-2">{e.canonical_unit}</td>
                    <td className="px-3 py-2 text-right">
                      {e.gated ? (
                        <span className="inline-flex rounded border border-proceed-bd bg-proceed-bg px-1.5 py-0.5 text-[10px] font-medium text-proceed-fg">
                          Gated
                        </span>
                      ) : (
                        <span className="inline-flex rounded border border-line bg-card-2 px-1.5 py-0.5 text-[10px] font-medium text-text-3">
                          Registered
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}
    </div>
  )
}
