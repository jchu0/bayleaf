import { X } from 'lucide-react'
import { useState } from 'react'
import { type Density, type Palette, usePrefs } from '../context/PrefsContext'
import { useRole } from '../context/RoleContext'
import { SegmentedControl } from './SegmentedControl'

// The profile/preferences modal opened from the user-panel popover (dc.html 95-128) — DISTINCT
// from the /settings thresholds screen. Theme + density now persist + take effect (PrefsContext);
// the digest/notification toggles remain demo-local (a production prefs-store seam).
type Theme = 'light' | 'dark' | 'system'

function ToggleSwitch({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className={`relative h-[22px] w-[38px] shrink-0 rounded-full transition-colors ${
        on ? 'bg-accent' : 'bg-card-3'
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

function PrefRow({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5">
      <div className="min-w-0">
        <div className="text-[13.5px] font-medium text-text">{label}</div>
        {hint && <div className="text-[12px] text-text-2">{hint}</div>}
      </div>
      {children}
    </div>
  )
}

export function UserSettingsDialog({ onClose }: { onClose: () => void }) {
  const { role } = useRole()
  const { theme, setTheme, density, setDensity, palette, setPalette } = usePrefs()
  const [emailDigest, setEmailDigest] = useState(true)
  // Matches the prototype seed prefInApp: true (dc.html) — opens ON.
  const [desktopNotifications, setDesktopNotifications] = useState(true)

  // UIC-7 — a palette family shows its light name in light mode, its dark complement's name in
  // dark mode. Resolve "system" the same way PrefsContext does so the labels match what's on screen.
  const resolvedTheme =
    theme === 'system'
      ? window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark'
        : 'light'
      : theme
  const paletteOptions: { value: Palette; label: string }[] =
    resolvedTheme === 'dark'
      ? [
          { value: 'clinical', label: 'Midnight' },
          { value: 'sand', label: 'Carbon' },
          { value: 'slate', label: 'Indigo' },
        ]
      : [
          { value: 'clinical', label: 'Clinical' },
          { value: 'sand', label: 'Sand' },
          { value: 'slate', label: 'Slate' },
        ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-[520px] max-w-full overflow-hidden rounded-2xl border border-line bg-card shadow-pop">
        <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
          <h2 className="font-serif text-[19px] font-medium text-text">Settings</h2>
          <button
            onClick={onClose}
            className="grid h-8 w-8 place-items-center rounded-lg text-text-2 hover:bg-page"
            aria-label="Close"
          >
            <X size={17} />
          </button>
        </div>

        <div className="max-h-[70vh] overflow-y-auto px-5 py-4">
          <section>
            <p className="mb-3 text-[11px] font-bold uppercase tracking-[0.8px] text-text-3">Profile</p>
            {/* Avatar row leads Profile (dc.html): same 150deg green gradient as the sidebar user chip. */}
            <div className="mb-4 flex items-center gap-3.5">
              <div
                className="grid h-[46px] w-[46px] shrink-0 place-items-center rounded-full text-[16px] font-semibold text-white"
                style={{ background: 'linear-gradient(150deg,#3a7,#186)' }}
              >
                AR
              </div>
              <button
                type="button"
                className="rounded-lg border border-line-strong bg-card px-3 py-[7px] text-[12px] font-medium text-accent-strong hover:bg-page"
              >
                Change avatar
              </button>
            </div>
            {/* Two-column field grid with labels above each control (dc.html). */}
            <div className="grid grid-cols-2 gap-[13px]">
              <div>
                <label className="mb-1.5 block text-[11px] font-semibold text-text-2">Display name</label>
                <input
                  defaultValue="Ada Rivera"
                  className="w-full rounded-lg border border-line-strong bg-card px-[11px] py-2 text-[13px] text-text focus:border-accent focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-[11px] font-semibold text-text-2">Email</label>
                <input
                  defaultValue="a.rivera@lab.org"
                  className="w-full rounded-lg border border-line-strong bg-card px-[11px] py-2 font-mono text-[12.5px] text-text focus:border-accent focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-[11px] font-semibold text-text-2">Role</label>
                <div className="rounded-lg border border-line bg-card-2 px-[11px] py-2 text-[12.5px] capitalize text-text-2">
                  {role} · RBAC
                </div>
              </div>
              <div>
                <label className="mb-1.5 block text-[11px] font-semibold text-text-2">Time zone</label>
                <select
                  defaultValue="America/Denver"
                  className="w-full cursor-pointer rounded-lg border border-line-strong bg-card px-[11px] py-2 text-[12.5px] text-text focus:border-accent focus:outline-none"
                >
                  <option value="America/Denver">America/Denver (MST)</option>
                  <option value="America/New_York">America/New_York (ET)</option>
                  <option value="UTC">UTC</option>
                </select>
              </div>
            </div>
          </section>

          <section className="mt-4">
            <p className="mb-1 text-[11px] font-bold uppercase tracking-[0.8px] text-text-3">
              Preferences
            </p>
            <div className="divide-y divide-line">
              <PrefRow label="Theme">
                <SegmentedControl<Theme>
                  value={theme}
                  onChange={setTheme}
                  options={[
                    { value: 'light', label: 'Light' },
                    { value: 'dark', label: 'Dark' },
                    { value: 'system', label: 'System' },
                  ]}
                />
              </PrefRow>
              <PrefRow label="Palette" hint="Color theme for the current mode">
                <SegmentedControl<Palette> value={palette} onChange={setPalette} options={paletteOptions} />
              </PrefRow>
              <PrefRow label="Card density" hint="Default decision-card layout">
                <SegmentedControl<Density>
                  value={density}
                  onChange={setDensity}
                  options={[
                    { value: 'split', label: 'Split' },
                    { value: 'brief', label: 'Brief' },
                    { value: 'dense', label: 'Dense' },
                  ]}
                />
              </PrefRow>
              <PrefRow label="Email digest" hint="Daily summary of runs needing review">
                <ToggleSwitch on={emailDigest} onChange={setEmailDigest} />
              </PrefRow>
              <PrefRow label="Desktop notifications" hint="Alert on escalations assigned to me">
                <ToggleSwitch on={desktopNotifications} onChange={setDesktopNotifications} />
              </PrefRow>
            </div>
          </section>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-line px-5 py-3">
          <button
            onClick={onClose}
            className="rounded-lg border border-line bg-card px-3.5 py-1.5 text-[13px] font-medium text-text-2 hover:bg-page"
          >
            Cancel
          </button>
          <button
            onClick={onClose}
            className="rounded-lg bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white hover:bg-accent-strong"
          >
            Save changes
          </button>
        </div>
      </div>
    </div>
  )
}
