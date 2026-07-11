import { useMemo, useState } from 'react'
import { ExternalLink } from 'lucide-react'
import type { RunArtifact } from '../../types'
import { GATE_DOT } from '../../verdict'
import {
  type ArtifactEdge,
  artifactNameTitle,
  distinct,
  fmtSize,
  groupArtifacts,
  originMeta,
  STAGE_GATE,
  STAGE_LABEL,
} from '../../provenance'
import { Empty } from '../States'
import { Pager, type PerPage } from '../Pager'
import { Fingerprint } from './Fingerprint'

// A flat, filterable, paginated artifact index — complements Lineage's per-stage drill-in with a
// whole-run view where "which stages produced/consumed this file" is one row. The endpoint emits
// one row per (stage, role) edge (api/main.py:582-593), so this groups by name and shows the edges
// as chips (e.g. demux_stats.csv collapses to one row: `Demux · out`, `QC · in`). Read-only:
// origin is surfaced verbatim, never relabeled up (a contrived fixture never launders to real).

const ALL = 'all'

export function ProvenanceArtifacts({ artifacts }: { artifacts: RunArtifact[] }) {
  const [stageFilter, setStageFilter] = useState<string>(ALL)
  const [originFilter, setOriginFilter] = useState<string>(ALL)
  const [roleFilter, setRoleFilter] = useState<string>(ALL)
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState<PerPage>('25')

  const groups = useMemo(() => groupArtifacts(artifacts), [artifacts])

  // Filter options list ONLY what's present.
  const stages = useMemo(() => distinct(groups.flatMap((g) => g.edges.map((e) => e.stage))), [groups])
  const origins = useMemo(() => distinct(groups.map((g) => g.origin)), [groups])
  const roles = useMemo(() => distinct(groups.flatMap((g) => g.edges.map((e) => e.role))), [groups])

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return groups.filter(
      (g) =>
        (stageFilter === ALL || g.edges.some((e) => e.stage === stageFilter)) &&
        (originFilter === ALL || g.origin === originFilter) &&
        (roleFilter === ALL || g.edges.some((e) => e.role === roleFilter)) &&
        (needle === '' || g.name.toLowerCase().includes(needle)),
    )
  }, [groups, stageFilter, originFilter, roleFilter, query])

  const per = Number(perPage)
  const pages = Math.max(1, Math.ceil(filtered.length / per))
  const cur = Math.min(page, pages)
  const pageGroups = filtered.slice((cur - 1) * per, cur * per)

  const resetPage = () => setPage(1)

  if (groups.length === 0) return <Empty message="No data artifacts registered for this run." />

  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-[12px] border border-line bg-card px-4 py-3">
        <FilterSelect
          label="Stage"
          value={stageFilter}
          onChange={(v) => {
            setStageFilter(v)
            resetPage()
          }}
          options={[{ value: ALL, label: 'All stages' }, ...stages.map((s) => ({ value: s, label: STAGE_LABEL[s] }))]}
        />
        <FilterSelect
          label="Origin"
          value={originFilter}
          onChange={(v) => {
            setOriginFilter(v)
            resetPage()
          }}
          options={[{ value: ALL, label: 'All origins' }, ...origins.map((o) => ({ value: o, label: originMeta(o).label }))]}
        />
        <FilterSelect
          label="Role"
          value={roleFilter}
          onChange={(v) => {
            setRoleFilter(v)
            resetPage()
          }}
          options={[{ value: ALL, label: 'Input & output' }, ...roles.map((r) => ({ value: r, label: r }))]}
        />
        <label className="flex items-center gap-1.5 text-[11.5px] text-text-3">
          Search
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              resetPage()
            }}
            placeholder="file name"
            className="w-[160px] rounded-lg border border-line bg-card px-2.5 py-1 text-[12.5px] text-text outline-none focus:border-accent"
          />
        </label>
      </div>

      {filtered.length === 0 ? (
        <div className="mt-4">
          <Empty message="No artifacts match these filters." />
        </div>
      ) : (
        <>
          <div className="mt-4 overflow-hidden rounded-[10px] border border-line">
            <div className="grid grid-cols-[1.5fr_1.4fr_0.8fr_0.6fr_1.5fr] bg-card-2 text-[9.5px] font-semibold uppercase tracking-[0.4px] text-text-3">
              <div className="px-[13px] py-[9px]">Name</div>
              <div className="px-[10px] py-[9px]">Stages · role</div>
              <div className="px-[10px] py-[9px]">Origin</div>
              <div className="px-[10px] py-[9px]">Size</div>
              <div className="px-[10px] py-[9px]">Integrity</div>
            </div>
            {pageGroups.map((g, i) => {
              const om = originMeta(g.origin)
              return (
                <div
                  key={g.name}
                  className={`grid grid-cols-[1.5fr_1.4fr_0.8fr_0.6fr_1.5fr] items-start border-t border-line ${
                    i % 2 === 1 ? 'bg-card-2' : 'bg-card'
                  }`}
                >
                  <div className="min-w-0 px-[13px] py-[10px]">
                    <a
                      href={g.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={artifactNameTitle(g.name)}
                      className="inline-flex items-center gap-[5px] break-all font-mono text-[12px] font-medium text-accent-strong hover:underline"
                    >
                      <ExternalLink size={11} strokeWidth={1.9} className="shrink-0" />
                      {g.name}
                    </a>
                  </div>
                  <div className="flex flex-wrap items-center gap-1 px-[10px] py-[10px]">
                    {g.edges.map((e, j) => (
                      <EdgeChip key={j} edge={e} />
                    ))}
                  </div>
                  <div className="px-[10px] py-[10px]">
                    <span
                      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium ${om.chip}`}
                      title={om.tip}
                    >
                      {om.label}
                    </span>
                  </div>
                  <div className="px-[10px] py-[10px] text-[11.5px] text-text-2">{fmtSize(g.size_bytes)}</div>
                  <div className="flex flex-wrap items-center gap-[10px] px-[10px] py-[10px]">
                    <Fingerprint value={g.sha256} />
                    <a
                      href={`${g.url}?download=1`}
                      download={g.name}
                      title="Download artifact"
                      className="text-[11px] text-accent-strong hover:underline"
                    >
                      download
                    </a>
                  </div>
                </div>
              )
            })}
          </div>
          <Pager total={filtered.length} page={cur} perPage={perPage} onPage={setPage} onPerPage={setPerPage} noun="artifacts" />
        </>
      )}
    </div>
  )
}

// One (stage, role) edge chip — gate-dotted where the stage sits under a gate checkpoint.
function EdgeChip({ edge }: { edge: ArtifactEdge }) {
  const gate = STAGE_GATE[edge.stage]
  const roleShort = edge.role === 'input' ? 'in' : edge.role === 'output' ? 'out' : edge.role
  return (
    <span className="inline-flex items-center gap-1 rounded-[5px] border border-line bg-card px-1.5 py-px text-[10px] font-medium text-text-2">
      {gate && <span className={`h-[5px] w-[5px] rounded-full ${GATE_DOT[gate]}`} />}
      {STAGE_LABEL[edge.stage]} · {roleShort}
    </span>
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
