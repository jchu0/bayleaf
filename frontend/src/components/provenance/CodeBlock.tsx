import { useState } from 'react'

// A copyable, monospace code/stderr block for the Provenance event trail (UIC-9): any
// code/command or error/stderr payload — and any structured (object/array) payload, pretty-
// printed — renders here as a <pre> that preserves whitespace and scrolls inside its own frame
// (never reflowing the row), with a corner copy button. Kept distinct from <Fingerprint> (a
// one-line content-hash cell): this is for multi-line dumps and JSON payloads. 100% read-only —
// it only displays, verbatim, what the ledger recorded (ADR-0001/0002).
export function CodeBlock({ code, label }: { code: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    void navigator.clipboard?.writeText(code).then(
      () => {
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      },
      () => {},
    )
  }
  return (
    <div className="min-w-0">
      {label && (
        <div className="mb-1 font-mono text-[10px] font-semibold uppercase tracking-[0.4px] text-text-3">{label}</div>
      )}
      <div className="relative overflow-hidden rounded-[7px] border border-line bg-card-2">
        <button
          type="button"
          onClick={copy}
          className="absolute right-1.5 top-1.5 z-10 rounded-[5px] border border-line bg-card px-1.5 py-0.5 text-[10px] text-accent-strong hover:underline"
        >
          {copied ? 'copied ✓' : 'copy'}
        </button>
        {/* overflow-auto scrolls a long command/stderr in BOTH axes inside a capped frame, so a
            large dump never blows out the event row. whitespace-pre preserves the exact bytes. */}
        <pre className="max-h-[280px] overflow-auto px-3 py-2.5 pr-14">
          <code className="select-all whitespace-pre font-mono text-[11px] leading-relaxed text-text-2">{code}</code>
        </pre>
      </div>
    </div>
  )
}
