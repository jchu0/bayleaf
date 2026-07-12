import { useEffect, useState } from 'react'
import { ChevronRight, File as FileIcon, Folder, Home, Loader2, TriangleAlert, X } from 'lucide-react'
import { api } from '../api'
import type { FileEntry, FileKind } from '../types'

// Sandboxed server-side file picker (GET /api/files). The GB-scale genomics inputs live on the
// COMPUTE HOST, so the picker lists them server-side and returns only metadata (name/size/kind) — the
// bytes never reach the browser (ADR-0020 / files.py). Off-gate, read-only: it lists file metadata,
// never reads content, runs a tool, or touches a verdict (ADR-0001/0003). Used by the Builder's
// "Browse…" affordance beside a type-a-path field; the manual text input stays (browse is ADDITIVE).

function humanBytes(n: number | null): string {
  if (n == null) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

export type FileBrowserProps = {
  title?: string
  // The allowlisted root KEY (a configured key, never a raw path — files.py). Default 'data'.
  root?: string
  initialPath?: string
  // When set, ONLY files of these kinds are selectable; other files render greyed (dirs stay navigable).
  kinds?: FileKind[]
  // Called with the chosen path RELATIVE to the root; the caller writes it into its path field.
  onPick: (path: string) => void
  onClose: () => void
}

export function FileBrowser({
  title = 'Browse server files',
  root = 'data',
  initialPath = '',
  kinds,
  onPick,
  onClose,
}: FileBrowserProps) {
  const [path, setPath] = useState(initialPath)
  const [entries, setEntries] = useState<FileEntry[] | null>(null)
  const [parent, setParent] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // One level per fetch (the endpoint lists a single directory). `path` is already canonical (built
  // from entry names below), so we don't echo the response path back — that would risk a fetch loop.
  useEffect(() => {
    let live = true
    setLoading(true)
    setError(null)
    api
      .browseFiles(root, path)
      .then((l) => {
        if (!live) return
        setEntries(l.entries)
        setParent(l.parent)
        setLoading(false)
      })
      .catch((e) => {
        if (!live) return
        setError(e instanceof Error ? e.message : String(e))
        setEntries(null)
        setLoading(false)
      })
    return () => {
      live = false
    }
  }, [root, path])

  const join = (name: string) => (path ? `${path}/${name}` : name)
  const selectable = (e: FileEntry) => !e.is_dir && (!kinds || (e.kind != null && kinds.includes(e.kind)))
  const crumbs = path ? path.split('/') : []

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-[rgba(16,24,40,.4)] p-6" onClick={onClose}>
      <div
        className="flex max-h-full w-[560px] max-w-full flex-col overflow-hidden rounded-2xl border border-line-strong bg-card shadow-pop"
        onClick={(e) => e.stopPropagation()}
      >
        {/* header */}
        <div className="flex items-start gap-3 border-b border-line px-4 py-3.5">
          <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-card-2 text-text-2">
            <Folder size={16} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[14px] font-semibold text-text">{title}</div>
            <div className="mt-0.5 text-[11px] text-text-3">
              Server-side · <span className="font-mono">{root}/</span> — file contents never leave the host, only the path is selected.
              {kinds && (
                <>
                  {' '}
                  Filtered to <span className="font-mono text-text-2">{kinds.join(', ')}</span>.
                </>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="grid h-7 w-7 shrink-0 place-items-center rounded-md border border-line bg-card text-text-2 hover:bg-page"
          >
            <X size={14} />
          </button>
        </div>

        {/* breadcrumb */}
        <div className="flex items-center gap-1 overflow-x-auto border-b border-line bg-card-2 px-4 py-2 text-[11.5px]">
          <button
            onClick={() => setPath('')}
            className="inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 font-mono text-text-2 hover:bg-page"
            title="Root"
          >
            <Home size={12} /> {root}
          </button>
          {crumbs.map((seg, i) => {
            const to = crumbs.slice(0, i + 1).join('/')
            const isLast = i === crumbs.length - 1
            return (
              <span key={to} className="inline-flex shrink-0 items-center gap-1">
                <ChevronRight size={11} className="text-text-3" />
                <button
                  onClick={() => setPath(to)}
                  className={`rounded px-1.5 py-0.5 font-mono hover:bg-page ${isLast ? 'font-semibold text-text' : 'text-text-2'}`}
                >
                  {seg}
                </button>
              </span>
            )
          })}
        </div>

        {/* listing */}
        <div className="min-h-[220px] flex-1 overflow-y-auto px-3 py-2.5">
          {loading ? (
            <p className="inline-flex items-center gap-1.5 px-1 py-6 text-[12.5px] text-text-3">
              <Loader2 size={13} className="animate-spin" /> Listing…
            </p>
          ) : error ? (
            <div className="flex items-start gap-2 rounded-[9px] border border-hold-bd bg-hold-bg px-3 py-2.5 text-[11.5px] text-hold-fg">
              <TriangleAlert size={14} className="mt-0.5 shrink-0" />
              <span>Couldn’t list this directory — {error}</span>
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              {parent != null && (
                <button
                  onClick={() => setPath(parent)}
                  className="flex items-center gap-2.5 rounded-lg border border-line px-2.5 py-1.5 text-left hover:border-line-strong hover:bg-page"
                >
                  <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-card-2 text-text-3">
                    <Folder size={13} />
                  </span>
                  <span className="font-mono text-[12px] text-text-2">.. (up a level)</span>
                </button>
              )}
              {entries && entries.length === 0 && (
                <p className="px-1 py-4 text-[12px] text-text-3">This directory is empty.</p>
              )}
              {entries?.map((e) => {
                if (e.is_dir) {
                  return (
                    <button
                      key={e.name}
                      onClick={() => setPath(join(e.name))}
                      className="flex items-center gap-2.5 rounded-lg border border-line px-2.5 py-1.5 text-left hover:border-line-strong hover:bg-page"
                    >
                      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-card-2 text-accent-strong">
                        <Folder size={13} />
                      </span>
                      <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-text">{e.name}</span>
                      <ChevronRight size={14} className="shrink-0 text-text-3" />
                    </button>
                  )
                }
                const ok = selectable(e)
                return (
                  <button
                    key={e.name}
                    disabled={!ok}
                    onClick={() => ok && onPick(join(e.name))}
                    title={ok ? 'Select this file' : kinds ? `Not a ${kinds.join(' / ')} file` : undefined}
                    className={`flex items-center gap-2.5 rounded-lg border px-2.5 py-1.5 text-left ${
                      ok ? 'cursor-pointer border-line hover:border-accent hover:bg-page' : 'cursor-not-allowed border-line bg-card-2 opacity-60'
                    }`}
                  >
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-card-2 text-text-3">
                      <FileIcon size={13} />
                    </span>
                    <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-text-2">{e.name}</span>
                    {e.kind && (
                      <span className="shrink-0 rounded border border-line bg-card px-1.5 py-0.5 font-mono text-[9.5px] text-text-3">{e.kind}</span>
                    )}
                    <span className="shrink-0 font-mono text-[10px] text-text-3">{humanBytes(e.size)}</span>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* footer */}
        <div className="flex items-center gap-2.5 border-t border-line px-4 py-3">
          <span className="flex-1 text-[10.5px] leading-snug text-text-3">
            Read-only · click a file to select its server path. Browse is additive — you can still type a path.
          </span>
          <button
            onClick={onClose}
            className="rounded-lg border border-line bg-card px-3 py-1.5 text-[12.5px] text-text-2 hover:border-line-strong"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}
