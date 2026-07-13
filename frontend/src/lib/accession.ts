import { colIndex, csvCell, splitCsv } from './csv'

// Sample accessioning (CRM) — the data model + tolerant parse/serialize + the Accession→Submit
// handoff. This is the subject-registration step UPSTREAM of the wetlab samplesheet and the
// preflight gate; it composes subject/sample metadata and NEVER runs a tool (compose ≠ execute).
//
// PII / honest seam: subject identifiers and everything in an AccessionRecord stay CLIENT-SIDE.
// Nothing here is transmitted or persisted server-side — POST /api/runs (`SubmitRunIn`) carries no
// subject field and is `extra="forbid"`, so it would reject one. Real subject/PII persistence is
// gated behind the data-platform PII/de-identification design (a labelled seam). DOB / MRN are
// deliberately NOT modeled (PHI); only lab-operational fields (collection date, accession #, site)
// are kept, and even those never leave the browser.

export type Sex = 'female' | 'male' | 'other' | 'unknown' | ''
export type Consent = 'research' | 'clinical' | 'withdrawn' | ''

export type AccessionRecord = {
  subjectId: string
  sampleId: string
  tissue: string // controlled vocab <select>
  sex?: Sex // controlled vocab
  consent?: Consent // controlled vocab
  collectedOn?: string // ISO date (NOT DOB — DOB is PHI, deliberately omitted)
  accessionId?: string // lab accession number
  site?: string // collection site / study
  notes?: string
}

// Controlled vocabularies for the CRM table's <select>s (scale-aware: dropdowns, never free-typed
// or cycle-on-click chips). Tissue mirrors Submit's sample-type vocabulary so a merged value lands
// on a recognized option.
export const TISSUES = ['Whole blood', 'Saliva', 'FFPE', 'Buccal swab', 'Plasma', 'Tissue']
export const SEXES: { value: Sex; label: string }[] = [
  { value: '', label: '—' },
  { value: 'female', label: 'Female' },
  { value: 'male', label: 'Male' },
  { value: 'other', label: 'Other' },
  { value: 'unknown', label: 'Unknown' },
]
export const CONSENTS: { value: Consent; label: string }[] = [
  { value: '', label: '—' },
  { value: 'research', label: 'Research' },
  { value: 'clinical', label: 'Clinical' },
  { value: 'withdrawn', label: 'Withdrawn' },
]

function asSex(v: string): Sex {
  const lc = v.toLowerCase()
  return (['female', 'male', 'other', 'unknown'] as const).find((s) => s === lc) ?? ''
}
function asConsent(v: string): Consent {
  const lc = v.toLowerCase()
  return (['research', 'clinical', 'withdrawn'] as const).find((c) => c === lc) ?? ''
}

// Parse a sample_metadata.csv (Subject_ID / Sample_ID / Tissue + optional CRM columns) into
// AccessionRecords. Tolerant: a missing/renamed column degrades to an empty cell (never a crash),
// matching Submit's parseMetadata boundary discipline. Reuses the shared csv.ts helpers.
export function parseAccessionCsv(text: string): AccessionRecord[] {
  const lines = text.split(/\r?\n/).filter((l) => l.trim())
  if (!lines.length) return []
  const header = splitCsv(lines[0])
  const cSample = colIndex(header, ['sample_id', 'sample', 'sampleid'])
  const cSubject = colIndex(header, ['subject_id', 'subject', 'patient_id', 'individual'])
  const cTissue = colIndex(header, ['tissue', 'sample_type', 'source'])
  const cSex = colIndex(header, ['sex', 'gender'])
  const cConsent = colIndex(header, ['consent', 'consent_type'])
  const cCollected = colIndex(header, ['collected_on', 'collection_date', 'collected', 'draw_date'])
  const cAccession = colIndex(header, ['accession_id', 'accession', 'accession_no', 'accession_number'])
  const cSite = colIndex(header, ['site', 'collection_site', 'study'])
  const cNotes = colIndex(header, ['notes', 'note', 'comment'])
  const at = (parts: string[], i: number) => (i >= 0 ? (parts[i] ?? '').trim() : '')
  const out: AccessionRecord[] = []
  for (let i = 1; i < lines.length; i++) {
    const parts = splitCsv(lines[i])
    const sampleId = (cSample >= 0 ? parts[cSample] : parts[0]) ?? ''
    const subjectId = at(parts, cSubject)
    // A row with neither a sample nor a subject id is noise — skip it, don't fabricate.
    if (!sampleId && !subjectId) continue
    out.push({
      subjectId,
      sampleId,
      tissue: at(parts, cTissue),
      sex: asSex(at(parts, cSex)),
      consent: asConsent(at(parts, cConsent)),
      collectedOn: at(parts, cCollected),
      accessionId: at(parts, cAccession),
      site: at(parts, cSite),
      notes: at(parts, cNotes),
    })
  }
  return out
}

