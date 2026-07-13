import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Download, FileCheck, Plus, ScanLine, ShieldAlert, Trash2 } from 'lucide-react'
import { PageHeader } from '../components/PageHeader'
import { Pager, type PerPage } from '../components/Pager'
import { useConfirm } from '../components/ConfirmDialog'
import { useToast } from '../components/Toast'
import {
  type AccessionRecord,
  CONSENTS,
  type Consent,
  SEXES,
  type Sex,
  TISSUES,
  loadAccessionDraft,
  parseAccessionCsv,
  saveAccessionDraft,
  stashHandoff,
  toAccessionCsv,
} from '../lib/accession'

// Sample accessioning (CRM) — the subject-registration step UPSTREAM of the wetlab samplesheet and
// the preflight gate. It composes subject/sample metadata and hands off to Submit; it NEVER runs a
// tool and NEVER transmits (compose ≠ execute). Every field here — subject id, collection date,
// accession #, site — stays CLIENT-SIDE (the PII seam banner says so). Structurally the same
// controlled-table + pagination pattern proven in Submit.

const INPUT_CLS =
  'w-full rounded-[7px] border border-line bg-card px-[9px] py-[7px] font-mono text-[12px] text-text outline-none focus:border-accent'
const SELECT_CLS =
  'w-full rounded-[7px] border border-line-strong bg-card-2 px-[9px] py-[7px] text-[11.5px] text-text-2 outline-none focus:border-accent'

function blankRecord(): AccessionRecord {
  return { subjectId: '', sampleId: '', tissue: TISSUES[0], sex: '', consent: '', collectedOn: '', accessionId: '', site: '', notes: '' }
}

