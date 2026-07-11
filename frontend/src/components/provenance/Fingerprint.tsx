import { useState } from 'react'

// The shared copy / show-full content-fingerprint cell — extracted from the copy+reveal logic
// that was inline in Provenance.tsx's ProvArtifactRow, so the lineage rows, artifact index,
// event-trail entity refs and the header's run id all read identically. Labelled "fingerprint"
// (not "sha256") as house defense-in-depth (T-080): it's a content digest for fixity, not a
// process/ledger id, and the label stays accurate without advertising the algorithm.
//
// Renders as a FRAGMENT (copy button · show-full toggle · optional full reveal) so it drops into
// a `flex flex-wrap items-center` row — the `w-full` reveal then breaks onto its own line beneath
// the controls. Every call site wraps it in such a row.
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
      <button
        type="button"
        onClick={copy}
        title={`${label} · ${value} · click to copy`}
        className="font-mono text-[11px] text-accent-strong hover:underline"
      >
        {copied ? 'copied ✓' : `${label} ${value.slice(0, 12)}…`}
      </button>
      <button
        type="button"
        onClick={() => setShowFull((v) => !v)}
        className="text-[10.5px] text-text-3 hover:text-text-2"
      >
        {showFull ? 'hide' : 'show full'}
      </button>
      {showFull && (
        <span className="w-full select-all break-all font-mono text-[10.5px] leading-relaxed text-text-2">{value}</span>
      )}
    </>
  )
}
