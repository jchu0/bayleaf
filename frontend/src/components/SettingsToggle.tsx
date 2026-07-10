// The Settings pill toggle (dc.html 2734): 38×22 track, 18px knob, accent when on. Shared by
// the notification channels and the "Live synthesis" switch so both read identically.
export function SettingsToggle({
  on,
  onChange,
  label,
}: {
  on: boolean
  onChange?: (v: boolean) => void
  label?: string
}) {
  return (
    <button
      type="button"
      onClick={() => onChange?.(!on)}
      aria-pressed={on}
      aria-label={label}
      className={`relative inline-block h-[22px] w-[38px] shrink-0 rounded-full transition-colors ${
        on ? 'bg-accent' : 'bg-line-strong'
      }`}
    >
      <span
        className={`absolute top-[2px] h-[18px] w-[18px] rounded-full bg-white shadow-sm transition-all ${
          on ? 'left-[18px]' : 'left-[2px]'
        }`}
      />
    </button>
  )
}
