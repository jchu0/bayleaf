import { useState } from 'react'
import { Archive, ChevronRight, Wrench } from 'lucide-react'
import { PageHeader } from '../components/PageHeader'
import { ArchivistModal, PipelineRepairModal } from '../components/BuilderModals'

// System agents — the org-wide advisory agents (pipeline-repair, archivist) that act ACROSS runs and
// the whole organization, never on a single run and never on a verdict (ADR-0001). Split out of the
// per-run Triage screen so the two nav items aren't near-duplicate pages: Triage triages a run's
// flagged samples; this page launches the run-independent system agents. Each opens a read-only,
// cited proposal modal; advisory + off-gate — neither sets a verdict.
export function SystemAgents() {
  const [repairOpen, setRepairOpen] = useState(false)
  const [archivistOpen, setArchivistOpen] = useState(false)

  return (
    <div className="pg-fade mx-auto max-w-[1080px]">
      <PageHeader
        title="System Agents"
        subtitle="Advisory agents that act across runs and the organization — never a single run, never a verdict."
      />

      <div className="mt-4 grid gap-2.5 sm:grid-cols-2">
        <AgentLauncher
          icon={<Wrench size={16} strokeWidth={2} />}
          title="Pipeline-repair"
          sub="Cited fix proposals for recurring failure signatures"
          onOpen={() => setRepairOpen(true)}
        />
        <AgentLauncher
          icon={<Archive size={16} strokeWidth={2} />}
          title="Archivist"
          sub="Organizes released runs for cold storage"
          onOpen={() => setArchivistOpen(true)}
        />
      </div>

      {repairOpen && <PipelineRepairModal onClose={() => setRepairOpen(false)} />}
      {archivistOpen && <ArchivistModal onClose={() => setArchivistOpen(false)} />}
    </div>
  )
}

// A launcher card for a system advisory agent — opens its read-only proposal modal. Advisory + off-gate:
// it never sets a verdict; the honest "advisory" label rides the card.
function AgentLauncher({ icon, title, sub, onOpen }: { icon: React.ReactNode; title: string; sub: string; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex items-center gap-3 rounded-[11px] border border-line bg-card px-3.5 py-3 text-left transition-colors hover:border-line-strong hover:bg-page"
    >
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-accent-weak text-accent-strong">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="truncate text-[13px] font-semibold text-text">{title}</span>
          <span className="shrink-0 rounded bg-card-2 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-[0.3px] text-text-3">
            advisory
          </span>
        </span>
        <span className="mt-0.5 block truncate text-[11.5px] text-text-2">{sub}</span>
      </span>
      <ChevronRight size={16} className="shrink-0 text-text-3" />
    </button>
  )
}
