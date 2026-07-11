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
const HANDOFF_KEY = 'pipeguard.accession.handoff'
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
const DRAFT_KEY = 'pipeguard.accession.draft'

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
