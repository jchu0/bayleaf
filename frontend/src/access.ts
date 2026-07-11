// ─────────────────────────────────────────────────────────────────────────────
// PAGE-ACCESS MODEL — a client-side VIEW-GATE, NOT a security control.
//
// This is the closed catalog of grantable pages, the named access profiles, per-user grants, and
// the pure resolution functions. It is the second frontend-only governance capability layered over
// the wire roles — exactly the shape of `isAdmin` (auth.ts): it gates what nav/pages a user SEES,
// it never authorizes a server write. The wire role (viewer|reviewer|approver) continues to govern
// every real write via api/auth.py's require_role, entirely unchanged. There is no backend authz
// store for page-access; the production seam is grants persisted + enforced server-side.
//
// Guarantees the model provides so a bad grant can never strand a user:
//   1. ACCESS_FLOOR (runs + cards) is re-asserted last in resolution — no deny can remove it.
//   2. `admin` is intentionally EXCLUDED from PageId — Admin stays governed solely by isAdmin
//      (login identity), so an admin can never be page-gated out of governance.
//   3. The provider layers an isAdmin bypass + a master `enforce` switch + Reset-to-defaults.
// ─────────────────────────────────────────────────────────────────────────────

// The closed catalog of grantable pages. `admin` is intentionally EXCLUDED (see header note 2).
export type PageId =
  | 'accession'
  | 'submit'
  | 'runs'
  | 'intake'
  | 'cards'
  | 'queue'
  | 'inbox'
  | 'provenance'
  | 'agent'
  | 'monitoring'
  | 'builder'
  | 'settings'

export type NavGroup = 'Operate' | 'Analyze' | 'Configure'
export type PageMeta = { id: PageId; label: string; group: NavGroup }

// Single source of truth — drives the Sidebar filter, the AccessEditor override table, and the
// effective-access preview. Order within Operate reflects the real lab flow (accession first).
export const PAGE_CATALOG: PageMeta[] = [
  { id: 'accession', label: 'Sample accessioning', group: 'Operate' },
  { id: 'submit', label: 'Submit samplesheet', group: 'Operate' },
  { id: 'runs', label: 'Runs', group: 'Operate' },
  { id: 'intake', label: 'Intake gate', group: 'Operate' },
  { id: 'cards', label: 'Decision cards', group: 'Operate' },
  { id: 'queue', label: 'Review queue', group: 'Operate' },
  { id: 'inbox', label: 'Inbox', group: 'Operate' },
  { id: 'provenance', label: 'Provenance', group: 'Analyze' },
  { id: 'agent', label: 'Agent triage', group: 'Analyze' },
  { id: 'monitoring', label: 'Monitoring', group: 'Analyze' },
  { id: 'builder', label: 'Pipeline builder', group: 'Configure' },
  { id: 'settings', label: 'Settings', group: 'Configure' },
]

export const NAV_GROUP_ORDER: NavGroup[] = ['Operate', 'Analyze', 'Configure']

export function pageLabel(page: PageId): string {
  return PAGE_CATALOG.find((p) => p.id === page)?.label ?? page
}

// A named bundle of pages — the maintainer's "role" in the CRM/workgroup sense (accessioning,
// wetlab, review, …). Distinct from the wire Role. Presets are READ-ONLY in MVP; per-user
// assignment is the editable governance surface.
export type AccessProfile = { id: string; label: string; description: string; pages: PageId[] }

export const ACCESS_PROFILES: AccessProfile[] = [
  {
    id: 'accessioning',
    label: 'Accessioning',
    description: 'Subject/sample accessioning (CRM).',
    pages: ['accession', 'runs', 'cards'],
  },
  {
    id: 'wetlab',
    label: 'Wet lab',
    description: 'Sequencing intake + preflight.',
    pages: ['submit', 'runs', 'intake', 'cards'],
  },
  {
    id: 'analysis',
    label: 'Analysis',
    description: 'Provenance, triage, monitoring.',
    pages: ['runs', 'cards', 'provenance', 'agent', 'monitoring'],
  },
  {
    id: 'review',
    label: 'Review',
    description: 'Review queue + inbox triage.',
    pages: ['runs', 'cards', 'queue', 'inbox', 'monitoring'],
  },
  {
    id: 'approval',
    label: 'Approval',
    description: 'Pipeline + policy authoring.',
    pages: ['runs', 'cards', 'queue', 'builder', 'settings'],
  },
  {
    id: 'governance',
    label: 'Governance',
    description: 'All pages (admin default).',
    pages: PAGE_CATALOG.map((p) => p.id),
  },
]

export function profileLabel(id: string): string {
  return ACCESS_PROFILES.find((p) => p.id === id)?.label ?? id
}

export type PageOverride = 'allow' | 'deny' // absent key = inherit from profiles
export type UserGrant = { profiles: string[]; overrides: Partial<Record<PageId, PageOverride>> }
export type AccessMap = Record<string /* userId */, UserGrant>

// A per-page FLOOR every non-admin keeps, so no assignment can strand the core viewing loop.
export const ACCESS_FLOOR: PageId[] = ['runs', 'cards']

// Seeded from DEMO_ACCOUNTS (auth.ts) so the demo works out of the box AND demonstrates gating
// differences. a.rivera deliberately holds THREE profiles → shows "one user, many roles, one
// platform." Admin (s.ops) gets governance but is also isAdmin-bypassed.
export const DEFAULT_ACCESS: AccessMap = {
  'l.santos': { profiles: ['analysis'], overrides: {} },
  'a.rivera': { profiles: ['accessioning', 'wetlab', 'review'], overrides: {} },
  'm.chen': { profiles: ['review', 'approval'], overrides: {} },
  's.ops': { profiles: ['governance'], overrides: {} },
}

// Resolve a grant → the set of pages it can see. Profiles union in; overrides allow/deny on top;
// the floor is re-asserted LAST so a deny can never remove runs/cards (see header note 1).
export function effectivePages(grant: UserGrant | undefined): Set<PageId> {
  const s = new Set<PageId>(ACCESS_FLOOR)
  for (const pid of grant?.profiles ?? []) {
    const profile = ACCESS_PROFILES.find((p) => p.id === pid)
    for (const pg of profile?.pages ?? []) s.add(pg)
  }
  for (const [pg, ov] of Object.entries(grant?.overrides ?? {})) {
    if (ov === 'deny') s.delete(pg as PageId)
    else if (ov === 'allow') s.add(pg as PageId)
  }
  // Re-assert the floor last so a deny override can never strand the core viewing loop.
  for (const f of ACCESS_FLOOR) s.add(f)
  return s
}

export function canSeePage(map: AccessMap, userId: string, page: PageId): boolean {
  return effectivePages(map[userId]).has(page)
}

// Value equality for a grant (order-insensitive on profiles) — powers the editor's dirty check.
export function sameGrant(a: UserGrant | undefined, b: UserGrant | undefined): boolean {
  const norm = (g: UserGrant | undefined) => ({
    profiles: [...(g?.profiles ?? [])].sort(),
    overrides: Object.fromEntries(Object.entries(g?.overrides ?? {}).sort(([x], [y]) => x.localeCompare(y))),
  })
  return JSON.stringify(norm(a)) === JSON.stringify(norm(b))
}

// Client-side audit entry for an access change (the store has no backend; a labelled seam).
export type AccessAuditEntry = { at: string; actor: string; targetUser: string; summary: string }
