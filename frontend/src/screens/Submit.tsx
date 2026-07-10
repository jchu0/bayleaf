import { PageHeader } from '../components/PageHeader'

// Submit samplesheet (§5.1) — the pipeline's front door: registers a run + its samples BEFORE
// processing (compose ≠ execute; it never runs a tool). Foundation stub: route + nav land in
// Wave 1; the upload/BaseSpace flow + editable samples table are built in Wave 2.
export function Submit() {
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        eyebrow="Intake"
        title="Submit samplesheet"
        subtitle="Register a run and its samples before processing. Upload a samplesheet or pull from BaseSpace — this screen never runs a tool."
      />
      <div className="rounded-xl border border-dashed border-line-strong bg-card p-10 text-center text-[13.5px] text-text-2">
        The upload / BaseSpace flow and editable samples table land in the next wave.
      </div>
    </div>
  )
}
