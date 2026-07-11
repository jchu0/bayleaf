import { Bell, CheckCheck, Flag } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { DEMO_ACCOUNTS } from '../auth'
import { useInbox } from '../context/InboxContext'
import { initials, SOURCE_META, timeAgo } from '../inbox'

// A tiny assignee chip so the quick-glance surface shows who owns an item (IB14 / UIC-14 assignment).
function AssigneeChip({ id }: { id: string }) {
  const name = DEMO_ACCOUNTS.find((a) => a.id === id)?.name ?? id
  return (
    <span
      className="mt-0.5 grid h-[16px] w-[16px] shrink-0 place-items-center rounded-full bg-accent-weak text-[7.5px] font-semibold text-accent-strong"
      title={`Assigned to ${name}`}
    >
      {initials(name)}
    </span>
  )
}

// The top-bar bell — a QUICK-GLANCE triage surface, deliberately distinct from the full /inbox
// workspace (the maintainer's complaint was that a bare scrolling list loses people). It shows the
// most recent live items (unread first), lets you flag or mark-read without leaving the page, and
// hands off to the workspace for organizing. Count + items come from the shared InboxContext, so
// the state you set here is the same state waiting for you in the Inbox — page changes don't lose it.
const MAX_ROWS = 6

export function NotificationBell() {
  const { items, unreadCount, markRead, toggleFlag, markAllRead } = useInbox()
  const [open, setOpen] = useState(false)
  // Unread first, then newest; the workspace holds the exhaustive, organizable view.
  const recent = [...items]
    .filter((i) => i.column !== 'done')
    .sort((a, b) => (a.read === b.read ? 0 : a.read ? 1 : -1))
    .slice(0, MAX_ROWS)

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative grid h-8 w-8 place-items-center rounded-lg text-text-2 hover:bg-card-2"
        aria-label={`Notifications${unreadCount ? `, ${unreadCount} unread` : ''}`}
      >
        <Bell size={17} strokeWidth={1.8} />
        {unreadCount > 0 && (
          <span className="absolute right-0 top-0.5 grid h-[15px] min-w-[15px] place-items-center rounded-full bg-escalate px-0.5 text-[9px] font-semibold text-white">
            {unreadCount}
          </span>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full z-40 mt-1.5 w-[360px] overflow-hidden rounded-xl border border-line-strong bg-card shadow-pop">
            <div className="flex items-center justify-between border-b border-line px-3.5 py-2.5">
              <span className="text-[13px] font-semibold text-text">
                Notifications{unreadCount > 0 && <span className="ml-1.5 font-mono text-[11px] text-text-3">{unreadCount} unread</span>}
              </span>
              {unreadCount > 0 && (
                <button
                  onClick={markAllRead}
                  className="inline-flex items-center gap-1 text-[11.5px] text-text-2 hover:text-accent-strong"
                >
                  <CheckCheck size={13} /> Mark all read
                </button>
              )}
            </div>

            <div className="max-h-[340px] overflow-y-auto">
              {recent.length === 0 ? (
                <div className="px-4 py-8 text-center text-[12.5px] text-text-3">You're all caught up.</div>
              ) : (
                recent.map((i) => (
                  <div
                    key={i.id}
                    className={`flex items-start gap-2.5 border-b border-line px-3.5 py-2.5 last:border-b-0 ${i.read ? '' : 'bg-accent-weak/40'}`}
                  >
                    <button
                      onClick={() => markRead(i.id, !i.read)}
                      className="mt-1 shrink-0"
                      title={i.read ? 'Mark unread' : 'Mark read'}
                      aria-label={i.read ? 'Mark unread' : 'Mark read'}
                    >
                      <span className={`block h-2 w-2 rounded-full ${i.read ? 'bg-line-strong' : SOURCE_META[i.source].dot}`} />
                    </button>
                    <div className="min-w-0 flex-1">
                      <div className={`text-[12.5px] leading-snug ${i.read ? 'text-text-2' : 'font-medium text-text'}`}>
                        {i.title}
                      </div>
                      <div className="mt-0.5 flex items-center gap-2 text-[10.5px] text-text-3">
                        <span>{SOURCE_META[i.source].label}</span>
                        {i.runId && <span className="font-mono">· {i.runId}</span>}
                        <span>· {timeAgo(i.createdAt)}</span>
                      </div>
                    </div>
                    {i.assignee && <AssigneeChip id={i.assignee} />}
                    <button
                      onClick={() => toggleFlag(i.id)}
                      className={`mt-0.5 shrink-0 ${i.flagged ? 'text-escalate' : 'text-text-3 hover:text-text-2'}`}
                      title={i.flagged ? 'Unflag' : 'Flag'}
                      aria-label={i.flagged ? 'Unflag' : 'Flag'}
                    >
                      <Flag size={13} fill={i.flagged ? 'currentColor' : 'none'} />
                    </button>
                  </div>
                ))
              )}
            </div>

            <Link
              to="/inbox"
              onClick={() => setOpen(false)}
              className="flex items-center justify-between border-t border-line bg-card px-3.5 py-2.5 hover:bg-card-2"
            >
              <span className="text-[12px] font-semibold text-accent-strong">Open inbox</span>
              <span className="text-[11px] text-text-3">{items.filter((i) => i.column !== 'done').length} items →</span>
            </Link>
          </div>
        </>
      )}
    </div>
  )
}
