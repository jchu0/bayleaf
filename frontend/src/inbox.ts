import type { InboxColumn, InboxPriority, InboxSource } from './context/InboxContext'

// Shared inbox visual tokens — kept out of the .tsx components so a fast-refresh edit to a
// component never churns these, and so the bell dropdown and the /inbox workspace read identically.
// Derived-ticket sources reuse the verdict palette (escalate/rerun/hold) an operator already knows;
// self-authored reminders get the neutral accent.

export const SOURCE_META: Record<InboxSource, { label: string; dot: string; badge: string }> = {
  escalate: { label: 'Escalation', dot: 'bg-escalate', badge: 'bg-escalate-bg text-escalate-fg border-escalate-bd' },
  rerun: { label: 'Rerun', dot: 'bg-rerun', badge: 'bg-rerun-bg text-rerun-fg border-rerun-bd' },
  hold: { label: 'Hold', dot: 'bg-hold', badge: 'bg-hold-bg text-hold-fg border-hold-bd' },
  self: { label: 'Note', dot: 'bg-accent', badge: 'bg-accent-weak text-accent-strong border-accent/30' },
}

// A self-authored item is a REMINDER when it carries a due date (scheduled — authored on the
// Calendar page) or a NOTE when it doesn't (authored in Notes). So a note never masquerades as a
// "reminder": reminders are the dated, Calendar-owned things. Non-self items keep their verdict label.
export function sourceLabel(item: { source: InboxSource; due?: string | null }): string {
  if (item.source === 'self') return item.due ? 'Reminder' : 'Note'
  return SOURCE_META[item.source].label
}

// The four kanban columns, in board order. "inbox" is the untriaged intake; "done" is the archive
// (items there drop out of the unread count and the inbox list's default view).
export const COLUMNS: { key: InboxColumn; label: string; hint: string }[] = [
  { key: 'inbox', label: 'Inbox', hint: 'Untriaged' },
  { key: 'todo', label: 'To do', hint: 'Queued' },
  { key: 'doing', label: 'In progress', hint: 'Working' },
  { key: 'done', label: 'Done', hint: 'Archived' },
]
export const COLUMN_LABEL: Record<InboxColumn, string> = {
  inbox: 'Inbox',
  todo: 'To do',
  doing: 'In progress',
  done: 'Done',
}

// Priority chips — high/med/low reuse the escalate/hold/info accents; "none" is muted. Ordered so a
// sort can rank by urgency (higher weight = more urgent).
export const PRIORITY_META: Record<InboxPriority, { label: string; chip: string; weight: number }> = {
  high: { label: 'High', chip: 'bg-escalate-bg text-escalate-fg border-escalate-bd', weight: 3 },
  med: { label: 'Med', chip: 'bg-hold-bg text-hold-fg border-hold-bd', weight: 2 },
  low: { label: 'Low', chip: 'bg-card-2 text-text-2 border-line-strong', weight: 1 },
  none: { label: 'None', chip: 'bg-card-2 text-text-3 border-line', weight: 0 },
}
export const PRIORITY_ORDER: InboxPriority[] = ['none', 'low', 'med', 'high']

// A short, human-referenceable id for a board card (UIC-14 "visible, referenceable id"). A self
// reminder's raw `self:<uuid>` collapses to a stable IB-XXXX tail; a derived ticket that already
// reads as a short human id (e.g. T-2868) passes through unchanged, while a raw store id (a uuid /
// content hash) collapses to a stable TK-XXXX handle so the card never shows a giant hex string.
// The full id is still shown on hover (a `title`) so it stays referenceable.
export function shortItemId(id: string, isSelf: boolean): string {
  if (isSelf) {
    const tail = id.replace(/^self:/, '').replace(/-/g, '')
    return `IB-${tail.slice(0, 4).toUpperCase()}`
  }
  if (id.length <= 12) return id // already a friendly ticket id (T-2868, …)
  return `TK-${id.replace(/[^a-z0-9]/gi, '').slice(0, 6).toUpperCase()}`
}

// Two-letter initials for a roster avatar chip (first + last word). Tolerant of a single-word or
// empty name so an unknown actor id never crashes the render.
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  const first = parts[0]?.[0] ?? ''
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? '') : ''
  return (first + last).toUpperCase() || '?'
}

// A relative "time ago" from an ISO timestamp, kept compact for dense rows. Falls back to the raw
// date if parsing fails (tolerant-at-boundaries house rule).
export function timeAgo(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return iso.slice(0, 10)
  const s = Math.max(0, Math.round((Date.now() - then) / 1000))
  if (s < 60) return 'just now'
  const m = Math.round(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.round(h / 24)
  if (d < 30) return `${d}d ago`
  return new Date(iso).toISOString().slice(0, 10)
}

// Local yyyy-mm-dd (NOT toISOString, which is UTC) — the calendar grid and due-status must agree on
// what "today" is, or a reminder created for today reads as overdue when UTC has already rolled over.
export function localYmd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
export function todayYmd(): string {
  return localYmd(new Date())
}

// Due-date status for the calendar/agenda + inbox badges. Compares a yyyy-mm-dd due against today,
// all in LOCAL time so it matches the calendar grid.
export type DueStatus = 'overdue' | 'today' | 'soon' | 'later' | 'none'
export function dueStatus(due: string | null): DueStatus {
  if (!due) return 'none'
  const today = todayYmd()
  if (due < today) return 'overdue'
  if (due === today) return 'today'
  const in3 = new Date()
  in3.setDate(in3.getDate() + 3)
  if (due <= localYmd(in3)) return 'soon'
  return 'later'
}
export const DUE_META: Record<DueStatus, { label: string; chip: string }> = {
  overdue: { label: 'Overdue', chip: 'bg-escalate-bg text-escalate-fg border-escalate-bd' },
  today: { label: 'Due today', chip: 'bg-hold-bg text-hold-fg border-hold-bd' },
  soon: { label: 'Due soon', chip: 'bg-accent-weak text-accent-strong border-accent/30' },
  later: { label: 'Scheduled', chip: 'bg-card-2 text-text-2 border-line-strong' },
  none: { label: '', chip: '' },
}
