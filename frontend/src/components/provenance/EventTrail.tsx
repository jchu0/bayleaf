import { Fragment, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import type { DecisionCard, EntityRef, Finding, ProvenanceEvent } from '../../types'
import { STATUS_CHIP } from '../../verdict'
import {
  EVENT_META,
  eventMatches,
  fmtPayloadValue,
  fmtTime,
  distinct,
  indexCards,
  indexFindings,
  readSeverity,
  readVerdict,
  summarizeEvent,
} from '../../provenance'
import { CollapsibleRow } from '../CollapsibleRow'
import { CitedEvidence } from '../EvidenceTable'
import { VerdictBadge } from '../VerdictBadge'
import { Empty } from '../States'
import { Pager, type PerPage } from '../Pager'
import { SegmentedControl } from '../SegmentedControl'
import { Fingerprint } from './Fingerprint'

// The append-only event trail — the honest centerpiece of PV1. It renders `RunDetail.events`, the
// real ledger trail that already ships to the client (engine.py:90-171) but the screen used to
// throw away — filterable, paginated, with inline finding→evidence / verdict→card trace-back.
// 100% read-only: no write, no verdict/confidence set; the verdicts/findings shown are quoted
// verbatim from the events the rule engine authored (ADR-0001). Scale driver: a 100-sample run
// emits ~500 events (2 + 2N + F), so every list is dropdown-filtered + paginated, never unbounded.

type Order = 'oldest' | 'newest'
const ALL = 'all'

export function EventTrail({ events, cards, runId }: { events: ProvenanceEvent[]; cards: DecisionCard[]; runId: string }) {
  const [typeFilter, setTypeFilter] = useState<string>(ALL)
  const [sampleFilter, setSampleFilter] = useState<string>(ALL)
  const [actorFilter, setActorFilter] = useState<string>(ALL)
  const [query, setQuery] = useState('')
  const [order, setOrder] = useState<Order>('oldest') // oldest-first = the causal narrative
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState<PerPage>('25')
  const [openId, setOpenId] = useState<string | null>(null) // single-open accordion — caps expanded evidence to one block

  // Filter options list ONLY what's present (no dead options at scale).
  const types = useMemo(() => distinct(events.map((e) => e.event_type)), [events])
  const samples = useMemo(() => distinct(events.map((e) => e.sample_id).filter((s): s is string => !!s)), [events])
  const actors = useMemo(() => distinct(events.map((e) => e.actor)), [events])

  // Trace-back maps built once — a finding.id → its cited finding, a sample_id → its card.
  const findingIx = useMemo(() => indexFindings(cards), [cards])
  const cardIx = useMemo(() => indexCards(cards), [cards])

  const filtered = useMemo(() => {
    const base = events.filter(
      (e) =>
        (typeFilter === ALL || e.event_type === typeFilter) &&
        (sampleFilter === ALL || e.sample_id === sampleFilter) &&
        (actorFilter === ALL || e.actor === actorFilter) &&
        eventMatches(e, query),
    )
    // The ledger emits in chronological order (provenance.py:99-105); newest just reverses it.
    return order === 'newest' ? [...base].reverse() : base
  }, [events, typeFilter, sampleFilter, actorFilter, query, order])

  const per = Number(perPage)
  const pages = Math.max(1, Math.ceil(filtered.length / per))
  const cur = Math.min(page, pages)
  const pageEvents = filtered.slice((cur - 1) * per, cur * per)

  const resetPage = () => setPage(1)
  const resetFilters = () => {
    setTypeFilter(ALL)
    setSampleFilter(ALL)
    setActorFilter(ALL)
    setQuery('')
    resetPage()
  }
  const filtersActive = typeFilter !== ALL || sampleFilter !== ALL || actorFilter !== ALL || query !== ''

  // A run still `running` (or with no completed trail) ships no events — honest, not an error.
  if (events.length === 0) {
    return <Empty message="No provenance events recorded yet — this run hasn't completed the gate." />
  }

  return (
    <div>
      {/* Filter bar — native <select> dropdowns (single-choice; a browser handles a 100-option
          sample list natively, no pill row) + free-text search + order toggle. */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-[12px] border border-line bg-card px-4 py-3">
        <FilterSelect
          label="Type"
          value={typeFilter}
          onChange={(v) => {
            setTypeFilter(v)
            resetPage()
          }}
          options={[{ value: ALL, label: 'All types' }, ...types.map((t) => ({ value: t, label: EVENT_META[t]?.label ?? t }))]}
        />
        <FilterSelect
          label="Sample"
          value={sampleFilter}
          onChange={(v) => {
            setSampleFilter(v)
            resetPage()
          }}
          options={[{ value: ALL, label: 'All samples' }, ...samples.map((s) => ({ value: s, label: s }))]}
        />
        <FilterSelect
          label="Actor"
          value={actorFilter}
          onChange={(v) => {
            setActorFilter(v)
            resetPage()
          }}
          options={[{ value: ALL, label: 'All actors' }, ...actors.map((a) => ({ value: a, label: a }))]}
        />
        <label className="flex items-center gap-1.5 text-[11.5px] text-text-3">
          Search
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              resetPage()
            }}
            placeholder="id · rule · signature"
            className="w-[180px] rounded-lg border border-line bg-card px-2.5 py-1 text-[12.5px] text-text outline-none focus:border-accent"
          />
        </label>
        <div className="ml-auto flex items-center gap-3">
          {filtersActive && (
            <button type="button" onClick={resetFilters} className="text-[11.5px] text-accent-strong hover:underline">
              Reset filters
            </button>
          )}
          <SegmentedControl<Order>
            options={[
              { value: 'oldest', label: 'Oldest' },
              { value: 'newest', label: 'Newest' },
            ]}
            value={order}
            onChange={(o) => {
              setOrder(o)
              resetPage()
            }}
          />
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="mt-4">
          <Empty message="No events match these filters." />
        </div>
      ) : (
        <>
          <div className="mt-4 flex flex-col gap-2">
            {pageEvents.map((e) => (
              <EventRow
                key={e.id}
                event={e}
                open={openId === e.id}
                onToggle={() => setOpenId((prev) => (prev === e.id ? null : e.id))}
                findingIx={findingIx}
                cardIx={cardIx}
                runId={runId}
              />
            ))}
          </div>
          <Pager total={filtered.length} page={cur} perPage={perPage} onPage={setPage} onPerPage={setPerPage} noun="events" />
        </>
      )}
    </div>
  )
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <label className="flex items-center gap-1.5 text-[11.5px] text-text-3">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="max-w-[180px] rounded-lg border border-line bg-card px-2 py-1 text-[12.5px] text-text outline-none focus:border-accent"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  )
}