export function Accession() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const confirm = useConfirm()
  const [records, setRecords] = useState<AccessionRecord[]>(() => loadAccessionDraft() ?? [])
  const [uploadName, setUploadName] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState<PerPage>('25')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [addCount, setAddCount] = useState('1')
  const fileInput = useRef<HTMLInputElement>(null)

  // Restore any saved draft once on mount (a client-side convenience; never a server round-trip).
  useEffect(() => {
    const draft = loadAccessionDraft()
    if (draft?.length) toast(`Restored a saved accessioning draft of ${draft.length} subjects.`, 'info')
  }, [toast])

  const per = Number(perPage)
  const total = records.length
  const pages = Math.max(1, Math.ceil(total / per))
  const curPage = Math.min(page, pages)
  const pageStart = (curPage - 1) * per
  const paged = records.slice(pageStart, pageStart + per)

  function patch(i: number, p: Partial<AccessionRecord>) {
    setRecords((rows) => rows.map((r, j) => (j === i ? { ...r, ...p } : r)))
  }
  function addSubjects(n: number) {
    const k = Math.max(1, Math.min(500, Math.floor(n) || 1))
    setRecords((rows) => [...rows, ...Array.from({ length: k }, () => blankRecord())])
  }
  function toggleSel(i: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })
  }
  function toggleAll() {
    setSelected((prev) => (prev.size === records.length ? new Set() : new Set(records.map((_, i) => i))))
  }
  async function removeSelected() {
    const n = selected.size
    if (n === 0) return
    const ok = await confirm({
      title: `Remove ${n} subject${n === 1 ? '' : 's'} from this batch?`,
      body: 'Removed from this accessioning draft only — nothing downstream is affected.',
      confirmLabel: 'Remove',
      tone: 'danger',
    })
    if (!ok) return
    setRecords((rows) => rows.filter((_, j) => !selected.has(j)))
    setSelected(new Set())
  }

  async function onFile(file: File) {
    try {
      const parsed = parseAccessionCsv(await file.text())
      if (parsed.length === 0) {
        toast(`No rows found in ${file.name}. Expected columns like Sample_ID, Subject_ID, Tissue.`, 'error')
        return
      }
      setRecords(parsed)
      setUploadName(file.name)
      setPage(1)
      setSelected(new Set())
      toast(`Parsed ${parsed.length} subjects from ${file.name}.`, 'success')
    } catch (e) {
      toast(`Couldn't read ${file.name} — ${e instanceof Error ? e.message : String(e)}`, 'error')
    }
  }

  function exportCsv() {
    if (records.length === 0) return
    const blob = new Blob([toAccessionCsv(records)], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'sample_metadata.csv'
    a.click()
    URL.revokeObjectURL(url)
    toast(`Exported ${records.length} subjects to sample_metadata.csv.`, 'success')
  }

  function saveDraft() {
    saveAccessionDraft(records)
    toast(`Saved a draft of ${records.length} subjects (client-side only).`, 'success')
  }

  async function sendToIntake() {
    if (records.length === 0) return
    const withSample = records.filter((r) => r.sampleId.trim()).length
    const ok = await confirm({
      title: 'Send subject metadata to wetlab intake?',
      body: `Attaches subject id + tissue for ${withSample} sample${withSample === 1 ? '' : 's'} to the Submit samplesheet screen. Subject identifiers stay client-side — nothing is transmitted.`,
      confirmLabel: 'Send to intake',
    })
    if (!ok) return
    stashHandoff(records)
    navigate('/submit')
  }

  return (
    <div className="mx-auto max-w-[1080px]">
      {/* UIC-1: the left-nav names this page — no eyebrow/subtitle prose. The PII seam banner below
          is an explicit safety/limitation warning and stays. */}
      <PageHeader title="Sample Metadata" />

      {/* PII seam banner — prominent, honest: nothing here leaves the browser. */}
      <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-hold-bd bg-hold-bg px-4 py-3 text-[12.5px] leading-relaxed text-hold-fg">
        <ShieldAlert size={17} className="mt-px shrink-0" />
        <div>
          <strong>Subject identifiers stay in your browser.</strong> Nothing on this screen is transmitted or persisted
          server-side — <span className="font-mono">POST /api/runs</span> carries no subject field (it&apos;s{' '}
          <span className="font-mono">extra=&quot;forbid&quot;</span>), so subject/PII persistence is gated behind the
          data-platform PII/de-identification design (a labelled seam). DOB and MRN are deliberately{' '}
          <strong>not</strong> collected (PHI); only lab-operational fields (collection date, accession #, site) are
          kept, and even those never leave the browser.
        </div>
      </div>

      {/* Upload dropzone (mirrors Submit) */}
      <input
        ref={fileInput}
        type="file"
        accept=".csv,.txt,.tsv"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) void onFile(f)
          e.target.value = ''
        }}
      />
      <div
        onClick={() => fileInput.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          const f = e.dataTransfer.files?.[0]
          if (f) void onFile(f)
        }}
        className={`flex cursor-pointer items-center gap-[18px] rounded-[14px] border-[1.5px] border-dashed p-[26px] transition-colors ${
          dragging ? 'border-accent bg-accent-weak' : 'border-line-strong bg-card hover:border-accent'
        }`}
      >
        <div className="flex h-[46px] w-[46px] shrink-0 items-center justify-center rounded-xl bg-accent-weak">
          <ScanLine size={23} strokeWidth={1.7} className="text-accent-strong" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[14px] font-semibold text-text">Drop a sample_metadata.csv, or click to browse</div>
          <div className="mt-0.5 text-[12px] text-text-2">
            Columns like <span className="font-mono">Subject_ID, Sample_ID, Tissue, Sex, Consent, Collected_On</span>.
            A missing column degrades to an empty cell — never a crash. Or add subjects manually below.
          </div>
        </div>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            fileInput.current?.click()
          }}
          className="whitespace-nowrap rounded-[9px] border border-line-strong bg-card px-[15px] py-[9px] text-[13px] font-medium text-accent-strong"
        >
          Browse files
        </button>
      </div>
      {uploadName && (
        <div className="mt-[10px] flex items-center gap-[11px] rounded-[11px] border border-proceed-bd bg-proceed-bg px-[14px] py-[11px]">
          <FileCheck size={18} strokeWidth={1.9} className="shrink-0 text-proceed" />
          <div className="min-w-0 flex-1 text-[12px] text-text-2">
            <span className="font-mono font-semibold text-proceed-fg">{uploadName}</span> · parsed{' '}
            <strong className="text-text">{records.length}</strong> subjects. Review and edit below.
          </div>
        </div>
      )}

      {/* CRM table */}
      <div className="mt-[14px] overflow-hidden rounded-[14px] border border-line bg-card shadow-card">
        <div className="flex items-center gap-[10px] border-b border-line px-[18px] py-[14px]">
          <div className="flex-1">
            <div className="text-[14.5px] font-semibold text-text">Subjects · {total}</div>
            <div className="mt-0.5 text-[12px] text-text-2">
              Subject + sample identity and collection metadata. Tissue merges into the samplesheet on handoff.
            </div>
          </div>
          {selected.size > 0 && (
            <button
              type="button"
              onClick={() => void removeSelected()}
              className="inline-flex items-center gap-[6px] rounded-lg border border-escalate-bd bg-escalate-bg px-3 py-[7px] text-[12.5px] font-medium text-escalate-fg transition-[filter] hover:brightness-95"
            >
              <Trash2 size={14} strokeWidth={1.9} />
              Remove {selected.size}
            </button>
          )}
          <div className="flex items-center gap-1 rounded-lg border border-line-strong bg-card px-1.5 py-1">
            <input
              type="number"
              min={1}
              max={500}
              value={addCount}
              onChange={(e) => setAddCount(e.target.value)}
              className="w-11 rounded-[6px] bg-transparent px-1 py-1 text-center font-mono text-[12.5px] text-text outline-none"
              aria-label="Number of subjects to add"
            />
            <button
              type="button"
              onClick={() => addSubjects(Number(addCount))}
              className="inline-flex items-center gap-[6px] rounded-[7px] bg-accent-weak px-2.5 py-[6px] text-[12.5px] font-medium text-accent-strong"
            >
              <Plus size={14} strokeWidth={2} />
              Add subject
            </button>
          </div>
        </div>

        {total === 0 ? (
          <div className="px-4 py-[34px] text-center">
            <div className="mx-auto max-w-[440px] text-[12.5px] leading-relaxed text-text-2">
              No subjects yet. Drop a <span className="font-mono">sample_metadata.csv</span> above, or use{' '}
              <strong className="text-text">Add subject</strong> to accession them by hand. Then export the CSV or send
              subject + tissue on to the wetlab samplesheet.
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <div className="min-w-[1040px]">
              <div className="grid grid-cols-[28px_30px_1.2fr_1.2fr_1.1fr_0.8fr_0.9fr_1fr_1fr_1fr_1.1fr] gap-[9px] border-b border-line bg-card-2 px-4 py-[9px] text-[9.5px] font-bold uppercase tracking-[.4px] text-text-3">
                <div className="flex items-center">
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5 accent-accent"
                    aria-label="Select all subjects"
                    checked={records.length > 0 && selected.size === records.length}
                    ref={(el) => {
                      if (el) el.indeterminate = selected.size > 0 && selected.size < records.length
                    }}
                    onChange={toggleAll}
                  />
                </div>
                <div>#</div>
                <div>Subject ID</div>
                <div>Sample ID</div>
                <div>Tissue</div>
                <div>Sex</div>
                <div>Consent</div>
                <div>Collected on</div>
                <div>Accession #</div>
                <div>Site / study</div>
                <div>Notes</div>
              </div>
              {paged.map((r, li) => {
                const i = pageStart + li
                return (
                  <div
                    key={i}
                    className={`grid grid-cols-[28px_30px_1.2fr_1.2fr_1.1fr_0.8fr_0.9fr_1fr_1fr_1fr_1.1fr] items-center gap-[9px] border-b border-line px-4 py-[9px] transition-colors ${
                      selected.has(i) ? 'bg-accent-weak/40' : ''
                    }`}
                  >
                    <div className="flex items-center">
                      <input
                        type="checkbox"
                        className="h-3.5 w-3.5 accent-accent"
                        aria-label={`Select ${r.subjectId || r.sampleId || `subject ${i + 1}`}`}
                        checked={selected.has(i)}
                        onChange={() => toggleSel(i)}
                      />
                    </div>
                    <div className="font-mono text-[11.5px] text-text-3">{i + 1}</div>
                    <input value={r.subjectId} onChange={(e) => patch(i, { subjectId: e.target.value })} aria-label={`Subject ID, row ${i + 1}`} className={INPUT_CLS} placeholder="SUBJ-…" />
                    <input value={r.sampleId} onChange={(e) => patch(i, { sampleId: e.target.value })} aria-label={`Sample ID, row ${i + 1}`} className={INPUT_CLS} placeholder="HG002" />
                    <select value={r.tissue} onChange={(e) => patch(i, { tissue: e.target.value })} aria-label={`Tissue, row ${i + 1}`} className={SELECT_CLS}>
                      {[...new Set([...TISSUES, r.tissue])].filter(Boolean).map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                    <select value={r.sex ?? ''} onChange={(e) => patch(i, { sex: e.target.value as Sex })} aria-label={`Sex, row ${i + 1}`} className={SELECT_CLS}>
                      {SEXES.map((s) => (
                        <option key={s.value} value={s.value}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                    <select value={r.consent ?? ''} onChange={(e) => patch(i, { consent: e.target.value as Consent })} aria-label={`Consent, row ${i + 1}`} className={SELECT_CLS}>
                      {CONSENTS.map((c) => (
                        <option key={c.value} value={c.value}>
                          {c.label}
                        </option>
                      ))}
                    </select>
                    <input type="date" value={r.collectedOn ?? ''} onChange={(e) => patch(i, { collectedOn: e.target.value })} aria-label={`Collected on, row ${i + 1}`} className={INPUT_CLS} title="Collection date — not date of birth (DOB is PHI, not collected)" />
                    <input value={r.accessionId ?? ''} onChange={(e) => patch(i, { accessionId: e.target.value })} aria-label={`Accession number, row ${i + 1}`} className={INPUT_CLS} placeholder="ACC-…" />
                    <input value={r.site ?? ''} onChange={(e) => patch(i, { site: e.target.value })} aria-label={`Site or study, row ${i + 1}`} className={INPUT_CLS} />
                    <input value={r.notes ?? ''} onChange={(e) => patch(i, { notes: e.target.value })} aria-label={`Notes, row ${i + 1}`} className={INPUT_CLS} />
                  </div>
                )
              })}
            </div>
          </div>
        )}
        {total > 0 && (
          <div className="px-4 pb-3">
            <Pager total={total} page={curPage} perPage={perPage} onPage={setPage} onPerPage={setPerPage} noun="subjects" />
          </div>
        )}
      </div>

      {/* Footer actions */}
      <div className="mt-4 flex flex-wrap items-center gap-[12px]">
        <span className="text-[11.5px] text-text-3">
          Authored here, consumed in{' '}
          <Link to="/submit" className="font-medium text-accent-strong hover:underline">
            Submit samplesheet
          </Link>
          .
        </span>
        <div className="flex-1" />
        <button
          type="button"
          onClick={exportCsv}
          disabled={total === 0}
          className="inline-flex items-center gap-2 rounded-[9px] border border-line-strong bg-card px-4 py-[9px] text-[13px] font-medium text-text-2 disabled:opacity-50"
        >
          <Download size={15} strokeWidth={1.9} />
          Export CSV
        </button>
        <button
          type="button"
          onClick={saveDraft}
          className="rounded-[9px] border border-line-strong bg-card px-4 py-[9px] text-[13px] font-medium text-text-2"
        >
          Save draft
        </button>
        <button
          type="button"
          onClick={() => void sendToIntake()}
          disabled={total === 0}
          className="inline-flex items-center gap-2 rounded-[9px] bg-accent px-[18px] py-2.5 text-[13px] font-semibold text-white transition-opacity disabled:opacity-60"
        >
          <ArrowRight size={15} strokeWidth={2} />
          Send to wetlab intake
        </button>
      </div>
    </div>
  )
}
