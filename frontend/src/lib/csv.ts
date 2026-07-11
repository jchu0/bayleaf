// Tolerant CSV helpers shared by every boundary that reads an uploaded sheet (the wetlab
// samplesheet in Submit, the CRM sheet in Accession). Extracted from Submit.tsx so both parsers
// share ONE implementation instead of each minting its own (a missing/renamed column must degrade
// to an empty cell, never a crash — boundary tolerance, README §Data handling 2). Behavior is
// identical to the original private copies.

// Tolerant CSV line split — handles simple double-quoted fields; trims each cell. Not a full RFC
// parser (no embedded newlines), which is fine for a samplesheet a boundary reads defensively.
export function splitCsv(line: string): string[] {
  const out: string[] = []
  let cur = ''
  let inQ = false
  for (const c of line) {
    if (c === '"') inQ = !inQ
    else if (c === ',' && !inQ) {
      out.push(cur)
      cur = ''
    } else cur += c
  }
  out.push(cur)
  return out.map((s) => s.trim())
}

// Resolve a column index tolerantly by any of several accepted header names (case-insensitive).
export function colIndex(header: string[], names: string[]): number {
  const lc = header.map((h) => h.toLowerCase())
  for (const n of names) {
    const i = lc.indexOf(n)
    if (i >= 0) return i
  }
  return -1
}

// Escape a single CSV cell — quote when it contains a comma, quote, or newline; double interior
// quotes. The write-side counterpart to splitCsv so a round-trip (export → re-import) is lossless.
export function csvCell(value: string): string {
  if (/[",\n]/.test(value)) return `"${value.replace(/"/g, '""')}"`
  return value
}
