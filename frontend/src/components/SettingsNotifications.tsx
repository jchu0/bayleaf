import { type ReactNode, useState } from 'react'
import { Info, Pencil } from 'lucide-react'
import { SettingsToggle } from './SettingsToggle'
import { useToast } from './Toast'

// Notifications (dc.html 1225-1244): three channel rows — Slack + Microsoft Teams + Discord.
// Honesty: this is a PRESENTATIONAL demo seam. The channel status is NOT a live health check, the
// Edit→Save toggles persist nothing to a backend, and Connect is not wired — the real Slack send is
// env-armed on the core, off the gate. Every affordance is labelled as such so nothing reads as a
// verified/live connection it isn't. (Persisting these settings + a real reachability check are a
// documented, not-built seam.)

// Design icons are inlined verbatim (currentColor lets the token class drive the stroke) rather
// than reached for from lucide so the glyphs match the prototype exactly.
function SlackGlyph() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <line x1="10" y1="3" x2="8" y2="21" />
      <line x1="16" y1="3" x2="14" y2="21" />
      <line x1="3" y1="9" x2="21" y2="9" />
      <line x1="2" y1="15" x2="20" y2="15" />
    </svg>
  )
}
function TeamsGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="6" width="13" height="12" rx="2" />
      <path d="M16 9l5-2v10l-5-2" />
    </svg>
  )
}
function DiscordGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="9" cy="12" r="1" />
      <circle cx="15" cy="12" r="1" />
      <path d="M7.5 7.5c3-1 6-1 9 0M7.5 16.5c3 1 6 1 9 0M7 8l-2 8a12 12 0 0 0 5 2M17 8l2 8a12 12 0 0 1-5 2" />
    </svg>
  )
}

// Honest channel status: the connection is NOT health-checked here, so it must not render as a green
// "Connected" (which reads as a verified/live link). Show a muted, neutral "Configured · not
// verified" with the reason in the tooltip — absent/unverified never reads as passed.
function ConfiguredDot() {
  return (
    <span
      className="mt-[2px] flex items-center gap-[5px] text-[11.5px] text-text-3"
      title="Configured in this demo — the connection is not health-checked, so this is not a live status."
    >
      <span className="inline-block h-[6px] w-[6px] rounded-full border border-line-strong bg-transparent" />
      Configured · not verified
    </span>
  )
}

function ChannelRow({
  icon,
  iconWhiteBox,
  iconTone,
  name,
  status,
  control,
  tinted,
}: {
  icon: ReactNode
  iconWhiteBox?: boolean
  iconTone: string
  name: ReactNode
  status: ReactNode
  control: ReactNode
  tinted?: boolean
}) {
  return (
    <div
      className={`flex items-center gap-3 rounded-[10px] border border-line px-[14px] py-[12px] ${
        tinted ? 'bg-card-2' : ''
      }`}
    >
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-line ${
          iconWhiteBox ? 'bg-white' : 'bg-card-2'
        } ${iconTone}`}
      >
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-semibold text-text">{name}</div>
        {status}
      </div>
      {control}
    </div>
  )
}

export function SettingsNotifications() {
  const { toast } = useToast()
  // Committed channel state. UIC-4: these toggles read at a glance but are only mutable behind an
  // explicit Edit → Save, so a stray click can't silently mute the gate's alerts. `draft*` holds the
  // uncommitted edit; Save commits, Cancel discards (nothing changes until Save).
  const [slackOn, setSlackOn] = useState(true)
  const [teamsOn, setTeamsOn] = useState(true)
  const [editing, setEditing] = useState(false)
  const [draftSlack, setDraftSlack] = useState(true)
  const [draftTeams, setDraftTeams] = useState(true)

  const beginEdit = () => {
    setDraftSlack(slackOn)
    setDraftTeams(teamsOn)
    setEditing(true)
  }
  const cancelEdit = () => setEditing(false)
  const saveEdit = () => {
    setSlackOn(draftSlack)
    setTeamsOn(draftTeams)
    setEditing(false)
    // Honesty: nothing persists on this seam — the edit updates local component state only and is
    // lost on reload. Say so rather than claiming a durable "saved" the backend never recorded.
    toast('Applied locally — demo seam, not persisted to a backend', 'info')
  }

  // Discord has no channel wiring — the button must not look like it does something. Surface the
  // honest "not wired" outcome via a toast (the same way every off-gate affordance reports).
  const connectDiscord = () => {
    toast('Discord connect is not wired in this demo', 'info')
  }

  // In edit mode the toggles bind to the draft; in view mode they show the committed value and are
  // locked (disabled) so the switch is legible but not directly flippable.
  const slackView = editing ? draftSlack : slackOn
  const teamsView = editing ? draftTeams : teamsOn

  return (
    <section className="rounded-[13px] border border-line bg-card px-[18px] py-[17px]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[14.5px] font-semibold text-text">Notifications</div>
          <p className="mt-[3px] text-[12.5px] text-text-2">
            Ping the channel when a run reaches the gate with samples needing attention.
          </p>
        </div>
        {editing ? (
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              onClick={saveEdit}
              className="rounded-lg bg-accent px-3 py-1.5 text-[12.5px] font-semibold text-white transition-colors hover:bg-accent-strong"
            >
              Save
            </button>
            <button
              type="button"
              onClick={cancelEdit}
              className="rounded-lg border border-line bg-card px-3 py-1.5 text-[12.5px] font-medium text-text-2 transition-colors hover:border-line-strong"
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={beginEdit}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12.5px] font-medium text-text-2 transition-colors hover:border-accent hover:text-accent-strong"
          >
            <Pencil size={13} />
            Edit
          </button>
        )}
      </div>
      {/* Honesty seam banner — this panel is a presentational demo: no channel is health-checked,
          Save persists nothing, and Connect isn't wired. Say it plainly so nothing reads as live. */}
      <div className="mt-[13px] flex items-start gap-2 rounded-[10px] border border-dashed border-line-strong bg-card-2 px-[13px] py-[9px]">
        <Info size={14} className="mt-[1px] shrink-0 text-text-3" />
        <p className="text-[11.5px] leading-snug text-text-3">
          Demo seam — channel status is not health-checked, Save applies locally only (not persisted),
          and Connect is not wired. Live delivery is env-armed on the core, off the gate.
        </p>
      </div>
      <div className="mt-[13px] space-y-[9px]">
        <ChannelRow
          tinted
          iconWhiteBox
          iconTone="text-text-2"
          icon={<SlackGlyph />}
          name={
            <>
              Slack · <span className="font-mono">#pipeguard-ops</span>
            </>
          }
          status={<ConfiguredDot />}
          control={
            <SettingsToggle
              on={slackView}
              onChange={setDraftSlack}
              disabled={!editing}
              label="Slack notifications"
            />
          }
        />
        <ChannelRow
          iconTone="text-text-2"
          icon={<TeamsGlyph />}
          name={
            <>
              Microsoft Teams · <span className="font-mono">Lab Ops</span>
            </>
          }
          status={<ConfiguredDot />}
          control={
            <SettingsToggle
              on={teamsView}
              onChange={setDraftTeams}
              disabled={!editing}
              label="Microsoft Teams notifications"
            />
          }
        />
        <ChannelRow
          iconTone="text-text-3"
          icon={<DiscordGlyph />}
          name="Discord"
          status={<div className="mt-[2px] text-[11.5px] text-text-3">Not connected</div>}
          control={
            <button
              type="button"
              onClick={connectDiscord}
              className="shrink-0 rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12px] font-medium text-accent"
            >
              Connect
            </button>
          }
        />
      </div>
    </section>
  )
}
