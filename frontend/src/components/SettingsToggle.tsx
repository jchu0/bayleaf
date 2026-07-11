// The Settings pill toggle (dc.html 2734): 38×22 track, 18px knob, accent when on. Shared by
// the notification channels and the "Live synthesis" switch so both read identically.
//
// `disabled` keeps the toggle legible (state still reads off the knob position) but non-mutable —
// the UIC-4 edit/save gate: a consequential switch (notifications on/off, model live/stub) must
// not flip on a stray click, so it renders locked until its row/panel is put in edit mode.
export function SettingsToggle({
  on,
  onChange,
  label,
  disabled,
}: {
  on: boolean
  onChange?: (v: boolean) => void
  label?: string
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      onClick={() => onChange?.(!on)}
      disabled={disabled}
      aria-pressed={on}
      aria-label={label}
      className={`relative inline-block h-[22px] w-[38px] shrink-0 rounded-full transition-colors ${
        on ? 'bg-accent' : 'bg-line-strong'
      } ${disabled ? 'cursor-not-allowed opacity-55' : ''}`}
    >
      <span
        className={`absolute top-[2px] h-[18px] w-[18px] rounded-full bg-white shadow-sm transition-all ${
          on ? 'left-[18px]' : 'left-[2px]'
        }`}
      />
    </button>
  )
}
