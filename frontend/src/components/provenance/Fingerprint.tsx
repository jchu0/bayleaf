import { useState } from 'react'

// The shared content-fingerprint cell — used wherever a named entity (an artifact file, an
// EntityRef, a finding/card) carries a content digest. Labelled "fingerprint" (not "sha256") as
// house defense-in-depth (T-080): it's a content digest for fixity, not a process/ledger id.
//
// UIC-9: the id/name (the file name / ref id shown alongside) is the human handle; the hash is
// on-demand DETAIL. So this renders `<label>:` + a "show full" toggle and NEVER a leading partial
// — a truncated prefix reads as if it were the value yet can't be scanned or matched, so it's
// pure noise. Expansion reveals the FULL digest inside a mono `overflow-x` block that scrolls
// sideways within its own frame: it wraps onto its own full-width line and never reflows the
// controls or neighbours beside it (UIC-9: "show full" must not distort card formatting).
//
// Renders as a FRAGMENT (label · toggle · optional full reveal) so it drops into a
// `flex flex-wrap items-center` row — every call site wraps it in such a row, and the `w-full`
// reveal then breaks onto its own line beneath the controls.
export function Fingerprint({ value, label = 'fingerprint' }: { value: string | null; label?: string }) {
  const [copied, setCopied] = useState(false)
  const [showFull, setShowFull] = useState(false)

  if (!value) return <span className="font-mono text-[11px] text-text-3">{label} n/a</span>

  const copy = () => {
    void navigator.clipboard?.writeText(value).then(
      () => {
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      },
      () => {},
    )
  }

  return (
    <>
      <span className="font-mono text-[11px] text-text-3">{label}:</span>
      <button
        type="button"
        onClick={() => setShowFull((v) => !v)}
        title={showFull ? undefined : `${label} · click to reveal the full digest`}
        className="text-[10.5px] text-accent-strong hover:underline"
      >
        {showFull ? 'hide' : 'show full'}
      </button>
      {showFull && (
        <span className="flex w-full items-center gap-2">
          <code className="block min-w-0 flex-1 select-all overflow-x-auto whitespace-nowrap rounded-[5px] border border-line bg-card-2 px-2 py-1 font-mono text-[10.5px] leading-relaxed text-text-2">
            {value}
          </code>
          <button type="button" onClick={copy} className="shrink-0 text-[10.5px] text-accent-strong hover:underline">
            {copied ? 'copied ✓' : 'copy'}
          </button>
        </span>
      )}
    </>
  )
}
