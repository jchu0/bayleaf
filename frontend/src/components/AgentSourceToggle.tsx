// Live/offline source toggle for the Agent triage header (dc.html 1093-1096, 2705-2708).
// A pill button that swaps the triage source between the live model and the rule-derived
// (offline) fallback. INV: this only reflects/requests a *narration* source — it never sets
// or changes the verdict/confidence, which the rule engine owns.
export function AgentSourceToggle({
  live,
  label,
  onToggle,
}: {
  live: boolean
  label: string
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      title="Switch the triage narration source (advisory — never changes the verdict)"
      className="inline-flex shrink-0 items-center gap-2 rounded-full border border-line-strong bg-card py-[5px] pl-3 pr-1.5"
    >
      <span className="text-[11.5px] font-medium text-text-2">{label}</span>
      {/* 34×19 switch track; accent when live, neutral (--surface-3 → card-3) when offline. */}
      <span
        className={`relative inline-block h-[19px] w-[34px] rounded-full transition-colors ${
          live ? 'bg-accent' : 'bg-card-3'
        }`}
      >
        <span
          className={`absolute top-[2px] h-[15px] w-[15px] rounded-full bg-white shadow-[0_1px_2px_rgba(0,0,0,.25)] transition-[left] ${
            live ? 'left-[17px]' : 'left-[2px]'
          }`}
        />
      </span>
    </button>
  )
}