// Serialize AccessionRecords → a CSV whose header round-trips through parseAccessionCsv. Column
// order leads with the identity triple (Sample_ID, Subject_ID, Tissue) Submit's parseMetadata reads.
const CSV_HEADER = ['Sample_ID', 'Subject_ID', 'Tissue', 'Sex', 'Consent', 'Collected_On', 'Accession_ID', 'Site', 'Notes']
export function toAccessionCsv(records: AccessionRecord[]): string {
  const rows = records.map((r) =>
    [r.sampleId, r.subjectId, r.tissue, r.sex ?? '', r.consent ?? '', r.collectedOn ?? '', r.accessionId ?? '', r.site ?? '', r.notes ?? '']
      .map((c) => csvCell(c))
      .join(','),
  )
  return [CSV_HEADER.join(','), ...rows].join('\n')
}

// ── Accession → Submit handoff (client-side only, labelled seam) ─────────────────────────────
// A localStorage courier keyed by sample id carrying ONLY {subject_id, tissue} — the exact shape
// Submit's client-side SampleMeta merge already consumes. No network call: accessioning transmits
// nothing. Submit reads this on mount and clears it (a one-shot handoff, not a persistent store).
const HANDOFF_KEY = 'bayleaf.accession.handoff'
export type HandoffMap = Record<string /* sampleId */, { subject_id?: string; tissue?: string }>

export function stashHandoff(records: AccessionRecord[]): void {
  try {
    const map: HandoffMap = {}
    for (const r of records) {
      if (!r.sampleId) continue
      map[r.sampleId] = { subject_id: r.subjectId || undefined, tissue: r.tissue || undefined }
    }
    localStorage.setItem(HANDOFF_KEY, JSON.stringify(map))
  } catch {
    // localStorage unavailable (private mode) — the handoff just won't survive the navigation.
  }
}

export function readHandoff(): HandoffMap | null {
  try {
    const raw = localStorage.getItem(HANDOFF_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as HandoffMap
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}

export function clearHandoff(): void {
  try {
    localStorage.removeItem(HANDOFF_KEY)
  } catch {
    // ignore — nothing to clear if storage is unavailable.
  }
}

// ── Accession draft persistence (client-side only) ───────────────────────────────────────────
// Save draft keeps an in-progress accessioning batch across a refresh (like PrefsContext / the demo
// session) — still purely client-side, never a server round-trip.
const DRAFT_KEY = 'bayleaf.accession.draft'

export function saveAccessionDraft(records: AccessionRecord[]): void {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify(records))
  } catch {
    // ignore — the draft just won't survive a refresh.
  }
}

export function loadAccessionDraft(): AccessionRecord[] | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as AccessionRecord[]
    return Array.isArray(parsed) ? parsed : null
  } catch {
    return null
  }
}

// ── Sample-identity join (Submit intake gate, UIC-11) ─────────────────────────────────────────
// The samplesheet is a SEQUENCING structure (sample id + barcodes + sample type); sample_metadata
// is the SUBJECT/clinical sheet that says WHO each library belongs to. Before a run proceeds the two
// are joined so a human can confirm identity. Sample-identity mixups are the highest-consequence
// error at intake, so the join NEVER trusts a single-column (Sample_ID-only) match: it requires
// Sample_ID PLUS a corroborating column — tissue ↔ sample-type, the field both sheets carry — to
// agree. Every row that is not a clean corroborated match is surfaced loudly and BLOCKS the approval
// gate. Pure + client-side (no network): compose ≠ execute, same as the rest of accessioning.
//
// Honest limitation (a labelled seam): when the corroborating column is uniform across a run (e.g.
// every library is Whole blood), tissue agreement cannot reveal a 1-index-off mixup — no field in
// these two sheets discriminates it. A stronger corroborator (subject-level study/site) lands when
// the metadata model widens; the join still catches every mismatch that Sample_ID / tissue CAN.

export type SampleMetaMap = Record<string, { subject_id?: string; tissue?: string }>

export type JoinStatus = 'matched' | 'conflict' | 'weak' | 'unmatched' | 'duplicate'
export type JoinRow = {
  sample: string
  sheetType: string
  metaTissue?: string
  subjectId?: string
  status: JoinStatus
  reason: string
}
export type IdentityJoin = {
  rows: JoinRow[] // one per samplesheet library, in table order
  orphans: { sample: string; subjectId?: string; tissue?: string }[] // metadata subjects not on this flowcell
  counts: Record<JoinStatus, number>
  blocking: number // rows that are NOT a clean corroborated match — these gate approval
  metadataPresent: boolean
}

