import { useState } from 'react'
import { ChevronDown, GitBranch, Plus, Search } from 'lucide-react'
import { BUILTIN_PROFILES, SAVED_PROFILES } from './BuilderShared'

// Searchable profile combobox (README §6): built-in (default/giab_panel/sarek) + saved
// profiles (versioned, with status) + "New profile from current graph". Only approved graphs
// emit a blessed config; saved profiles carry a draft→approved lifecycle (§7 backend seam).

export function BuilderProfileCombobox({
  profile,
  open,
  onToggle,
  onSelect,
  onNewFromGraph,
}: {
  profile: string
  open: boolean
  onToggle: () => void
  onSelect: (p: string) => void
  onNewFromGraph: () => void
}) {
  const [query, setQuery] = useState('')
  const q = query.trim().toLowerCase()
  const builtin = BUILTIN_PROFILES.filter((p) => !q || p.toLowerCase().includes(q))
  const saved = SAVED_PROFILES.filter((p) => !q || p.k.toLowerCase().includes(q))

  return (
    <div className="relative shrink-0">
      <button
        onClick={onToggle}
        className="flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-2.5 py-1.5 hover:border-line"
      >
        <GitBranch size={14} className="text-text-2" />
        <span className="font-mono text-[12px] font-semibold text-text">{profile}</span>
        <ChevronDown size={12} className="text-text-3" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={onToggle} />
          <div className="absolute right-0 top-[38px] z-50 w-[252px] overflow-hidden rounded-xl border border-line-strong bg-card shadow-pop">
            <div className="flex items-center gap-1.5 border-b border-line px-3 py-2">
              <Search size={13} className="text-text-3" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search profiles…"
                className="min-w-0 flex-1 bg-transparent text-[11.5px] text-text placeholder:text-text-3 focus:outline-none"
              />
            </div>
            <div className="px-2 py-1.5">
              <div className="px-1.5 py-1 text-[9.5px] font-bold uppercase tracking-[0.4px] text-text-3">Built-in</div>
              {builtin.map((p) => (
                <button
                  key={p}
                  onClick={() => onSelect(p)}
                  className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left ${
                    profile === p ? 'bg-accent-weak' : 'hover:bg-page'
                  }`}
                >
                  <span className="font-mono text-[12px] text-text">{p}</span>
                </button>
              ))}
              <div className="px-1.5 pb-1 pt-2 text-[9.5px] font-bold uppercase tracking-[0.4px] text-text-3">Saved</div>
              {saved.map((p) => (
                <button
                  key={p.k}
                  onClick={() => onSelect(p.k)}
                  className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left ${
                    profile === p.k ? 'bg-accent-weak' : 'hover:bg-page'
                  }`}
                >
                  <span className="font-mono text-[12px] text-text">{p.k}</span>
                  <span className="ml-auto font-mono text-[9.5px] text-text-3">
                    {p.ver} · {p.status}
                  </span>
                </button>
              ))}
            </div>
            <button
              onClick={onNewFromGraph}
              className="flex w-full items-center gap-1.5 border-t border-line px-3 py-2.5 text-accent hover:bg-page"
            >
              <Plus size={14} />
              <span className="text-[12px] font-semibold">New profile from current graph</span>
            </button>
          </div>
        </>
      )}
    </div>
  )
}
