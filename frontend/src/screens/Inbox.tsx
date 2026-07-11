import {
  AtSign,
  BellPlus,
  CalendarDays,
  Check,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  Circle,
  ExternalLink,
  Flag,
  Folder,
  FolderPlus,
  Inbox as InboxIcon,
  LayoutGrid,
  Mail,
  MessageSquare,
  Pencil,
  Plus,
  RotateCw,
  Send,
  StickyNote,
  Trash2,
  X,
} from 'lucide-react'
import { type ChangeEvent, type KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { DEMO_ACCOUNTS } from '../auth'
import { useConfirm } from '../components/ConfirmDialog'
import { PageHeader } from '../components/PageHeader'
import { Pager, PER_PAGE_25, type PerPage } from '../components/Pager'
import { Truncate } from '../components/Truncate'
import { SegmentedControl, type SegmentOption } from '../components/SegmentedControl'
import { Empty, ErrorBox, Loading } from '../components/States'
import { useToast } from '../components/Toast'
import {
  type InboxColumn,
  type InboxComment,
  type InboxItem,
  type InboxNotify,
  type InboxPriority,
  MAX_LEADS,
  type NotifyCadence,
  type NotifyChannel,
  useInbox,
} from '../context/InboxContext'
import { useRole } from '../context/RoleContext'
import {
  COLUMN_LABEL,
  COLUMNS,
  DUE_META,
  dueStatus,
  initials,
  localYmd,
  PRIORITY_META,
  PRIORITY_ORDER,
  shortItemId,
  SOURCE_META,
  timeAgo,
  todayYmd,
} from '../inbox'

type Tab = 'inbox' | 'board' | 'calendar' | 'notes'
const TABS: SegmentOption<Tab>[] = [
  { value: 'inbox', label: 'Inbox' },
  { value: 'board', label: 'Board' },
  { value: 'calendar', label: 'Calendar' },
  { value: 'notes', label: 'Notes' },
]

// ── shared small pieces ────────────────────────────────────────────────────────
function PriorityChip({ p }: { p: InboxPriority }) {
  if (p === 'none') return null
  const m = PRIORITY_META[p]
  return <span className={`rounded-full border px-1.5 py-px text-[10px] font-medium ${m.chip}`}>{m.label}</span>
}
function DueChip({ due }: { due: string | null }) {
  const st = dueStatus(due)
  if (st === 'none') return null
  const m = DUE_META[st]
  return (
    <span className={`rounded-full border px-1.5 py-px text-[10px] font-medium ${m.chip}`} title={due ?? undefined}>
      {m.label}
    </span>
  )
}
// ── IB14: kanban QOL — ids, assignees, @-mention comments (UIC-14), all off the gate ─────────────
function accountName(id: string): string {
  return DEMO_ACCOUNTS.find((a) => a.id === id)?.name ?? id
}
// A round initials chip for a roster member — the assignment surface on cards + comments.
function Avatar({ id, size = 18 }: { id: string; size?: number }) {
  const name = accountName(id)
  return (
    <span
      className="grid shrink-0 place-items-center rounded-full bg-accent-weak font-semibold text-accent-strong"
      style={{ width: size, height: size, fontSize: Math.round(size * 0.42) }}
      title={name}
    >
      {initials(name)}
    </span>
  )
}
// A comment body with @handles resolved to the mentioned member's display name + accent highlight.
function CommentBody({ body }: { body: string }) {
  const parts = body.split(/(@[a-z0-9._-]+)/gi)
  return (
    <p className="whitespace-pre-wrap break-words text-[12px] leading-snug text-text-2">
      {parts.map((p, i) => {
        if (p.startsWith('@')) {
          const acct = DEMO_ACCOUNTS.find((a) => a.id === p.slice(1))
          if (acct) {
            return (
              <span key={i} className="rounded bg-accent-weak px-1 font-medium text-accent-strong">
                @{acct.name}
              </span>
            )
          }
        }
        return <span key={i}>{p}</span>
      })}
    </p>
  )
}
// ── IB4: per-reminder notification config (Slack/Teams/Discord/email + cadence + ≤3 reminders) ──
const NOTIFY_CHANNELS: { k: NotifyChannel; label: string }[] = [
  { k: 'slack', label: 'Slack' },
  { k: 'teams', label: 'Teams' },
  { k: 'discord', label: 'Discord' },
  { k: 'email', label: 'Email' },
]
const NOTIFY_CADENCES: NotifyCadence[] = ['once', 'daily', 'weekdays']
const LEAD_OPTS = ['At time', '10 min before', '1 hour before', '1 day before']

function NotifyEditor({ item }: { item: InboxItem }) {
  const { setNotify } = useInbox()
  const { toast } = useToast()
  const n = item.notify
  if (!n) {
    return (
      <button
        onClick={() => setNotify(item.id, { channels: ['slack'], cadence: 'once', leads: ['At time'] })}
        className="inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1 text-[12px] text-text-2 hover:border-accent hover:text-accent-strong"
      >
        <BellPlus size={13} /> Notify me
      </button>
    )
  }
  const update = (patch: Partial<InboxNotify>) => setNotify(item.id, { ...n, ...patch })
  const toggleChannel = (c: NotifyChannel) =>
    update({ channels: n.channels.includes(c) ? n.channels.filter((x) => x !== c) : [...n.channels, c] })
  const toggleLead = (l: string) => {
    if (n.leads.includes(l)) update({ leads: n.leads.filter((x) => x !== l) })
    else if (n.leads.length < MAX_LEADS) update({ leads: [...n.leads, l] })
    else toast(`Up to ${MAX_LEADS} reminders per item.`, 'info')
  }
  return (
    <div className="w-full rounded-md border border-line bg-card-2 p-2.5">
      <div className="flex items-center justify-between">
        <span className="text-[10.5px] font-semibold uppercase tracking-[0.4px] text-text-3">
          Notify · phase-2 seam (not yet wired to a live ping)
        </span>
        <button onClick={() => setNotify(item.id, null)} className="text-[11px] text-text-3 hover:text-escalate">
          Remove
        </button>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {NOTIFY_CHANNELS.map((c) => (
          <button
            key={c.k}
            onClick={() => toggleChannel(c.k)}
            className={`rounded-full border px-2 py-0.5 text-[11px] transition-colors ${
              n.channels.includes(c.k) ? 'border-accent bg-accent-weak text-accent-strong' : 'border-line text-text-3 hover:border-line-strong'
            }`}
          >
            {c.label}
          </button>
        ))}
        <select
          value={n.cadence}
          onChange={(e) => update({ cadence: e.target.value as NotifyCadence })}
          className="ml-1 rounded-md border border-line bg-card px-1.5 py-1 text-[11px] capitalize text-text-2"
          aria-label="Notification cadence"
        >
          {NOTIFY_CADENCES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <span className="text-[10.5px] text-text-3">
          Reminders ({n.leads.length}/{MAX_LEADS}):
        </span>
        {LEAD_OPTS.map((l) => (
          <button
            key={l}
            onClick={() => toggleLead(l)}
            className={`rounded-full border px-2 py-0.5 text-[11px] transition-colors ${
              n.leads.includes(l) ? 'border-accent bg-accent-weak text-accent-strong' : 'border-line text-text-3 hover:border-line-strong'
            }`}
          >
            {l}
          </button>
        ))}
      </div>
    </div>
  )
}

// ── INBOX tab: the triage stream ───────────────────────────────────────────────
type InboxFilter = 'all' | 'unread' | 'flagged'

function InboxRow({ item }: { item: InboxItem }) {
  const { markRead, toggleFlag, setPriority, setColumn, setDue, setNote, deleteSelfItem } = useInbox()
  const [open, setOpen] = useState(false)
  const src = SOURCE_META[item.source]
  return (
    <div className={`rounded-[11px] border bg-card transition-colors ${item.read ? 'border-line' : 'border-line-strong'}`}>
      <div className="flex items-start gap-2.5 px-3.5 py-2.5">
        <button
          onClick={() => markRead(item.id, !item.read)}
          className="mt-1 shrink-0"
          title={item.read ? 'Mark unread' : 'Mark read'}
          aria-label={item.read ? 'Mark unread' : 'Mark read'}
        >
          <span className={`block h-2.5 w-2.5 rounded-full border ${item.read ? 'border-line-strong bg-transparent' : 'border-accent bg-accent'}`} />
        </button>
        <button onClick={() => setOpen((o) => !o)} className="min-w-0 flex-1 text-left">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className={`rounded-md border px-1.5 py-px text-[10px] font-medium ${src.badge}`}>{src.label}</span>
            <PriorityChip p={item.priority} />
            <DueChip due={item.due} />
            {item.column !== 'inbox' && (
              <span className="rounded-full border border-line bg-card-2 px-1.5 py-px text-[10px] text-text-2">
                {COLUMN_LABEL[item.column]}
              </span>
            )}
            {item.note && <StickyNote size={12} className="text-text-3" />}
          </div>
          <div className={`mt-1 text-[13px] leading-snug ${item.read ? 'text-text-2' : 'font-medium text-text'}`}>
            {item.title}
          </div>
          <div className="mt-0.5 flex items-center gap-2 text-[11px] text-text-3">
            {item.runId && <span className="font-mono">{item.runId}</span>}
            {item.sampleId && <span className="font-mono">· {item.sampleId}</span>}
            <span>· {timeAgo(item.createdAt)}</span>
          </div>
        </button>
        <button
          onClick={() => toggleFlag(item.id)}
          className={`mt-0.5 shrink-0 rounded-md p-1 transition-colors ${item.flagged ? 'text-escalate' : 'text-text-3 hover:text-text-2'}`}
          title={item.flagged ? 'Unflag' : 'Flag'}
          aria-label={item.flagged ? 'Unflag' : 'Flag'}
        >
          <Flag size={15} fill={item.flagged ? 'currentColor' : 'none'} />
        </button>
      </div>

      {open && (
        <div className="flex flex-wrap items-end gap-3 border-t border-line px-3.5 py-3">
          <label className="flex flex-col gap-1 text-[10.5px] text-text-3">
            Priority
            <select
              value={item.priority}
              onChange={(e) => setPriority(item.id, e.target.value as InboxPriority)}
              className="rounded-md border border-line bg-card-2 px-2 py-1 text-[12px] text-text"
            >
              {PRIORITY_ORDER.slice().reverse().map((p) => (
                <option key={p} value={p}>
                  {PRIORITY_META[p].label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-[10.5px] text-text-3">
            Board column
            <select
              value={item.column}
              onChange={(e) => setColumn(item.id, e.target.value as InboxColumn)}
              className="rounded-md border border-line bg-card-2 px-2 py-1 text-[12px] text-text"
            >
              {COLUMNS.map((c) => (
                <option key={c.key} value={c.key}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-[10.5px] text-text-3">
            Due date
            <input
              type="date"
              value={item.due ?? ''}
              onChange={(e) => setDue(item.id, e.target.value || null)}
              className="rounded-md border border-line bg-card-2 px-2 py-1 text-[12px] text-text"
            />
          </label>
          <label className="flex min-w-[220px] flex-1 flex-col gap-1 text-[10.5px] text-text-3">
            Note to self
            <textarea
              value={item.note}
              onChange={(e) => setNote(item.id, e.target.value)}
              rows={2}
              placeholder="Add a private note…"
              className="resize-y rounded-md border border-line bg-card-2 px-2 py-1 text-[12px] text-text placeholder:text-text-3"
            />
          </label>
          {/* IB4: per-reminder notification config (channels + cadence + ≤3 reminders). */}
          <NotifyEditor item={item} />
          <div className="flex items-center gap-2">
            {item.link && (
              <Link
                to={item.link}
                className="inline-flex items-center gap-1.5 rounded-md border border-line bg-card px-2.5 py-1.5 text-[12px] text-text-2 hover:border-accent hover:text-accent-strong"
              >
                <ExternalLink size={13} /> Open in queue
              </Link>
            )}
            {item.isSelf && (
              <button
                onClick={() => deleteSelfItem(item.id)}
                className="inline-flex items-center gap-1.5 rounded-md border border-line bg-card px-2.5 py-1.5 text-[12px] text-text-2 hover:border-escalate-bd hover:text-escalate"
              >
                <Trash2 size={13} /> Delete
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function InboxTab() {
  const { items, markAllRead, markAllUnread } = useInbox()
  const [filter, setFilter] = useState<InboxFilter>('all')
  // UIC-5: the notification stream paginates (25/50/100) — never an unbounded scroll.
  const [perPage, setPerPage] = useState<PerPage>('25')
  const [page, setPage] = useState(1)
  const shown = useMemo(() => {
    // Default view hides the archived (done) column; the board/calendar still show it.
    const base = items.filter((i) => i.column !== 'done')
    if (filter === 'unread') return base.filter((i) => !i.read)
    if (filter === 'flagged') return base.filter((i) => i.flagged)
    return base
  }, [items, filter])
  const unread = items.filter((i) => !i.read && i.column !== 'done').length

  const per = Number(perPage)
  const total = shown.length
  const pages = Math.max(1, Math.ceil(total / per))
  const curPage = Math.min(page, pages) // clamp so a narrowing filter can't strand the pager
  const paged = shown.slice((curPage - 1) * per, curPage * per)
  // Reset to page 1 whenever the filter or per-page changes.
  useEffect(() => {
    setPage(1)
  }, [filter, perPage])

  const FILTERS: { key: InboxFilter; label: string; n: number }[] = [
    { key: 'all', label: 'All', n: items.filter((i) => i.column !== 'done').length },
    { key: 'unread', label: 'Unread', n: unread },
    { key: 'flagged', label: 'Flagged', n: items.filter((i) => i.flagged).length },
  ]

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1.5">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12px] transition-colors ${
                filter === f.key ? 'border-accent bg-accent-weak text-accent-strong' : 'border-line bg-card text-text-2 hover:border-line-strong'
              }`}
            >
              {f.label}
              <span className="font-mono text-[10.5px] text-text-3">{f.n}</span>
            </button>
          ))}
        </div>
        {/* IB2: mark everything read OR unread (single-item toggles live on each row's dot). */}
        <div className="flex items-center gap-1.5">
          {unread > 0 && (
            <button
              onClick={markAllRead}
              className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-card px-2.5 py-1.5 text-[12px] text-text-2 hover:border-line-strong"
            >
              <CheckCheck size={14} /> Mark all read
            </button>
          )}
          {items.some((i) => i.read && i.column !== 'done') && (
            <button
              onClick={markAllUnread}
              className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-card px-2.5 py-1.5 text-[12px] text-text-2 hover:border-line-strong"
            >
              <Circle size={14} /> Mark all unread
            </button>
          )}
        </div>
      </div>
      <div className="flex flex-col gap-2">
        {total === 0 ? (
          <Empty message={filter === 'all' ? 'Your inbox is clear. New escalations, reruns, and holds land here.' : `No ${filter} items.`} />
        ) : (
          paged.map((i) => <InboxRow key={i.id} item={i} />)
        )}
      </div>
      <Pager
        total={total}
        page={curPage}
        perPage={perPage}
        onPage={setPage}
        onPerPage={setPerPage}
        perPageOptions={PER_PAGE_25}
        noun="notifications"
      />
    </div>
  )
}

// ── BOARD tab: kanban with native drag-and-drop ────────────────────────────────
// A per-column reveal cap so a 100+-ticket column stays navigable (scale-aware, like the app's pagers)
// — the first N cards render, the rest hide behind a "Show N more" expander.
const COLUMN_PAGE = 20

function BoardCard({
  item,
  onOpen,
  onResolve,
  resolving,
}: {
  item: InboxItem
  onOpen: () => void
  onResolve: () => void
  resolving: boolean
}) {
  const { toggleFlag, comments } = useInbox()
  const src = SOURCE_META[item.source]
  const commentCount = comments[item.id]?.length ?? 0
  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('text/plain', item.id)
        e.dataTransfer.effectAllowed = 'move'
      }}
      // A plain click opens the card detail (native drag never fires click); the flag button stops it.
      onClick={onOpen}
      className="cursor-grab rounded-[10px] border border-line bg-card px-3 py-2.5 shadow-card transition-colors hover:border-line-strong active:cursor-grabbing"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1.5">
          <span className={`h-2 w-2 shrink-0 rounded-full ${src.dot}`} />
          <span className="shrink-0 text-[10px] font-medium text-text-3">{src.label}</span>
          {/* IB14: a stable, referenceable id — a ticket shows its review-queue id, a self card IB-XXXX. */}
          <span className="truncate font-mono text-[10px] text-text-3" title={item.id}>{shortItemId(item.id, item.isSelf)}</span>
        </span>
        <span className="flex shrink-0 items-center gap-1.5">
          {item.assignee && <Avatar id={item.assignee} size={17} />}
          {/* Resolve straight from the card (ticket-derived only) — confirm-gated + audited upstream. */}
          {!item.isSelf && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                onResolve()
              }}
              disabled={resolving}
              className="text-text-3 hover:text-accent-strong disabled:opacity-40"
              title="Resolve ticket"
              aria-label="Resolve ticket"
            >
              <CheckCheck size={13} />
            </button>
          )}
          <button
            onClick={(e) => {
              e.stopPropagation()
              toggleFlag(item.id)
            }}
            className={item.flagged ? 'text-escalate' : 'text-text-3 hover:text-text-2'}
            title={item.flagged ? 'Unflag' : 'Flag'}
            aria-label={item.flagged ? 'Unflag' : 'Flag'}
          >
            <Flag size={13} fill={item.flagged ? 'currentColor' : 'none'} />
          </button>
        </span>
      </div>
      <div className="mt-1 text-[12.5px] leading-snug text-text">{item.title}</div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <PriorityChip p={item.priority} />
        <DueChip due={item.due} />
        {item.runId && <span className="font-mono text-[10px] text-text-3">{item.runId}</span>}
        {commentCount > 0 && (
          <span className="inline-flex items-center gap-1 text-[10px] text-text-3">
            <MessageSquare size={11} /> {commentCount}
          </span>
        )}
      </div>
    </div>
  )
}

// A single rendered comment; its author can delete it (author == acting operator at read time).
function CommentRow({ itemId, c, canDelete }: { itemId: string; c: InboxComment; canDelete: boolean }) {
  const { deleteComment } = useInbox()
  return (
    <div className="flex gap-2.5">
      <Avatar id={c.authorId} size={22} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-[12px] font-medium text-text">{c.authorName}</span>
          <span className="text-[10.5px] text-text-3">{timeAgo(c.createdAt)}</span>
          {canDelete && (
            <button
              onClick={() => deleteComment(itemId, c.id)}
              className="ml-auto text-text-3 hover:text-escalate"
              title="Delete comment"
              aria-label="Delete comment"
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
        <CommentBody body={c.body} />
      </div>
    </div>
  )
}

// The @-mention comment composer: typing "@" opens a roster autocomplete (arrow keys + Enter/Tab to
// pick, Escape to dismiss); ⌘/Ctrl-Enter posts. Mentions are resolved from the body on submit.
function MentionComposer({ itemId }: { itemId: string }) {
  const { addComment } = useInbox()
  const [text, setText] = useState('')
  const [query, setQuery] = useState<string | null>(null) // active @-token being typed, or null
  const [hi, setHi] = useState(0) // highlighted suggestion index
  const taRef = useRef<HTMLTextAreaElement>(null)

  const matches = useMemo(() => {
    if (query === null) return []
    const q = query.toLowerCase()
    return DEMO_ACCOUNTS.filter((a) => a.id.toLowerCase().includes(q) || a.name.toLowerCase().includes(q)).slice(0, 6)
  }, [query])
  // Reset the highlight whenever the candidate token changes so it never points past the list.
  useEffect(() => {
    setHi(0)
  }, [query])

  const onChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value
    setText(val)
    const caret = e.target.selectionStart ?? val.length
    const m = val.slice(0, caret).match(/@([a-z0-9._-]*)$/i)
    setQuery(m ? m[1] : null)
  }

  const insert = (acct: (typeof DEMO_ACCOUNTS)[number]) => {
    const ta = taRef.current
    const caret = ta?.selectionStart ?? text.length
    const before = text.slice(0, caret).replace(/@([a-z0-9._-]*)$/i, `@${acct.id} `)
    const after = text.slice(caret)
    setText(before + after)
    setQuery(null)
    // Restore focus + drop the caret right after the inserted mention.
    requestAnimationFrame(() => {
      ta?.focus()
      ta?.setSelectionRange(before.length, before.length)
    })
  }

  const submit = () => {
    if (!text.trim()) return
    addComment(itemId, text)
    setText('')
    setQuery(null)
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (query !== null && matches.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setHi((h) => (h + 1) % matches.length)
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setHi((h) => (h - 1 + matches.length) % matches.length)
        return
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault()
        insert(matches[hi] ?? matches[0])
        return
      }
      if (e.key === 'Escape') {
        setQuery(null)
        return
      }
    }
    // ⌘/Ctrl-Enter posts; a plain Enter keeps adding newlines to the body.
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="relative mt-3">
      <textarea
        ref={taRef}
        value={text}
        onChange={onChange}
        onKeyDown={onKeyDown}
        rows={2}
        placeholder="Add a comment… use @ to mention a teammate"
        className="w-full resize-y rounded-md border border-line bg-card-2 px-2.5 py-1.5 text-[12px] text-text placeholder:text-text-3"
      />
      {query !== null && matches.length > 0 && (
        // Opens UPWARD (bottom-full): the composer is pinned at the modal's bottom edge, so a downward
        // menu would spill past the dialog. Above the textarea it stays inside the visible dialog.
        <div className="absolute inset-x-0 bottom-full z-10 mb-1 overflow-hidden rounded-md border border-line-strong bg-card shadow-pop">
          {matches.map((a, i) => (
            <button
              key={a.id}
              type="button"
              // mousedown (not click) so the textarea keeps focus + selection while we insert.
              onMouseDown={(e) => {
                e.preventDefault()
                insert(a)
              }}
              onMouseEnter={() => setHi(i)}
              className={`flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[12px] ${
                i === hi ? 'bg-accent-weak' : 'hover:bg-card-2'
              }`}
            >
              <Avatar id={a.id} size={18} />
              <span className="font-medium text-text">{a.name}</span>
              <span className="font-mono text-[10.5px] text-text-3">@{a.id}</span>
              <span className="ml-auto text-[10px] capitalize text-text-3">{a.role}</span>
            </button>
          ))}
        </div>
      )}
      <div className="mt-1.5 flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1 text-[10.5px] text-text-3">
          <AtSign size={11} /> Mentions are a demo seam — stored locally, not a live ping.
        </span>
        <button
          type="button"
          onClick={submit}
          disabled={!text.trim()}
          className="inline-flex items-center gap-1.5 rounded-md bg-accent px-2.5 py-1 text-[12px] font-medium text-white disabled:opacity-40"
        >
          <Send size={12} /> Comment
        </button>
      </div>
    </div>
  )
}

// The board card detail (UIC-14): the referenceable id, an editable description, assignment + status
// wired to the roster, and the @-mention comment thread. A large, user-RESIZABLE dialog (a kanban
// column is far too narrow for a discussion), split into a fixed meta/description top region and a
// dominant, scrollable comments region with the composer pinned at the bottom.
function BoardCardDetail({
  item,
  onClose,
  onResolve,
  resolving,
}: {
  item: InboxItem
  onClose: () => void
  onResolve: () => void
  resolving: boolean
}) {
  const { setNote, setAssignee, setColumn, setPriority, setDue, comments } = useInbox()
  const { actor } = useRole()
  const src = SOURCE_META[item.source]
  const list = comments[item.id] ?? []
  // Portal to <body> so the fixed backdrop is VIEWPORT-relative — the page's `.pg-fade` transition
  // wrapper carries a transform, which otherwise traps `fixed` and drops the dialog low (the "too low"
  // complaint). At the body it centres in the viewport, sitting higher regardless of board scroll.
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        // Generous default size + a native drag grip (CSS `resize: both`) at the bottom-right corner,
        // so an operator can grow the dialog to give the thread even more room. Theme-aware via tokens.
        className="flex flex-col overflow-hidden rounded-2xl border border-line bg-card shadow-pop"
        style={{
          resize: 'both',
          width: 'min(880px, 95vw)',
          height: 'min(760px, 88vh)',
          minWidth: 720,
          minHeight: 520,
          maxWidth: '96vw',
          maxHeight: '92vh',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header — id + title + a Resolve action (ticket-derived only) beside the close button. */}
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-3.5">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className={`rounded-md border px-1.5 py-px text-[10px] font-medium ${src.badge}`}>{src.label}</span>
              <span className="font-mono text-[11px] text-text-3" title={item.id}>{shortItemId(item.id, item.isSelf)}</span>
            </div>
            <h2 className="mt-1.5 text-[15px] font-medium leading-snug text-text">{item.title}</h2>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-text-3">
              {item.runId && <span className="font-mono">{item.runId}</span>}
              {item.sampleId && <span className="font-mono">· {item.sampleId}</span>}
              <span>· {timeAgo(item.createdAt)}</span>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {/* A neutral outlined Resolve (matching the review queue's own resolve styling) — the
                backend close is confirm-gated + audited by the caller. */}
            {!item.isSelf && (
              <button
                onClick={onResolve}
                disabled={resolving}
                className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-2.5 py-1.5 text-[12px] font-medium text-text-2 hover:border-accent hover:text-accent-strong disabled:opacity-50"
                title="Resolve this ticket in the review queue"
              >
                <CheckCheck size={14} /> Resolve
              </button>
            )}
            <button
              onClick={onClose}
              className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-text-2 hover:bg-page"
              aria-label="Close"
            >
              <X size={17} />
            </button>
          </div>
        </div>

        {/* Meta + description — the fixed top region; kept compact so comments get the vertical space. */}
        <div className="border-b border-line px-5 py-4">
          {/* Assignment + status wired to the user/review system (UIC-14). */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <label className="flex flex-col gap-1 text-[10.5px] text-text-3">
              Assignee
              <select
                value={item.assignee ?? ''}
                onChange={(e) => setAssignee(item.id, e.target.value || null)}
                className="rounded-md border border-line bg-card-2 px-2 py-1.5 text-[12px] text-text"
              >
                <option value="">Unassigned</option>
                {DEMO_ACCOUNTS.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} · {a.role}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-[10.5px] text-text-3">
              Status
              <select
                value={item.column}
                onChange={(e) => setColumn(item.id, e.target.value as InboxColumn)}
                className="rounded-md border border-line bg-card-2 px-2 py-1.5 text-[12px] text-text"
              >
                {COLUMNS.map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-[10.5px] text-text-3">
              Priority
              <select
                value={item.priority}
                onChange={(e) => setPriority(item.id, e.target.value as InboxPriority)}
                className="rounded-md border border-line bg-card-2 px-2 py-1.5 text-[12px] text-text"
              >
                {PRIORITY_ORDER.slice().reverse().map((p) => (
                  <option key={p} value={p}>
                    {PRIORITY_META[p].label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-[10.5px] text-text-3">
              Due date
              <input
                type="date"
                value={item.due ?? ''}
                onChange={(e) => setDue(item.id, e.target.value || null)}
                className="rounded-md border border-line bg-card-2 px-2 py-1.5 text-[12px] text-text"
              />
            </label>
          </div>

          {/* IB14: a body/description — the card's working notes (autosaved to your overlay). */}
          <label className="mt-3 flex flex-col gap-1 text-[10.5px] text-text-3">
            Description
            <textarea
              value={item.note}
              onChange={(e) => setNote(item.id, e.target.value)}
              rows={2}
              placeholder="What's the plan for this card…"
              className="resize-y rounded-md border border-line bg-card-2 px-2.5 py-1.5 text-[12px] text-text placeholder:text-text-3"
            />
          </label>
        </div>

        {/* Comments — the dominant, scrollable region; the composer stays pinned below the thread. */}
        <div className="flex min-h-0 flex-1 flex-col px-5 py-4">
          <div className="mb-2.5 flex items-center gap-1.5 text-[12px] font-semibold text-text">
            <MessageSquare size={14} /> Comments
            <span className="font-mono text-[11px] text-text-3">{list.length}</span>
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
            {list.length === 0 ? (
              <p className="text-[12px] text-text-3">No comments yet — @-mention a teammate to loop them in.</p>
            ) : (
              list.map((c) => <CommentRow key={c.id} itemId={item.id} c={c} canDelete={c.authorId === actor.id} />)
            )}
          </div>
          <MentionComposer itemId={item.id} />
        </div>
      </div>
    </div>,
    document.body,
  )
}

function BoardTab() {
  const { items, setColumn, resolveTicket } = useInbox()
  const confirm = useConfirm()
  const { toast } = useToast()
  const [dragOver, setDragOver] = useState<InboxColumn | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const [resolving, setResolving] = useState(false)
  // Per-column reveal counts — each column shows COLUMN_PAGE cards, then reveals more on demand.
  const [shownPer, setShownPer] = useState<Record<InboxColumn, number>>({
    inbox: COLUMN_PAGE,
    todo: COLUMN_PAGE,
    doing: COLUMN_PAGE,
    done: COLUMN_PAGE,
  })
  // Resolve the open card from live items (not a captured copy) so edits reflect instantly.
  const openItem = openId ? (items.find((i) => i.id === openId) ?? null) : null
  const byColumn = (c: InboxColumn) =>
    items
      .filter((i) => i.column === c)
      .sort((a, b) => PRIORITY_META[b.priority].weight - PRIORITY_META[a.priority].weight)

  // Close a ticket-derived card from the board. A state-changing backend write, so it's confirm-gated
  // (naming that it resolves + is audited) and resolves against the item's REAL ticket id.
  const handleResolve = async (item: InboxItem) => {
    if (item.isSelf || resolving) return
    const ok = await confirm({
      title: 'Resolve this ticket?',
      body: 'Closes it in the review queue and drops it from your board. Recorded in the audit log.',
      confirmLabel: 'Resolve',
    })
    if (!ok) return
    setResolving(true)
    try {
      await resolveTicket(item.id)
      setOpenId((cur) => (cur === item.id ? null : cur))
      toast('Ticket resolved.', 'success')
    } catch (e) {
      toast(String(e), 'error')
    } finally {
      setResolving(false)
    }
  }
  const showMore = (c: InboxColumn) => setShownPer((p) => ({ ...p, [c]: p[c] + COLUMN_PAGE }))
  const collapse = (c: InboxColumn) => setShownPer((p) => ({ ...p, [c]: COLUMN_PAGE }))

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {COLUMNS.map((col) => {
        const cards = byColumn(col.key)
        const limit = shownPer[col.key]
        const visible = cards.slice(0, limit)
        const hidden = cards.length - visible.length
        return (
          <div
            key={col.key}
            onDragOver={(e) => {
              e.preventDefault()
              setDragOver(col.key)
            }}
            onDragLeave={() => setDragOver((c) => (c === col.key ? null : c))}
            onDrop={(e) => {
              e.preventDefault()
              const id = e.dataTransfer.getData('text/plain')
              if (id) setColumn(id, col.key)
              setDragOver(null)
            }}
            className={`flex min-h-[160px] flex-col gap-2 rounded-[12px] border p-2.5 transition-colors ${
              dragOver === col.key ? 'border-accent bg-accent-weak/40' : 'border-line bg-card-2/50'
            }`}
          >
            <div className="flex items-center justify-between px-1">
              <span className="text-[12px] font-semibold text-text">{col.label}</span>
              <span className="font-mono text-[11px] text-text-3">{cards.length}</span>
            </div>
            {cards.length === 0 ? (
              <div className="grid flex-1 place-items-center rounded-[9px] border border-dashed border-line px-2 py-6 text-center text-[11px] text-text-3">
                {col.hint}
              </div>
            ) : (
              <>
                {visible.map((i) => (
                  <BoardCard
                    key={i.id}
                    item={i}
                    onOpen={() => setOpenId(i.id)}
                    onResolve={() => void handleResolve(i)}
                    resolving={resolving}
                  />
                ))}
                {/* Scale-aware reveal — the cap keeps a long column navigable; expand/collapse on demand. */}
                {hidden > 0 ? (
                  <button
                    onClick={() => showMore(col.key)}
                    className="mt-0.5 rounded-[9px] border border-dashed border-line px-2 py-1.5 text-[11px] text-text-2 transition-colors hover:border-line-strong hover:text-text"
                  >
                    Show {Math.min(hidden, COLUMN_PAGE)} more
                    <span className="ml-1 font-mono text-[10.5px] text-text-3">· {hidden} hidden</span>
                  </button>
                ) : (
                  limit > COLUMN_PAGE &&
                  cards.length > COLUMN_PAGE && (
                    <button
                      onClick={() => collapse(col.key)}
                      className="mt-0.5 rounded-[9px] border border-dashed border-line px-2 py-1.5 text-[11px] text-text-2 transition-colors hover:border-line-strong hover:text-text"
                    >
                      Show less
                    </button>
                  )
                )}
              </>
            )}
          </div>
        )
      })}
      {openItem && (
        <BoardCardDetail
          item={openItem}
          onClose={() => setOpenId(null)}
          onResolve={() => void handleResolve(openItem)}
          resolving={resolving}
        />
      )}
    </div>
  )
}

// ── CALENDAR tab: month grid of due dates ──────────────────────────────────────
const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']

function CalendarTab() {
  const { items, addSelfItem } = useInbox()
  const { toast } = useToast()
  const today = todayYmd()
  const [cursor, setCursor] = useState(() => {
    const d = new Date()
    return { year: d.getFullYear(), month: d.getMonth() } // month 0-11
  })
  const [selected, setSelected] = useState<string>(today)
  const [newTitle, setNewTitle] = useState('')

  const scheduled = useMemo(() => items.filter((i) => i.due), [items])
  const byDay = useMemo(() => {
    const m = new Map<string, InboxItem[]>()
    for (const i of scheduled) {
      if (!i.due) continue
      const arr = m.get(i.due) ?? []
      arr.push(i)
      m.set(i.due, arr)
    }
    return m
  }, [scheduled])

  const first = new Date(cursor.year, cursor.month, 1)
  const monthLabel = first.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
  const startPad = first.getDay()
  const daysInMonth = new Date(cursor.year, cursor.month + 1, 0).getDate()
  const cells: (string | null)[] = [
    ...Array.from({ length: startPad }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => localYmd(new Date(cursor.year, cursor.month, i + 1))),
  ]
  const step = (delta: number) => {
    setCursor((c) => {
      const m = c.month + delta
      return { year: c.year + Math.floor(m / 12), month: ((m % 12) + 12) % 12 }
    })
  }
  const selectedItems = byDay.get(selected) ?? []

  return (
    <div>
      {/* IB1: calendar connectors live UNDER the Calendar tab (they belong to this view, not Notes).
          Labelled phase-2 seams — a toast, not a real OAuth flow. */}
      <div className="mb-4 flex flex-wrap items-center gap-3 rounded-[12px] border border-line bg-card px-4 py-3">
        <div className="mr-auto min-w-0">
          <div className="text-[12.5px] font-semibold text-text">Calendar sync</div>
          <p className="text-[11px] text-text-3">
            Push reminders to your calendar. Connectors are a production seam — not yet wired.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {[
            { k: 'gmail', label: 'Google Calendar' },
            { k: 'outlook', label: 'Outlook Calendar' },
          ].map((c) => (
            <button
              key={c.k}
              onClick={() => toast(`${c.label} connector isn't wired in this build (a labelled seam).`, 'info')}
              className="inline-flex items-center gap-2 rounded-md border border-line-strong bg-card-2 px-2.5 py-2 text-[12px] text-text-2 hover:border-accent hover:text-accent-strong"
            >
              <Mail size={14} />
              Connect {c.label}
              <span className="ml-0.5 rounded-full border border-line bg-card px-1.5 py-px text-[9.5px] text-text-3">
                phase-2
              </span>
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="rounded-[14px] border border-line bg-card p-4">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-[14px] font-semibold text-text">{monthLabel}</span>
          <div className="flex items-center gap-1">
            <button onClick={() => step(-1)} className="grid h-7 w-7 place-items-center rounded-md border border-line text-text-2 hover:border-line-strong" aria-label="Previous month">
              <ChevronLeft size={15} />
            </button>
            <button
              onClick={() => {
                const d = new Date()
                setCursor({ year: d.getFullYear(), month: d.getMonth() })
                setSelected(today)
              }}
              className="rounded-md border border-line px-2 py-1 text-[11px] text-text-2 hover:border-line-strong"
            >
              Today
            </button>
            <button onClick={() => step(1)} className="grid h-7 w-7 place-items-center rounded-md border border-line text-text-2 hover:border-line-strong" aria-label="Next month">
              <ChevronRight size={15} />
            </button>
          </div>
        </div>
        <div className="grid grid-cols-7 gap-1">
          {WEEKDAYS.map((w) => (
            <div key={w} className="pb-1 text-center text-[10.5px] font-medium text-text-3">
              {w}
            </div>
          ))}
          {cells.map((day, idx) => {
            if (!day) return <div key={`pad-${idx}`} />
            const dayItems = byDay.get(day) ?? []
            const hasOverdue = day < today && dayItems.length > 0
            const isToday = day === today
            const isSel = day === selected
            return (
              <button
                key={day}
                onClick={() => setSelected(day)}
                className={`flex min-h-[52px] flex-col rounded-[8px] border p-1 text-left transition-colors ${
                  isSel ? 'border-accent bg-accent-weak' : 'border-line bg-card-2/40 hover:border-line-strong'
                }`}
              >
                <span className={`text-[11px] ${isToday ? 'font-bold text-accent-strong' : 'text-text-2'}`}>
                  {Number(day.slice(-2))}
                </span>
                {dayItems.length > 0 && (
                  <span className="mt-auto flex items-center gap-1">
                    <span className={`h-1.5 w-1.5 rounded-full ${hasOverdue ? 'bg-escalate' : 'bg-accent'}`} />
                    <span className="font-mono text-[9.5px] text-text-3">{dayItems.length}</span>
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <div className="rounded-[14px] border border-line bg-card p-4">
          <div className="text-[12.5px] font-semibold text-text">
            {new Date(`${selected}T00:00:00`).toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })}
          </div>
          <div className="mt-2 flex flex-col gap-2">
            {selectedItems.length === 0 ? (
              <p className="text-[12px] text-text-3">Nothing scheduled.</p>
            ) : (
              selectedItems.map((i) => (
                <div key={i.id} className="rounded-[9px] border border-line bg-card-2 px-2.5 py-2">
                  <div className="flex items-center gap-1.5">
                    <span className={`h-2 w-2 rounded-full ${SOURCE_META[i.source].dot}`} />
                    <span className="text-[10px] font-medium text-text-3">{SOURCE_META[i.source].label}</span>
                    <PriorityChip p={i.priority} />
                  </div>
                  <div className="mt-1 text-[12px] text-text">{i.title}</div>
                </div>
              ))
            )}
          </div>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            addSelfItem(newTitle, { due: selected })
            setNewTitle('')
          }}
          className="rounded-[14px] border border-line bg-card p-4"
        >
          <div className="text-[12.5px] font-semibold text-text">Add a reminder</div>
          {/* IB3: the date is implied by the selected day (shown here), not repeated on the button. */}
          <p className="mb-2 mt-0.5 text-[11px] text-text-3">
            Scheduled for{' '}
            <span className="font-medium text-text-2">
              {new Date(`${selected}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
            </span>
            .
          </p>
          <input
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="Reminder title…"
            className="w-full rounded-md border border-line bg-card-2 px-2.5 py-1.5 text-[12.5px] text-text placeholder:text-text-3"
          />
          <button
            type="submit"
            disabled={!newTitle.trim()}
            className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-[12px] font-medium text-white disabled:opacity-40"
          >
            <Plus size={14} /> Add reminder
          </button>
        </form>
      </div>
      </div>
    </div>
  )
}

// ── NOTES tab: self reminders + notes to self, with edit-gating + folders ───────
const UNFILED = '__unfiled__'

// An absolute created-date for a note header (4a). Tolerant of a bad timestamp (house rule: a
// boundary never crashes) — falls back to the raw yyyy-mm-dd, mirroring timeAgo's own fallback.
function fmtDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function NotesTab() {
  const { items, folders, addSelfItem, updateSelfItem, deleteSelfItem, setFolder, addFolder, deleteFolder } =
    useInbox()
  const confirm = useConfirm()
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [composerFolder, setComposerFolder] = useState('')
  const [newFolder, setNewFolder] = useState('')
  // IB5: editing is explicit — a note is read-only until you click Edit, gating accidental changes.
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editBody, setEditBody] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [folderFilter, setFolderFilter] = useState<string>('all') // 'all' | UNFILED | <folder>

  // Everything the operator has authored, plus any ticket they've annotated.
  const noted = useMemo(() => items.filter((i) => i.isSelf || i.note.trim()), [items])
  const shown = useMemo(() => {
    if (folderFilter === 'all') return noted
    if (folderFilter === UNFILED) return noted.filter((i) => !i.folder)
    return noted.filter((i) => i.folder === folderFilter)
  }, [noted, folderFilter])

  const startEdit = (i: InboxItem) => {
    setEditingId(i.id)
    setEditTitle(i.title)
    setEditBody(i.note)
  }
  const cancelEdit = () => setEditingId(null)
  const saveEdit = (i: InboxItem) => {
    // A ticket annotation has no editable title (the title is the ticket's); only its note changes.
    updateSelfItem(i.id, i.isSelf ? { title: editTitle, note: editBody } : { note: editBody })
    setEditingId(null)
  }

  const toggleSel = (id: string) =>
    setSelected((p) => {
      const n = new Set(p)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  const selfSelected = [...selected].filter((id) => noted.find((i) => i.id === id)?.isSelf)
  const deleteSelected = async () => {
    if (!selfSelected.length) return
    const ok = await confirm({
      title: `Delete ${selfSelected.length} note${selfSelected.length === 1 ? '' : 's'}?`,
      body: "Your own reminders are removed. Ticket annotations aren't deleted here.",
      confirmLabel: 'Delete',
      tone: 'danger',
    })
    if (!ok) return
    selfSelected.forEach(deleteSelfItem)
    setSelected(new Set())
  }

  const folderOpts = [{ v: '', label: 'Unfiled' }, ...folders.map((f) => ({ v: f, label: f }))]
  // The folder sidebar's nav/filter list — All + Unfiled pseudo-entries, then each real folder
  // (deletable). Merges the old right-side filter chips + left-side folder manager into one column.
  const folderNav: { v: string; label: string; count: number; deletable: boolean }[] = [
    { v: 'all', label: 'All notes', count: noted.length, deletable: false },
    { v: UNFILED, label: 'Unfiled', count: noted.filter((i) => !i.folder).length, deletable: false },
    ...folders.map((f) => ({ v: f, label: f, count: noted.filter((i) => i.folder === f).length, deletable: true })),
  ]
  const filterLabel = folderNav.find((e) => e.v === folderFilter)?.label ?? 'All notes'

  return (
    // 4b: a NARROW folders sidebar + a dominant editing area (the composer + notes list get the room).
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
      {/* LEFT: a compact folders sidebar — new-folder at the TOP (4c), then the filter/nav list. */}
      <aside className="h-fit rounded-[14px] border border-line bg-card p-3.5">
        <div className="mb-2.5 text-[12.5px] font-semibold text-text">Folders</div>
        {/* 4c: create a folder ABOVE the folder list + the note view (was buried below the list). */}
        <form
          onSubmit={(e) => {
            e.preventDefault()
            addFolder(newFolder)
            setNewFolder('')
          }}
          className="mb-3 flex items-center gap-1.5"
        >
          <input
            value={newFolder}
            onChange={(e) => setNewFolder(e.target.value)}
            placeholder="New folder…"
            className="min-w-0 flex-1 rounded-md border border-line bg-card-2 px-2 py-1.5 text-[12px] text-text placeholder:text-text-3"
          />
          <button
            type="submit"
            disabled={!newFolder.trim()}
            className="inline-flex shrink-0 items-center gap-1 rounded-md border border-line-strong bg-card px-2 py-1.5 text-[12px] text-text-2 hover:border-accent hover:text-accent-strong disabled:opacity-40"
            aria-label="Add folder"
          >
            <FolderPlus size={13} />
          </button>
        </form>
        {/* IB8: the folder filter/nav — click to filter; each real folder carries a delete affordance. */}
        <div className="flex flex-col gap-0.5">
          {folderNav.map((e) => (
            <div
              key={e.v}
              className={`flex items-center gap-1 rounded-md border transition-colors ${
                folderFilter === e.v ? 'border-accent bg-accent-weak' : 'border-transparent hover:bg-card-2'
              }`}
            >
              <button
                onClick={() => setFolderFilter(e.v)}
                className={`flex min-w-0 flex-1 items-center gap-1.5 px-2 py-1.5 text-left text-[12px] ${
                  folderFilter === e.v ? 'font-medium text-accent-strong' : 'text-text-2'
                }`}
              >
                <Folder size={12} className="shrink-0 text-text-3" />
                <span className="min-w-0 flex-1 truncate">{e.label}</span>
                <span className="font-mono text-[10.5px] text-text-3">{e.count}</span>
              </button>
              {e.deletable && (
                <button
                  onClick={async () => {
                    const ok = await confirm({
                      title: `Delete folder "${e.label}"?`,
                      body: 'Notes in it are kept and moved to Unfiled.',
                      confirmLabel: 'Delete folder',
                    })
                    if (ok) {
                      deleteFolder(e.label)
                      // Don't strand the list on a filter that no longer exists.
                      setFolderFilter((f) => (f === e.label ? 'all' : f))
                    }
                  }}
                  className="shrink-0 px-1.5 text-text-3 hover:text-escalate"
                  aria-label={`Delete folder ${e.label}`}
                >
                  <X size={12} />
                </button>
              )}
            </div>
          ))}
        </div>
      </aside>

      {/* RIGHT: the dominant editing area — composer + notes list. */}
      <div className="flex min-w-0 flex-col gap-3">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            addSelfItem(title, { note: body, folder: composerFolder || null })
            setTitle('')
            setBody('')
          }}
          className="rounded-[14px] border border-line bg-card p-4"
        >
          <div className="text-[13px] font-semibold text-text">New note to self</div>
          <p className="mb-3 mt-0.5 text-[11.5px] text-text-3">
            A private reminder — lands in your inbox and board, never on the gate.
          </p>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title…"
            className="w-full rounded-md border border-line bg-card-2 px-2.5 py-1.5 text-[13px] text-text placeholder:text-text-3"
          />
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={5}
            placeholder="Details (optional)…"
            className="mt-2 w-full resize-y rounded-md border border-line bg-card-2 px-2.5 py-1.5 text-[12.5px] text-text placeholder:text-text-3"
          />
          <div className="mt-2 flex items-center gap-2">
            <select
              value={composerFolder}
              onChange={(e) => setComposerFolder(e.target.value)}
              className="rounded-md border border-line bg-card-2 px-2 py-1.5 text-[12px] text-text-2"
              aria-label="File note under folder"
            >
              {folderOpts.map((o) => (
                <option key={o.v} value={o.v}>
                  {o.label}
                </option>
              ))}
            </select>
            <button
              type="submit"
              disabled={!title.trim()}
              className="ml-auto inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-[12.5px] font-medium text-white disabled:opacity-40"
            >
              <Plus size={15} /> Add note
            </button>
          </div>
        </form>

        {/* Active-filter label + the mass-delete for the checkbox selection (self notes only, IB7). */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-[11.5px] text-text-3">
            {filterLabel} · <span className="font-mono">{shown.length}</span>
          </span>
          {selfSelected.length > 0 && (
            <button
              onClick={() => void deleteSelected()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-escalate-bd bg-escalate-bg px-2.5 py-1.5 text-[12px] font-medium text-escalate-fg hover:brightness-95"
            >
              <Trash2 size={13} /> Delete {selfSelected.length}
            </button>
          )}
        </div>

        <div className="flex flex-col gap-2.5">
          {shown.length === 0 ? (
            <Empty message="No notes here. Jot a reminder to yourself in the composer above." />
          ) : (
            shown.map((i) => {
              const editing = editingId === i.id
              return (
                <div key={i.id} className="rounded-[11px] border border-line bg-card px-3.5 py-3">
                  <div className="flex items-start gap-2.5">
                    {i.isSelf && (
                      <input
                        type="checkbox"
                        className="mt-1 h-3.5 w-3.5 shrink-0 accent-accent"
                        aria-label={`Select ${i.title}`}
                        checked={selected.has(i.id)}
                        onChange={() => toggleSel(i.id)}
                      />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className={`h-2 w-2 shrink-0 rounded-full ${SOURCE_META[i.source].dot}`} />
                        {editing && i.isSelf ? (
                          <input
                            value={editTitle}
                            onChange={(e) => setEditTitle(e.target.value)}
                            className="min-w-0 flex-1 rounded border border-line bg-card-2 px-1.5 py-0.5 text-[12.5px] font-medium text-text"
                          />
                        ) : (
                          <Truncate text={i.title} className="min-w-0 flex-1 text-[12.5px] font-medium text-text" />
                        )}
                        {i.folder && (
                          <span className="inline-flex items-center gap-1 rounded-full border border-line bg-card-2 px-1.5 py-px text-[10px] text-text-3">
                            <Folder size={9} /> {i.folder}
                          </span>
                        )}
                      </div>
                      {/* IB6/4a: the absolute created DATE (in the note header), plus the relative
                          edited timestamp when present. */}
                      <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[10px] text-text-3">
                        {i.runId && <span className="font-mono">{i.runId}</span>}
                        <span className="inline-flex items-center gap-1">
                          <CalendarDays size={10} /> Created {fmtDate(i.createdAt)}
                        </span>
                        {i.updatedAt && <span>· edited {timeAgo(i.updatedAt)}</span>}
                      </div>

                      {editing ? (
                        <>
                          <textarea
                            value={editBody}
                            onChange={(e) => setEditBody(e.target.value)}
                            rows={3}
                            placeholder="Add a note…"
                            className="mt-2 w-full resize-y rounded-md border border-line bg-card-2 px-2.5 py-1.5 text-[12px] text-text placeholder:text-text-3"
                          />
                          <div className="mt-2 flex flex-wrap items-center gap-2">
                            <button
                              onClick={() => saveEdit(i)}
                              className="inline-flex items-center gap-1.5 rounded-md bg-accent px-2.5 py-1 text-[12px] font-medium text-white"
                            >
                              <Check size={13} /> Save
                            </button>
                            <button
                              onClick={cancelEdit}
                              className="rounded-md border border-line px-2.5 py-1 text-[12px] text-text-2 hover:border-line-strong"
                            >
                              Cancel
                            </button>
                            {/* IB7: delete lives inside edit, gating accidental deletion. */}
                            {i.isSelf && (
                              <button
                                onClick={async () => {
                                  const ok = await confirm({
                                    title: 'Delete this note?',
                                    body: 'Your reminder is removed.',
                                    confirmLabel: 'Delete',
                                    tone: 'danger',
                                  })
                                  if (ok) {
                                    deleteSelfItem(i.id)
                                    setEditingId(null)
                                  }
                                }}
                                className="ml-auto inline-flex items-center gap-1.5 text-[12px] text-text-3 hover:text-escalate"
                              >
                                <Trash2 size={13} /> Delete
                              </button>
                            )}
                          </div>
                        </>
                      ) : (
                        <>
                          {i.note.trim() ? (
                            <p className="mt-1.5 whitespace-pre-wrap text-[12px] leading-snug text-text-2">{i.note}</p>
                          ) : (
                            <p className="mt-1.5 text-[12px] italic text-text-3">No details.</p>
                          )}
                          <div className="mt-2 flex flex-wrap items-center gap-2">
                            {/* IB5: edit gate. */}
                            <button
                              onClick={() => startEdit(i)}
                              className="inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1 text-[12px] text-text-2 hover:border-accent hover:text-accent-strong"
                            >
                              <Pencil size={12} /> Edit
                            </button>
                            {/* IB8: move to a folder (any item). */}
                            <select
                              value={i.folder ?? ''}
                              onChange={(e) => setFolder(i.id, e.target.value || null)}
                              className="rounded-md border border-line bg-card-2 px-2 py-1 text-[11.5px] text-text-2"
                              aria-label="Move to folder"
                            >
                              {folderOpts.map((o) => (
                                <option key={o.v} value={o.v}>
                                  {o.v === '' ? 'Unfiled' : `📁 ${o.label}`}
                                </option>
                              ))}
                            </select>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}

// ── page ───────────────────────────────────────────────────────────────────────
export function Inbox() {
  const { items, unreadCount, loading, error, refresh } = useInbox()
  const [tab, setTab] = useState<Tab>('inbox')
  const flagged = items.filter((i) => i.flagged).length
  const overdue = items.filter((i) => dueStatus(i.due) === 'overdue').length
  const done = items.filter((i) => i.column === 'done').length

  const TAB_ICON: Record<Tab, typeof InboxIcon> = {
    inbox: InboxIcon,
    board: LayoutGrid,
    calendar: CalendarDays,
    notes: StickyNote,
  }

  return (
    <div className="mx-auto max-w-[1080px]">
      <PageHeader
        title="Inbox"
        actions={
          <button
            onClick={() => refresh()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-card px-2.5 py-1.5 text-[12.5px] text-text-2 hover:border-line-strong"
          >
            <RotateCw size={14} /> Refresh
          </button>
        }
      />

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Unread', value: unreadCount, tone: 'text-accent-strong' },
          { label: 'Flagged', value: flagged, tone: 'text-escalate' },
          { label: 'Overdue', value: overdue, tone: overdue > 0 ? 'text-escalate' : 'text-text' },
          { label: 'Done', value: done, tone: 'text-proceed' },
        ].map((k) => (
          <div key={k.label} className="rounded-[12px] border border-line bg-card px-4 py-3">
            <div className={`text-[22px] font-semibold tabular-nums ${k.tone}`}>{k.value}</div>
            <div className="text-[11.5px] text-text-3">{k.label}</div>
          </div>
        ))}
      </div>

      <div className="mb-4">
        <SegmentedControl<Tab>
          options={TABS.map((t) => {
            const Icon = TAB_ICON[t.value]
            return {
              value: t.value,
              label: (
                <span className="inline-flex items-center gap-1.5">
                  <Icon size={14} />
                  {t.label}
                  {t.value === 'inbox' && unreadCount > 0 && (
                    <span className="grid h-[16px] min-w-[16px] place-items-center rounded-full bg-escalate px-1 font-mono text-[9.5px] font-semibold text-white">
                      {unreadCount}
                    </span>
                  )}
                </span>
              ),
            }
          })}
          value={tab}
          onChange={setTab}
        />
      </div>

      {error ? (
        <ErrorBox message={error} onRetry={() => refresh()} />
      ) : loading ? (
        <Loading />
      ) : (
        <>
          {tab === 'inbox' && <InboxTab />}
          {tab === 'board' && <BoardTab />}
          {tab === 'calendar' && <CalendarTab />}
          {tab === 'notes' && <NotesTab />}
        </>
      )}
    </div>
  )
}