function EventRow({
  event,
  open,
  onToggle,
  findingIx,
  cardIx,
  runId,
}: {
  event: ProvenanceEvent
  open: boolean
  onToggle: () => void
  findingIx: Map<string, { finding: Finding; sampleId: string }>
  cardIx: Map<string, DecisionCard>
  runId: string
}) {
  const header = (
    <div className="flex flex-wrap items-center gap-2.5">
      <span className="shrink-0 font-mono text-[11px] tabular-nums text-text-3">{fmtTime(event.created_at)}</span>
      <TypeChip event={event} />
      <span className="min-w-0 text-[12.5px] text-text">{summarizeEvent(event)}</span>
      {event.sample_id && (
        <span className="rounded-[5px] border border-line bg-card-2 px-1.5 py-px font-mono text-[10.5px] text-text-2">
          {event.sample_id}
        </span>
      )}
    </div>
  )

  // The expanded body is the trace-back: a finding resolves to its cited evidence in place, a
  // verdict to its decision card; everything else (and any unresolved ref) shows the raw payload.
  const body =
    event.event_type === 'finding.emitted' ? (
      <FindingTrace event={event} findingIx={findingIx} />
    ) : event.event_type === 'verdict.decided' ? (
      <VerdictTrace event={event} cardIx={cardIx} runId={runId} />
    ) : (
      <PayloadBlock event={event} />
    )

  return (
    <CollapsibleRow open={open} onToggle={onToggle} header={header}>
      {body}
    </CollapsibleRow>
  )
}