const normTissue = (s: string | undefined): string => (s ?? '').trim().toLowerCase()

export function computeIdentityJoin(
  samples: { sample: string; type: string }[],
  meta: SampleMetaMap,
): IdentityJoin {
  const metadataPresent = Object.keys(meta).length > 0
  // Count Sample_ID occurrences in the SAMPLESHEET so a duplicated library id reads as ambiguous
  // identity (two rows claiming the same sample) rather than silently last-wins.
  const idCount = new Map<string, number>()
  for (const s of samples) {
    const id = s.sample.trim()
    if (id) idCount.set(id, (idCount.get(id) ?? 0) + 1)
  }
  const rows: JoinRow[] = samples.map((s) => {
    const sample = s.sample.trim()
    const sheetType = s.type
    const m = meta[sample]
    if (!sample) {
      return { sample: s.sample, sheetType, status: 'unmatched', reason: 'Blank sample name — this library cannot be identified.' }
    }
    if ((idCount.get(sample) ?? 0) > 1) {
      return { sample, sheetType, metaTissue: m?.tissue, subjectId: m?.subject_id, status: 'duplicate', reason: `Sample_ID "${sample}" appears ${idCount.get(sample)}× in the samplesheet — ambiguous identity.` }
    }
    if (!m) {
      return { sample, sheetType, status: 'unmatched', reason: 'No sample_metadata row — this library is not identified to a subject.' }
    }
    const metaTissue = m.tissue
    if (!normTissue(metaTissue)) {
      return { sample, sheetType, subjectId: m.subject_id, status: 'weak', reason: 'Matched on Sample_ID only — no corroborating tissue in the metadata to confirm identity.' }
    }
    if (normTissue(metaTissue) === normTissue(sheetType)) {
      return { sample, sheetType, metaTissue, subjectId: m.subject_id, status: 'matched', reason: 'Sample_ID and tissue agree.' }
    }
    return { sample, sheetType, metaTissue, subjectId: m.subject_id, status: 'conflict', reason: `Tissue conflict — samplesheet "${sheetType || '—'}" vs metadata "${metaTissue}".` }
  })
  // Metadata subjects with no matching samplesheet library. Common (a metadata sheet can cover more
  // than one flowcell), so this is a loud INFO — never a hard block, but never hidden either.
  const sheetIds = new Set(samples.map((s) => s.sample.trim()).filter(Boolean))
  const orphans = Object.entries(meta)
    .filter(([id]) => id && !sheetIds.has(id))
    .map(([id, m]) => ({ sample: id, subjectId: m.subject_id, tissue: m.tissue }))
  const counts: Record<JoinStatus, number> = { matched: 0, conflict: 0, weak: 0, unmatched: 0, duplicate: 0 }
  for (const r of rows) counts[r.status]++
  const blocking = rows.length - counts.matched
  return { rows, orphans, counts, blocking, metadataPresent }
}

// A stable signature of the join so an APPROVAL auto-invalidates the moment any edit (a sample type,
// a re-attached metadata sheet, an added/removed row) changes it — a human re-confirms identity after
// any change, never inherits a stale approval.
export function joinSignature(join: IdentityJoin): string {
  return JSON.stringify(join.rows.map((r) => [r.sample, r.sheetType, r.metaTissue ?? '', r.subjectId ?? '', r.status]))
}

// ── Submit identity audit (client-side, labelled seam) ────────────────────────────────────────
// The identity join, its edits, and the human approval are logged to a localStorage feed shaped like
// the Admin Activity rows (when/actor/action/detail). No backend: POST /api/runs carries no subject
// field, so — like the page-access store — this trail is an honest client-side seam, surfaced in the
// Submit screen. Capped so it can't grow unbounded.
export type SubmitAuditEntry = { at: string; actor: string; action: string; detail: string }
const SUBMIT_AUDIT_KEY = 'bayleaf.submit.audit'
const SUBMIT_AUDIT_CAP = 200

export function readSubmitAudit(): SubmitAuditEntry[] {
  try {
    const raw = localStorage.getItem(SUBMIT_AUDIT_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as SubmitAuditEntry[]
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function appendSubmitAudit(entry: SubmitAuditEntry): SubmitAuditEntry[] {
  const next = [entry, ...readSubmitAudit()].slice(0, SUBMIT_AUDIT_CAP)
  try {
    localStorage.setItem(SUBMIT_AUDIT_KEY, JSON.stringify(next))
  } catch {
    // storage unavailable (private mode) — the audit just won't persist across a refresh.
  }
  return next
}
