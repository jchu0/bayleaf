import { ChevronLeft, Info, Layers, Lock, RotateCcw, ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import {
  ACCESS_FLOOR,
  ACCESS_PROFILES,
  NAV_GROUP_ORDER,
  type PageId,
  type PageOverride,
  PAGE_CATALOG,
  type UserGrant,
  effectivePages,
  pageLabel,
  profileLabel,
  sameGrant,
} from '../access'
import { DEMO_ACCOUNTS } from '../auth'
import { useAccess } from '../context/AccessContext'
import { CollapsibleRow } from './CollapsibleRow'
import { useConfirm } from './ConfirmDialog'
import { Pager, type PerPage } from './Pager'
import { SegmentedControl } from './SegmentedControl'
import { useToast } from './Toast'

// Admin → Page access. Assigns the frontend-only page-access capability per user: a bundle of
// read-only profiles + optional per-page allow/deny overrides. Every change stages into a draft,
// is confirmed, and lands in the client-side audit trail surfaced in the Activity log. This gates
// VIEWS only — the API still authorizes writes by wire role (the banner says so, honestly).
//
// Kept out of Admin.tsx (already large) as its own component per the design.

const ROSTER = DEMO_ACCOUNTS.map((a) => ({ id: a.id, name: a.name, role: a.role, admin: a.admin }))
const FLOOR = new Set<PageId>(ACCESS_FLOOR)

const OVERRIDE_OPTS: { value: 'inherit' | PageOverride; label: string }[] = [
  { value: 'inherit', label: 'Inherit' },
  { value: 'allow', label: 'Allow' },
  { value: 'deny', label: 'Deny' },
]

function emptyGrant(): UserGrant {
  return { profiles: [], overrides: {} }
}
function ovOf(g: UserGrant, pid: PageId): 'inherit' | PageOverride {
  return g.overrides[pid] ?? 'inherit'
}
function profileSummary(g: UserGrant): string {
  if (!g.profiles.length) return 'No profiles'
  const [first, ...rest] = g.profiles.map(profileLabel)
  return rest.length ? `${first} +${rest.length}` : first
}
function summarize(g: UserGrant): string {
  const profs = g.profiles.length ? g.profiles.map(profileLabel).join(', ') : 'none'
  const ovs = Object.entries(g.overrides).map(([p, o]) => `${pageLabel(p as PageId)}→${o}`)
  return `Profiles: ${profs}${ovs.length ? ` · overrides: ${ovs.join(', ')}` : ''}`
}

// The prominent, honest "this gates views, not API enforcement" banner shown wherever access is
// configured — the labelled seam mandated by the guardrails.
function ViewGateBanner() {
  return (
    <div className="mb-3 flex items-start gap-2 rounded-lg border border-hold-bd bg-hold-bg px-3 py-2 text-[12px] leading-relaxed text-hold-fg">
      <ShieldAlert size={15} className="mt-px shrink-0" />
      <span>
        <strong>Page access gates VIEWS, not API enforcement.</strong> This is a client-side
        governance layer (like admin capability) — it decides which pages a user sees in the nav. It
        does <strong>not</strong> authorize server writes: the API still checks every write against
        the user&apos;s wire role (viewer/reviewer/approver). A production build enforces page/read
        access server-side (a labelled seam).
      </span>
    </div>
  )
}

export function AccessEditor() {
  const { map, effectiveFor, setUserGrant, resetDefaults, enforce, setEnforce } = useAccess()
  const confirm = useConfirm()
  const { toast } = useToast()

  const [selected, setSelected] = useState<string | null>(null)
  const [draft, setDraft] = useState<UserGrant | null>(null)
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState<PerPage>('25')
  // Declared before the list-view early return so hook order is stable (rules-of-hooks): the
  // overrides section only renders in the editor view, but its state must live at the top.
  const [overridesOpen, setOverridesOpen] = useState(false)

  const savedGrant = (id: string): UserGrant => map[id] ?? emptyGrant()

  function open(id: string) {
    const g = savedGrant(id)
    setDraft({ profiles: [...g.profiles], overrides: { ...g.overrides } })
    setSelected(id)
  }
  function close() {
    setSelected(null)
    setDraft(null)
  }

  // ── list view ───────────────────────────────────────────────────────────────
  if (!selected || !draft) {
    const per = Number(perPage)
    const total = ROSTER.length
    const pages = Math.max(1, Math.ceil(total / per))
    const cur = Math.min(page, pages)
    const shown = ROSTER.slice((cur - 1) * per, (cur - 1) * per + per)

    const onReset = async () => {
      const ok = await confirm({
        title: 'Reset all page access to defaults?',
        body: 'Restores every user’s seeded profiles and clears all overrides. Recorded in the audit log.',
        confirmLabel: 'Reset to defaults',
        tone: 'danger',
      })
      if (!ok) return
      resetDefaults()
      close()
      toast('Page access reset to defaults.', 'success')
    }
    const onEnforce = async (on: boolean) => {
      if (on === enforce) return
      const ok = await confirm({
        title: on ? 'Enable page-access enforcement?' : 'Disable page-access enforcement?',
        body: on
          ? 'Nav is filtered by each user’s access profile again.'
          : 'Every page becomes visible to every user (the gate is off). The API still authorizes writes by role.',
        confirmLabel: on ? 'Enable' : 'Disable',
        tone: on ? 'default' : 'danger',
      })
      if (ok) setEnforce(on)
    }

    return (
      <div>
        <ViewGateBanner />
        <div className="mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-line bg-card px-3.5 py-2.5">
          <span className="flex items-center gap-1.5 text-[12.5px] font-medium text-text">
            <Lock size={14} className="text-text-3" /> Enforcement
          </span>
          <SegmentedControl<'on' | 'off'>
            options={[
              { value: 'on', label: 'On' },
              { value: 'off', label: 'Off' },
            ]}
            value={enforce ? 'on' : 'off'}
            onChange={(v) => void onEnforce(v === 'on')}
          />
          <span className="text-[11.5px] text-text-3">
            {enforce ? 'Nav filtered by profile · admins bypass' : 'Gate off — all pages visible'}
          </span>
          <button
            type="button"
            onClick={() => void onReset()}
            className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12px] font-medium text-text-2 hover:border-line"
          >
            <RotateCcw size={13} /> Reset to defaults
          </button>
        </div>

        <div className="overflow-hidden rounded-xl border border-line bg-card shadow-card">
          <div className="grid grid-cols-[1fr_110px_1fr_90px_110px] gap-3 border-b border-line px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.4px] text-text-3">
            <span>User</span>
            <span>Wire role</span>
            <span>Profiles</span>
            <span className="text-right">Pages</span>
            <span />
          </div>
          {shown.map((u) => {
            const g = savedGrant(u.id)
            const count = effectiveFor(u.id).size
            return (
              <div key={u.id} className="grid grid-cols-[1fr_110px_1fr_90px_110px] items-center gap-3 border-b border-line px-4 py-3 last:border-0">
                <div className="min-w-0">
                  <div className="truncate text-[13.5px] font-semibold text-text">{u.name}</div>
                  <div className="font-mono text-[11px] text-text-2">{u.id}</div>
                </div>
                <span className="text-[12.5px] capitalize text-text-2">{u.role}</span>
                <span className="min-w-0 truncate text-[12.5px] text-text-2" title={g.profiles.map(profileLabel).join(', ')}>
                  {u.admin ? 'All (admin)' : profileSummary(g)}
                </span>
                <span className="text-right font-mono text-[12.5px] text-text-2">
                  {u.admin ? 'all' : count}
                </span>
                <div className="text-right">
                  {u.admin ? (
                    <span className="text-[11px] text-text-3" title="Admins hold governance via login identity — never page-gated">
                      Governance
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => open(u.id)}
                      className="rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12px] font-medium text-accent-strong hover:border-line"
                    >
                      Edit access
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-text-3">
          Admins hold governance (all pages) via login identity — they are never page-gated, so they
          have no editable grant here. Everyone keeps a floor of{' '}
          <span className="font-medium text-text-2">Runs</span> and{' '}
          <span className="font-medium text-text-2">Decision cards</span> no deny can remove.
        </p>
        <Pager total={total} page={cur} perPage={perPage} onPage={setPage} onPerPage={setPerPage} noun="users" />
      </div>
    )
  }

  // ── editor view ──────────────────────────────────────────────────────────────
  const user = ROSTER.find((r) => r.id === selected)
  const saved = savedGrant(selected)
  const dirty = !sameGrant(draft, saved)
  const effective = effectivePages(draft)

  const toggleProfile = (pid: string) =>
    setDraft((d) => {
      if (!d) return d
      const has = d.profiles.includes(pid)
      return { ...d, profiles: has ? d.profiles.filter((p) => p !== pid) : [...d.profiles, pid] }
    })
  const setOverride = (pid: PageId, val: 'inherit' | PageOverride) =>
    setDraft((d) => {
      if (!d) return d
      const overrides = { ...d.overrides }
      if (val === 'inherit') delete overrides[pid]
      else overrides[pid] = val
      return { ...d, overrides }
    })

  const profChanged = (pid: string) => draft.profiles.includes(pid) !== saved.profiles.includes(pid)
  const ovChanged = (pid: PageId) => ovOf(draft, pid) !== ovOf(saved, pid)

  const save = async () => {
    const ok = await confirm({
      title: `Change page access for ${user?.name ?? selected}?`,
      body: 'Updates which pages they see in the nav — recorded in the audit log. A view-gate, not API enforcement.',
      confirmLabel: 'Save access',
    })
    if (!ok) return
    setUserGrant(selected, draft, { summary: summarize(draft) })
    toast(`Page access updated for ${user?.name ?? selected}.`, 'success')
  }

  return (
    <div>
      <ViewGateBanner />
      <button
        type="button"
        onClick={close}
        className="mb-3 inline-flex items-center gap-1 text-[12.5px] font-medium text-text-2 hover:text-text"
      >
        <ChevronLeft size={15} /> All users
      </button>

      <div className="mb-4 rounded-xl border border-line bg-card p-4 shadow-card">
        <div className="text-[15px] font-semibold text-text">{user?.name ?? selected}</div>
        <div className="mt-0.5 flex items-center gap-2 text-[12px] text-text-2">
          <span className="font-mono">{selected}</span>
          <span className="text-text-3">·</span>
          <span className="capitalize">wire role: {user?.role}</span>
          <span className="text-text-3">(read-only — role editing lives in Users &amp; roles)</span>
        </div>
      </div>

      {/* Profiles — a bounded checkbox list over the fixed vocabulary (no pill multi-select). */}
      <div className="mb-4">
        <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.4px] text-text-3">
          <Layers size={13} /> Access profiles
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          {ACCESS_PROFILES.map((p) => {
            const on = draft.profiles.includes(p.id)
            return (
              <label
                key={p.id}
                className={`flex cursor-pointer items-start gap-2.5 rounded-lg border px-3 py-2.5 transition-colors ${
                  on ? 'border-accent bg-accent-weak' : 'border-line bg-card hover:border-line-strong'
                }`}
              >
                <input type="checkbox" checked={on} onChange={() => toggleProfile(p.id)} className="mt-0.5 h-3.5 w-3.5 accent-accent" />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 text-[13px] font-semibold text-text">
                    {p.label}
                    {profChanged(p.id) && (
                      <span className="text-[10px] font-semibold uppercase tracking-[0.3px] text-hold-fg">unsaved</span>
                    )}
                  </span>
                  <span className="mt-0.5 block text-[11.5px] leading-snug text-text-2">{p.description}</span>
                </span>
              </label>
            )
          })}
        </div>
      </div>

      {/* Per-page overrides — tri-state Inherit/Allow/Deny <select>s (no pills). Floor pages lock. */}
      <div className="mb-4">
        <CollapsibleRow
          open={overridesOpen}
          onToggle={() => setOverridesOpen((o) => !o)}
          header={
            <div className="flex items-center gap-2">
              <span className="text-[13px] font-semibold text-text">Per-page overrides</span>
              <span className="rounded-full bg-card-2 px-1.5 py-px font-mono text-[10.5px] text-text-3">
                {Object.keys(draft.overrides).length}
              </span>
              <span className="text-[11.5px] text-text-3">refine on top of profiles</span>
            </div>
          }
        >
          <div className="flex flex-col gap-1.5">
            {PAGE_CATALOG.map((pm) => {
              const isFloor = FLOOR.has(pm.id)
              const cur = ovOf(draft, pm.id)
              const fromProfile = draft.profiles.some((pid) => ACCESS_PROFILES.find((p) => p.id === pid)?.pages.includes(pm.id))
              return (
                <div key={pm.id} className="grid grid-cols-[1fr_auto] items-center gap-3 border-b border-line py-1.5 last:border-0">
                  <div className="min-w-0">
                    <span className="text-[12.5px] text-text">{pm.label}</span>
                    <span className="ml-2 text-[10.5px] text-text-3">{pm.group}</span>
                    {fromProfile && !isFloor && <span className="ml-2 text-[10.5px] text-accent-strong">in a profile</span>}
                  </div>
                  {isFloor ? (
                    <span className="inline-flex items-center gap-1 text-[11px] text-text-3">
                      <Lock size={11} /> Always on (floor)
                    </span>
                  ) : (
                    <select
                      value={cur}
                      onChange={(e) => setOverride(pm.id, e.target.value as 'inherit' | PageOverride)}
                      className={`rounded-lg border bg-card px-2.5 py-1 text-[12.5px] text-text outline-none focus:border-accent ${
                        ovChanged(pm.id) ? 'border-hold-bd' : 'border-line'
                      }`}
                    >
                      {OVERRIDE_OPTS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              )
            })}
          </div>
        </CollapsibleRow>
      </div>

      {/* Live effective-access preview — the exact nav this user would see (the honest way to inspect
          another user's view without impersonating). */}
      <div className="rounded-xl border border-line bg-card-2 p-4">
        <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.4px] text-text-3">
          <Info size={13} /> Effective access · {effective.size} pages
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {NAV_GROUP_ORDER.map((grp) => {
            const inGroup = PAGE_CATALOG.filter((p) => p.group === grp && effective.has(p.id))
            return (
              <div key={grp}>
                <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-[0.4px] text-text-3">{grp}</div>
                {inGroup.length ? (
                  <ul className="flex flex-col gap-0.5">
                    {inGroup.map((p) => (
                      <li key={p.id} className="flex items-center gap-1.5 text-[12px] text-text-2">
                        <span className="h-1 w-1 rounded-full bg-accent" />
                        {p.label}
                        {FLOOR.has(p.id) && <span className="text-[10px] text-text-3">floor</span>}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="text-[11.5px] text-text-3">— none</div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {dirty && (
        <div className="mt-3 flex items-center justify-end gap-2">
          <span className="mr-auto text-[12px] text-text-2">Unsaved access changes.</span>
          <button
            type="button"
            onClick={() => open(selected)}
            className="rounded-lg border border-line bg-card px-3.5 py-1.5 text-[12.5px] font-medium text-text-2 hover:border-line-strong"
          >
            Discard
          </button>
          <button
            type="button"
            onClick={() => void save()}
            className="rounded-lg bg-accent px-3.5 py-1.5 text-[12.5px] font-semibold text-white hover:bg-accent-strong"
          >
            Save access
          </button>
        </div>
      )}
    </div>
  )
}