// The collapsed-row type chip: finding is recolored by severity, verdict renders as a VerdictBadge,
// an unknown type is shown verbatim (never faked into a known one).
function TypeChip({ event }: { event: ProvenanceEvent }) {
  const t = event.event_type
  const p = event.payload ?? {}

  if (t === 'verdict.decided') {
    const v = readVerdict(p)
    if (v) return <VerdictBadge verdict={v} />
  }

  const meta = EVENT_META[t]
  const base = 'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide'

  if (t === 'finding.emitted' && meta) {
    const sev = readSeverity(p)
    const cls = sev ? STATUS_CHIP[sev].cls : meta.chip
    const Icon = meta.icon
    return (
      <span className={`${base} ${cls}`}>
        <Icon size={11} strokeWidth={2.2} />
        {meta.label}
      </span>
    )
  }
  if (meta) {
    const Icon = meta.icon
    return (
      <span className={`${base} ${meta.chip}`}>
        <Icon size={11} strokeWidth={2.2} />
        {meta.label}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center rounded-full border border-line bg-card-2 px-2 py-0.5 font-mono text-[10.5px] font-semibold text-text-3">
      {t}
    </span>
  )
}

function FindingTrace({
  event,
  findingIx,
}: {
  event: ProvenanceEvent
  findingIx: Map<string, { finding: Finding; sampleId: string }>
}) {
  const ref = event.outputs[0]
  const hit = ref ? findingIx.get(ref.id) : undefined
  if (!hit) return <PayloadBlock event={event} />
  return (
    <div className="flex flex-col gap-3">
      <div className="text-[10px] font-semibold uppercase tracking-[0.4px] text-text-3">Traced to its cited evidence</div>
      <CitedEvidence findings={[hit.finding]} variant="dense" />
      <FingerprintRow label="Finding fingerprint" value={ref?.content_hash ?? null} />
    </div>
  )
}

function VerdictTrace({ event, cardIx, runId }: { event: ProvenanceEvent; cardIx: Map<string, DecisionCard>; runId: string }) {
  const ref = event.outputs[0]
  const card = ref ? cardIx.get(ref.id) : undefined
  if (!card) return <PayloadBlock event={event} />
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-center gap-2.5">
        <VerdictBadge verdict={card.verdict} />
        <span className="text-[13px] font-semibold text-text">{card.headline}</span>
      </div>
      {card.rationale && <p className="text-[12.5px] leading-[1.5] text-text-2">{card.rationale}</p>}
      {/* Soft deep-link: RunDetail reads ?filter=<verdict> (RunDetail.tsx:111) — a verdict-filtered
          jump, not a scroll-to-sample (the evidence is already shown inline above). */}
      <Link
        to={`/runs/${runId}?filter=${card.verdict}`}
        className="w-fit text-[12px] font-medium text-accent-strong hover:underline"
      >
        View decision card →
      </Link>
      <FingerprintRow label="Card fingerprint" value={ref?.content_hash ?? null} />
    </div>
  )
}

// started / completed / sample.registered / unknown / any unresolved ref → the raw payload k/v +
// any entity refs. Reads the untyped payload verbatim, never inventing a field.
function PayloadBlock({ event }: { event: ProvenanceEvent }) {
  const payload = event.payload ?? {}
  const keys = Object.keys(payload)
  return (
    <div className="flex flex-col gap-3">
      {keys.length === 0 ? (
        <p className="font-mono text-[11.5px] text-text-3">No payload recorded for this event.</p>
      ) : (
        <dl className="grid grid-cols-[minmax(90px,auto)_1fr] gap-x-4 gap-y-1 font-mono text-[11.5px]">
          {keys.map((k) => (
            <Fragment key={k}>
              <dt className="text-text-3">{k}</dt>
              <dd className="break-all text-text-2">{fmtPayloadValue(payload[k])}</dd>
            </Fragment>
          ))}
        </dl>
      )}
      {event.inputs.length > 0 && <RefList label="Inputs" refs={event.inputs} />}
      {event.outputs.length > 0 && <RefList label="Outputs" refs={event.outputs} />}
    </div>
  )
}

function RefList({ label, refs }: { label: string; refs: EntityRef[] }) {
  return (
    <div>
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.4px] text-text-3">{label}</div>
      <div className="flex flex-col gap-1.5">
        {refs.map((r, i) => (
          <div key={i} className="flex flex-wrap items-center gap-[10px] text-[11.5px]">
            <span className="rounded-[5px] border border-line bg-card-2 px-1.5 py-px font-mono text-[10.5px] text-text-2">
              {r.entity_type}
            </span>
            <span className="break-all font-mono text-text-2">{r.id}</span>
            <Fingerprint value={r.content_hash} label="fingerprint" />
          </div>
        ))}
      </div>
    </div>
  )
}

// The entity-ref fingerprint is the IMMUTABLE-ENTITY content hash (EntityRef.content_hash,
// provenance.py:45) — distinct from a file's content fingerprint; the tooltip says so.
function FingerprintRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex flex-wrap items-center gap-[10px]">
      <span
        className="text-[10px] font-semibold uppercase tracking-[0.4px] text-text-3"
        title="An immutable-entity fingerprint (EntityRef.content_hash) — distinct from a file's content fingerprint."
      >
        {label}
      </span>
      <Fingerprint value={value} label="fingerprint" />
    </div>
  )
}
