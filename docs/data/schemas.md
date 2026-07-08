# Data Schemas — Records & Persistence

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | bioinformatics / software |
| **Related** | [metric_registry.md](metric_registry.md), [provenance.md](provenance.md), [nf-core-conventions.md](nf-core-conventions.md), [qc_metrics.md](qc_metrics.md), ADR-0002/0007/0008/0009/0010/0013, the layered data-contract ADR *(in draft — link when numbered)* |

## Overview

The decided data contract. **Pydantic v2 is the source of truth**; SQLAlchemy tables
mirror it. The **append-only JSONL ledger is authoritative; the DB is a rebuildable
projection** (ADR-0002). We adopt nf-core/sarek *vocabulary* and diverge on *semantics*
(we validate outputs, not inputs). Illumina/sarek adapter-grade.

## Conventions

1. **IDs:** UUIDv7 with a type-prefix from an **extensible registry** (`run_`, `samp_`,
   `art_`, `arun_`, `eval_`, `metric_`, `find_`, `card_`, `evt_`, `sig_`, `tkt_`, `exp_`,
   `know_`, …) — not a hardcoded enum; new types register a prefix. **`created_at` is
   always stored** (never rely on the ID's embedded timestamp as truth).
2. **Timestamps:** store **UTC** (ISO-8601), display **America/Phoenix**.
3. **`schema_version`** on every persisted record.
4. **`origin`:** `real-giab | synthetic | contrived`.
5. **`source_contract`:** how a record was reconstructed (`samplesheet | csv_recap |
   pipeline_info | multiqc | filesystem`) — we trust documented file contracts, not
   runtime internals (nf-core `meta` guarantees only `id`/`single_end`).

## Records

### Inputs
1. **Run** (`run_`) — external_run_id · instrument · instrument_id · read_length ·
   workflow_id (run type) · created_at · completed_at · loaded_at · origin · status.
2. **Sample** (`samp_`) — run_id · subject_key *(from sarek `patient`; **not PHI-free by
   construction** — real deployments route through de-id)* · external_sample_id *(sarek
   `sample`)* · sex_declared (`XX|XY|NA|unknown`) · **sarek_status_raw** (`"0"|"1"|…`) ·
   **sample_role** (`normal|tumor|relapse|unknown`) · **sample_type** (`whole_blood|
   saliva`) · assay · assay_version · lane_ids[] · **num_lanes** *(derived = |lane_ids|)* ·
   library_prep · submitted_by · source_contract · origin.
3. **ArtifactRef** (`art_`) — analysis_run_id · run/sample_id · patient_id · **kind**
   (`fastq|recal_cram|recal_table|mosdepth_summary|fastp_json|markdup_metrics|
   samtools_stats|ngscheckmate|vcf|gvcf|filtered_vcf|joint_vcf|multiqc_json|versions_yml|
   params_json|execution_trace`) · uri · **content_hash** (sha256 over stored bytes) ·
   **hash_algorithm** · size_bytes · caller · stage · pipeline_version · **source_contract**
   (ingest priority: `csv_recap > samplesheet > pipeline_info > filesystem`) · source_row ·
   source_column · origin.

### Analysis
4. **AnalysisRun** (`arun_`) — one gate execution over a sample under pinned versions.
   Findings/MetricValues/DecisionCards/Events FK here. Two-layer manifest:
   - `sample_id` · `input_artifact_ids[]` · `generated_by` (`stub|rule_engine|claude|human`) ·
     `model` · `origin` · `started_at` · `completed_at` · `status`.
   - **`pipeline_provenance`** *(from sarek `pipeline_info/`)*: params_artifact_id + params_hash ·
     software_versions_artifact_id + hash (flattened `tool → version`) · execution_trace_artifact_id +
     hash · pipeline_name/version · nextflow_version? · run_command? · exit_summary.
   - **`gate_provenance`** *(ours)*: runbook_profile_id + profile_version · rule_pack_version ·
     metric_registry_version · parser_versions{}.
5. **EvaluationRun** (`eval_`) — a QA/benchmark run. label_set_id (GIAB truth /
   synthetic-known-verdicts) · analysis_run_ids[] · gate_version_manifest (pinned) ·
   scores{verdict precision/recall, narration faithfulness} · report_artifact_id · status.

### QC
6. **MetricValue** (`metric_`) — sample_id · analysis_run_id · **metric_key** *(→ registry
   `our_key`)* · gate · raw_value · raw_unit · **normalized_value** · **canonical_unit** ·
   **metric_registry_version** · source_artifact_id · source_field · source_locator ·
   parser_version · content_hash. **Immutable** (`frozen`, content-hash identity), built via
   [`MetricRegistry.observe(...)`](metric_registry.md) — the registry (not the model) computes
   `normalized_value` and stamps `canonical_unit` + `metric_registry_version` **onto every
   record** (not dereferenced at read time) so a row is standalone-interpretable for ML/audit
   (ADR-0007). **On the critical path today:** the rule engine builds registry-backed
   `MetricValue`s during evaluation and gates on `normalized_value` (units contract below).

> **Units contract — one representation across components.** A metric crosses every
> component boundary as its **`normalized_value`**: a `float` in the metric's
> **`canonical_unit`** — a **decimal fraction** for rates (Q30 `0.841`, duplication `0.226`,
> cluster-PF `0.834`), `x` for coverage. The [registry](metric_registry.md) is the single
> authority on each metric's canonical unit; `MetricValue` snapshots `raw_value`/`raw_unit`
> (what the tool reported, e.g. `84.1` `percent`) *alongside* the normalized value so the
> conversion is auditable and never re-guessed downstream. **Consumers read
> `normalized_value` (canonical) — never `raw_value`.** Passing a percent where a fraction is
> expected is the units-mismatch bug this contract exists to prevent. Runbook thresholds gate
> on the registry `our_key` and are stored in the same canonical unit, so the rules compare a
> threshold and the `normalized_value` it gates on the same scale by construction; the finding
> text then renders both back into the operator-facing raw unit via `MetricRegistry.denormalize` (Q30 `0.841 < 0.85` internally,
> shown as `84.1% / ≥ 85%`).

> **Realized in code:** `runbook.QCThreshold` carries the registry `our_key` + canonical
> `gate`/`hard_fail`; `rules._evaluate_metric` decides on `normalized_value` then denormalizes
> for display — verdicts stay byte-identical to the pre-registry engine
> ([metric_registry.md](metric_registry.md)).

### Findings & decisions
7. **Evidence** — **source_kind** (`artifact|metric|multiqc_source|execution_trace|params|
   human_note`) · artifact_id · **metric_value_id** · **corpus_id** · source_file ·
   source_field · locator · observed_value · expected_value? · threshold?.
8. **Finding** (`find_`) — **immutable** · analysis_run_id · sample_id · gate
   (`preflight|qc|variant`) · category (`provenance|qc|coverage|contamination|identity|
   variant|pipeline|metadata`) · severity · rule_id · **rule_version** · title · detail ·
   evidence[] · suggested_verdict · signature (→ IssueSignature) · **content_hash** ·
   created_at. *(Suppression/resolution never mutate a Finding — they live on
   IssueSignature/Ticket/ExperienceRecord.)*
9. **GateResult** *(embedded in DecisionCard)* — gate · verdict · severity · finding_ids[] · rationale.
10. **DecisionCard** (`card_`) — **one per (sample × analysis_run)** · analysis_run_id ·
    **run_id** *(human run id, e.g. `mock_run_01`; contextual — not in `content_hash`)* ·
    sample_id · verdict (`proceed|hold|rerun|escalate`) · **confidence?** *(nullable —
    omitted until grounded)* · headline · rationale · next_steps[] · finding_ids[] ·
    gate_results[] (GateResult) · generated_by · model · **content_hash** · created_at ·
    supersedes_card_id?. *(`is_current` is a projection, not stored truth.)*

### Provenance / events (append-only — ADR-0002)
11. **ProvenanceEvent** (`evt_`) — event_type *(vocabulary below)* · analysis_run_id ·
    run_id · sample_id · ticket_id? · actor (`system|rule_engine|agent|human:<id>`) ·
    **inputs[]** / **outputs[]** (EntityRef) · payload (typed by event_type) ·
    **trace_id** · **correlation_id** · ts.
12. **EntityRef** — entity_type (`artifact|metric|finding|card|ticket|experience|knowledge`) ·
    id · content_hash? *(required for artifacts; present on immutable findings/cards; null on mutable)*.

### Agents / corpora (ADR-0009) — MVP-deferred
13. **TriageNote** — finding_id/signature · agent (`qc_triage|pipeline_repair`) ·
    likely_cause · suggested_action · citations[] (finding_ids + corpus_ids) · model ·
    **advisory: Literal[True]** *(never sets a verdict)*.
14. **ExperienceRecord** (`exp_`) — issue_signature · source_finding_id · source_ticket_id ·
    context · diagnosis · human_action · outcome · resolution_type (`class_fix|
    see_one_fix_one|suppress|escalate`) · resolved_by · created_at. *(Canonical; embeddings
    are separate derived index records, not stored here.)*
15. **KnowledgeRecord** (`know_`) — kind (`tool_doc|metric_def|failure_signature|
    runbook_rule`) · title · content · source · version · tags[]. *(Embeddings derived/indexed separately.)*

### Ops / tickets (ADR-0008, ADR-0010)
16. **IssueSignature** (`sig_`) — **signature** *(hash of category + normalized locus/params
    — issue **semantics**, decoupled from rule impl)* · **signature_version** *(hashing
    scheme only)* · **salient_params** *(stored, not just hashed)* · category ·
    example_finding_ids[] · occurrence_count · first/last_seen · status (`active|suppressed|
    escalated`) · suppressed_until · escalated_to.
17. **ReviewItem/Ticket** (`tkt_`) — card_id · sample_id · status (`open|in_review|resolved`) ·
    priority · assignee · required_tier (`reviewer|approver`) · resolution_experience_id ·
    created_at · updated_at.
18. **Notifications** (ADR-0010 §2) — two shapes:
    a. **NotifyEvent** *(ticket-era shape, deferred)* — ticket_id · channel (`slack|jira|…`) ·
       status (`queued|sent|failed`) · payload · created_at.
    b. **NotifyPayload / NotifyResult** *(implemented — T-015b)* — the outbound notify port
       turns a *flagged* `DecisionCard` into a channel-ready notification. **NotifyPayload**
       (frozen, content-hashed): channel · title · text · blocks[] *(Slack Block Kit dicts — no
       SDK to build)* · sample_id · run_id · **verdict** · headline — **display only**, copies
       the gate's verdict and never sets one (ADR-0001). **NotifyResult**: status
       (`skipped|prepared|sent`) · adapter (`stub|slack`) · payload? · detail. Only *actionable*
       (non-PROCEED) cards notify; live Slack send is opt-in (`PIPEGUARD_SLACK_LIVE`) and
       degrades to the offline stub on any error. Each real notification emits a
       `notification.emitted` event (below). See [provenance.md](provenance.md).

### Config
19. **RunbookProfile** — assay · assay_version · sample_type · platform · **profile_version** ·
    source_ref · effective_from · effective_to · active · checksum ·
    `thresholds{ metric_key → { gate, hard_fail, borderline_band, direction, unit,
    ui:{group, fa_icon?, help_text, enum?, min?, max?} } }`. *(Borrows the
    `nextflow_schema.json` form shape; keeps the three-way gate keywords first-class.)*
20. **Profile** (deployment/agent, ADR-0005) — **config (pydantic-settings/YAML), not a DB record**.

## Event vocabulary (the event-sourced core)

Authoritative append-only ledger, projector-compatible from day one:
`run.registered` · `sample.registered` · `analysis_run.started` · `artifact.ingested` ·
`metric.parsed` · `finding.emitted` · `verdict.decided` · `analysis_run.completed` ·
`notification.emitted` *(one per actionable card when a notifier is wired — T-015b)* ·
`ticket.actioned` · `resolution.recorded`.

**Separately authoritative (NOT event-sourced / not in decision-replay):**
1. RunbookProfile / config — JSON/YAML/JSONL source files.
2. MetricRegistry — a versioned schema artifact.
3. Knowledge corpora — curated JSONL.
4. ExperienceRecords — their own append-only corpus/ledger (not part of production-state replay yet).

## Persistence (databases)

1. **Repository interface is mandatory** (ADR-0003) — the core never touches a DB directly.
2. **JSONL ledger is authoritative; the relational DB is a rebuildable projection.**
   Ship a **`rebuild-db`** command from day one (replay JSONL → DB); Phase-2 hardens it to
   byte-identical replay determinism (ADR-0002).
3. **Relational** (SQLite default → Postgres adapter): runs, samples, analysis_runs,
   artifacts, metric_values, findings, decision_cards, issue_signatures, review_items,
   notify_events, runbook_profiles.
4. **Artifacts:** raw files (VCF/CRAM/QC) in an **ArtifactStore** (local FS now, S3/object
   later); the DB holds only the hashed **ArtifactRef**.
5. **Corpora/embeddings:** knowledge + experience as JSONL; retrieval via BM25/embedding
   index now; **pgvector** when Postgres lands (also the wishlist vector-QC home). Embeddings
   are **derived index records**, never stored on the canonical record.

## Invariants

1. Findings are immutable; state lives on IssueSignature/Ticket/ExperienceRecord.
2. IssueSignature identity is **semantic**, decoupled from rule_version.
3. AI is **advisory** — never sets or overrides a verdict (ADR-0001).
4. One DecisionCard per (sample × analysis_run); current-card is a projection.
5. JSONL authoritative; DB projection rebuildable — no dual-write truth.
6. Every Finding/Card cites Evidence traceable to an artifact + hash.
