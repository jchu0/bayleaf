import { useState } from 'react'
import { SettingsToggle } from './SettingsToggle'

// Model tiering (dc.html 1246-1263, 2713-2732). A model per agent, narration-only — verdicts
// stay rule-derived (ADR-0001), so nothing here can move a gate. List pricing ($ in / out per
// 1M tokens) is ILLUSTRATIVE, not a live or contractual quote. The roster includes Fable 5.
type ModelKey = 'opus' | 'sonnet' | 'haiku' | 'fable'

const MODELS: { key: ModelKey; name: string; cost: string }[] = [
  { key: 'opus', name: 'Claude Opus 4.8', cost: '$5 / $25' },
  { key: 'sonnet', name: 'Claude Sonnet 5', cost: '$3 / $15' },
  { key: 'haiku', name: 'Claude Haiku 4.5', cost: '$1 / $5' },
  { key: 'fable', name: 'Claude Fable 5', cost: '$0.50 / $2.50' },
]

const AGENTS: { key: string; label: string; desc: string; def: ModelKey }[] = [
  { key: 'synthesizer', label: 'Card synthesizer', desc: 'Narrates decision cards', def: 'sonnet' },
  { key: 'triage', label: 'Triage agent', desc: 'Answers the "Ask the agent" chat', def: 'sonnet' },
  { key: 'feedback', label: 'Feedback learner', desc: 'Summarizes reviewer overrides', def: 'haiku' },
]

export function SettingsModelTier() {
  const [synthLive, setSynthLive] = useState(false)
  const [models, setModels] = useState<Record<string, ModelKey>>(
    Object.fromEntries(AGENTS.map((a) => [a.key, a.def])),
  )

  return (
    <section className="rounded-[13px] border border-line bg-card px-[18px] py-[17px]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[14.5px] font-semibold text-text">Model tiering</div>
          <p className="mt-[3px] text-[12.5px] text-text-2">
            A model per agent — narration only, verdicts stay rule-derived. Offline uses the
            deterministic stub at $0.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-[9px]">
          <span className="text-[12px] font-medium text-text-2">Live synthesis</span>
          <SettingsToggle on={synthLive} onChange={setSynthLive} label="Live synthesis" />
        </div>
      </div>

      <div className="mt-[13px] flex flex-col gap-[9px]">
        {AGENTS.map((a) => {
          const cur = models[a.key] ?? a.def
          const cost = MODELS.find((m) => m.key === cur)?.cost ?? ''
          return (
            <div
              key={a.key}
              className="flex items-center gap-[14px] rounded-[11px] border border-line px-[14px] py-[11px]"
            >
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-semibold text-text">{a.label}</div>
                <div className="text-[11.5px] text-text-2">{a.desc}</div>
              </div>
              <span className="shrink-0 font-mono text-[10.5px] text-text-3">{cost} / 1M</span>
              <select
                value={cur}
                onChange={(e) => setModels((prev) => ({ ...prev, [a.key]: e.target.value as ModelKey }))}
                aria-label={`${a.label} model`}
                className="min-w-[158px] shrink-0 cursor-pointer rounded-lg border border-line-strong bg-card px-[11px] py-[7px] text-[12.5px] font-medium text-text focus:border-accent focus:outline-none"
              >
                {MODELS.map((m) => (
                  <option key={m.key} value={m.key}>
                    {m.name}
                  </option>
                ))}
              </select>
            </div>
          )
        })}
      </div>
    </section>
  )
}
