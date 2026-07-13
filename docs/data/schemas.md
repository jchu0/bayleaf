# Data Schemas — Records & Persistence

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-13 (MST) — the `CheckCoverage` contamination-flip is now REAL (`b03d1fa`'s `rules._examined_metric_categories`); corrects the 2026-07-12 note below, which was accurate as of that day but is now superseded. Prior: 2026-07-12 (MST) — job-store `held`/`scheduled` parked states (ADR-0021); corrected the `CheckCoverage` contamination-flip claim (WS-02 landed but the flip did not — verified against `rules.py`) |
| **Audience** | bioinformatics / software |
| **Related** | [metric_registry.md](metric_registry.md), [provenance.md](provenance.md), [nf-core-conventions.md](nf-core-conventions.md), [qc_metrics.md](qc_metrics.md), ADR-0002/0007/0008/0009/0010/0013, [ADR-0015](../adr/ADR-0015-layered-data-contract.md), [ADR-0016](../adr/ADR-0016-postgres-port.md) (pluggable-store family, incl. the job + library stores), [ADR-0018](../adr/ADR-0018-variant-interpretation-advisory-evidence.md) (VariantCall / route-to-human / `data.exported` share egress), [ADR-0021](../adr/ADR-0021-operator-gated-scheduled-pipeline-processing.md) (job-store `held`/`scheduled`), [design/agent-authoring-contract.md](../design/agent-authoring-contract.md) (`LibraryEntry`'s conformance gate), [journal 2026-07-10](../journal/2026-07-10-provenance-qc-builder-auth.md), [journal 2026-07-10 (wave 6)](../journal/2026-07-10-wave6-route-to-human-deid.md), [journal 2026-07-11](../journal/2026-07-11-d2-d3-share-egress.md), [journal 2026-07-11 P3 backlog](../journal/2026-07-11-p3-backlog.md), [journal 2026-07-11 fleet](../journal/2026-07-11-fleet.md) |

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
   workflow_id (run type) · created_at · completed_at · loaded_at · origin · status ·
   **platform** · **run_date** · **run_name** *(run-level `[Header]` context the
   `RunArtifacts` intake bundle carries — all `str | None`, default `None`; see the
   header-context note below)*.
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

> **Run-level header context — `RunArtifacts.platform` / `.run_date` / `.run_name`.** Parsed
> tolerantly from the Illumina v2 SampleSheet `[Header]` block (keys `InstrumentPlatform` /
> `Date` / `RunName`) by `parsers.parse_sample_sheet_header` → `SampleSheetHeader`, and threaded
> onto the `RunArtifacts` intake bundle by `load_run`. All three are **`str | None`, default
> `None`**: a sheet may omit any key (or the whole sheet), and a **missing key stays `None`**
> rather than being invented — the tolerant-boundary principle (a missing field is a signal, not
> a crash), same as the other intake parsers. `run_date` is the **raw header date string exactly
> as written** (e.g. `"2026-07-07"`), **not** a parsed/normalized `datetime`: the intake layer
> deliberately does not coerce it, so an absent or malformed value degrades to `None` instead of
> failing — contrast Convention 2, which governs *stored* run timestamps (`created_at`, etc.).

> **Intake bundle — `RunArtifacts` (parser output, tolerant).** The in-memory contract
> `parsers.load_run` hands the rules (ADR-0015 *tolerant intake*, distinct from the persisted
> records above): `run_id` plus per-sample collections `samples[]` (`Sample`), `sample_sheet[]`
> (`SampleSheetEntry`), `demux[]` (`DemuxRecord`), `qc[]` (`QCMetrics`), `log_lines[]` (raw
> `pipeline.log` lines), **`execution_trace[]` (`TraceRecord`)**, and **`variant_calls[]`
> (`VariantCall`)** — plus the run-level header context above. **Each collection defaults empty**;
> a missing on-disk artifact yields no rows, not a crash (tolerant boundary, CLAUDE.md
> data-handling 2).
>
> **`VariantCall` (ADR-0018 D2, 2026-07-10).** One annotated candidate variant bayleaf **READS**
> from an externally-produced annotated VCF/table — a driver ran VEP/bcftools, bayleaf never does
> (composes ≠ executes, ADR-0001/0003) — parsed by `parsers.parse_variant_calls` from the on-disk
> artifact **`variants.csv`** (tolerant of alt column spellings `clnsig`/`clnrevstat`/`clnacc`; an
> absent file yields `[]`). Fields — `sample_id` (required) plus **all-optional** `gene` · `hgvs` ·
> `clinvar_significance` (raw `CLNSIG`) · `clinvar_review_status` (raw `CLNREVSTAT`) ·
> `clinvar_accession` · `clinvar_version`. **Clinical significance is stored VERBATIM** — the
> parser and the rule that reads it never normalize or reclassify the string; bayleaf authors no
> pathogenicity of its own (ADR-0004). `variant_calls` is folded into `RunArtifacts.sample_ids()`
> (a sample present only via an annotated variant still gets evaluated). Empty for every
> committed fixture except `data/RUN-2026-07-11-CLINVAR-RTH/` (a contrived, verbatim-cited
> ClinVar spike); it feeds the off-by-default route-to-human rule below (no verdict by itself)
> **and, additively (2026-07-11, W3 continuation), a read-only wire projection:**
> `GET /api/runs/{run_id}/variants` (`api/main.py`) re-parses the same `variants.csv` via the
> SAME `parse_variant_calls` and returns the list verbatim — 404 for an unknown run, `[]` for a
> run with no `variants.csv`. `frontend/src/types.ts`'s `VariantCall` mirrors the seven fields
> above exactly (`sample_id` required, the rest nullable); `RunReport.tsx`'s per-variant table
> renders it. See [functional.md REQ-F-094](../requirements/functional.md).
>
> **Route-to-human policy (`runbook.RouteToHumanPolicy`, ADR-0018 D2).** A `Runbook.route_to_human`
> field, **OFF BY DEFAULT** (`significances: tuple[str, ...] = ()`  — an empty tuple is
> *disarmed*, `.armed` is `False`). An operator arms it with the ClinVar `CLNSIG` values (and,
> optionally, a `review_statuses` star-rating floor) that should route a sample to mandatory human
> review. This is a config object on the runbook, **not** a persisted record — see
> [qc_metrics.md](qc_metrics.md) for the rule it drives (**VAR-RTH-001**) and its verdict.
>
> **`QCMetrics` (T-082).** The frozen-CSV five (`q30` · `pct_reads_identified` ·
> `mean_coverage` · `dup_rate` · `cluster_pf`, every run carries these) plus **8 additional
> `float | None` fields** a richer QC report may also emit: `phix_aligned` (preflight tier);
> `breadth_20x` · `breadth_30x` · `pct_mapped` · `on_target` (extra QC tier); `variant_dp` ·
> `variant_gq` · `variant_titv` (variant tier). All 8 default `None` (absent column → `None`,
> tolerant, same as the frozen five) and each maps to a **registered** metric-registry
> `our_key` with a declared raw unit (`metrics/mapping.py` `_QCMETRICS_MAP` —
> [metric_registry.md](metric_registry.md)); a present value populates the decision card's
> **preflight** and **variant** gate groups (previously always empty for every run). `runbook.QCThreshold`
> correspondingly gains `required: bool = True` — 5 of the 8 (breadth_20x/30x, pct_mapped,
> on_target, variant_dp) get an **optional** (`required=False`) threshold that scores a present
> value but never NA-flags an absent one (`rules._evaluate_metric`); `phix_aligned`/`variant_gq`/
> `variant_titv` stay ungated observations. See [qc_metrics.md](qc_metrics.md) for the concrete
> thresholds.
>
> **`SampleMetrics` / `RawObservation` — the registry-keyed ingestion contract (WS-06·PR1/PR2,
> 2026-07-12).** An alternate, additive shape for `RunArtifacts.qc` entries alongside `QCMetrics`:
> `models.RawObservation` (frozen: `raw_value` + `raw_unit` + source provenance) and
> `models.SampleMetrics` (`sample_id` + `raw: dict[our_key -> RawObservation]`) — a generic map
> over registered metric-registry keys, rather than a fixed set of named fields. **`RunArtifacts.qc:
> list[QCMetrics | SampleMetrics]`** is a **transition Union, not a hard flip**: every reader of
> `.qc` (rules, engine, `sample_ids()`, the Claude synthesizer context) already went through
> `metrics.mapping.metric_values_for` / `.sample_id` / `.model_dump`, which PR1 made accept both
> shapes — so an ingested run and a frozen-CSV run gate identically, with zero `QCMetrics`
> field-access anywhere in `src/`/`api/`. `metrics.sample_metrics_from_qcmetrics` is the transition
> bridge that lowers a `QCMetrics` into the SAME `SampleMetrics` shape internally (byte-identical
> normalized values either way). The intended producer of a real `SampleMetrics` is
> [`ingest/nfcore.py`](../../src/bayleaf/ingest/nfcore.py)'s `ingest_results_dir()` (a published
> nf-core `results/` dir → `SampleMetrics`, WS-03) — proven end-to-end against real HG002 output
> (`tests/test_ingest.py::test_real_nextflow_results_ingest_and_gate`) but **not yet called from any
> production code path**; see [nf-core-conventions.md §4](nf-core-conventions.md) and `CLAUDE.md`
> code map item 1g/1b for the as-built vs. proven-but-unwired distinction.
>
> **`TraceRecord`** — one task row of the Nextflow/nf-core **execution trace**, whose on-disk
> artifact is **`trace.txt`** (matching ArtifactRef `kind=execution_trace`), parsed by
> `parsers.parse_execution_trace` inside `load_run`. Fields — **all optional (`… | None`,
> default `None`):** `task_id` · `process` · `tag` *(the nf-core sample tag; EXEC-001 matches a
> task to a sample by exact `tag`)* · `status` *(task disposition, upper-cased —
> `COMPLETED|FAILED|CACHED|ABORTED`)* · `exit` *(process exit code; `0` = success)*. A
> **STRUCTURED pipeline-execution signal the gate READS — it never runs a process** (composes ≠
> executes, ADR-0001/0003); every field is optional so a partial/garbled trace is a **signal,
> not a crash**. A failed task (status in the runbook failure set — default `FAILED`/`ABORTED` —
> **or** a nonzero `exit`) drives the **EXEC-001** rule (category `pipeline` → **preflight** gate,
> suggested **RERUN**), the structured sibling of PIPE-001's free-text log marker; its `Evidence`
> cites `trace.txt` with **`source_kind=execution_trace`** (#7). See [provenance.md](provenance.md)
> for why this is a *gate input*, not a new ledger event.

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
    gate_results[] (GateResult) · **metric_values[]** *(MetricValue; registry-normalized QC
    metrics for the sample, T-025 — contextual ML/audit metadata surfaced to API/frontend;
    like `run_id`, excluded from `content_hash` — ADR-0007)* · **check_coverage?**
    *(`models.CheckCoverage` — WS-01 PR2, 2026-07-12: `{checks_expected, checks_ran,
    not_examined, categories_ran, categories_not_run}` over a fixed
    provenance/metadata/qc/contamination/identity/pipeline catalog, computed by
    `rules.compute_check_coverage(artifacts, findings)` — a category counts as "ran" when its
    artifact is present OR it emitted a finding, so a clean finding-less QC gate still counts as
    examined. Deterministic, un-hashed contextual metadata like `metric_values[]` — never sets a
    verdict. **Contamination now genuinely flips to "ran" when examined (fixed 2026-07-13,
    `b03d1fa`)**: `rules._examined_metric_categories` checks whether the sample's metrics map
    actually carries a `contamination.*` registry key (present = examined = ran, pass **or**
    fail) — a separate mechanism from the generic `QCThreshold` loop, which still tags every
    finding `Category.QC` never `Category.CONTAMINATION` (that part of the prior note holds; the
    fix does not touch finding categories). **Identity stays honestly "not examined"** — no
    NGSCheckMate/`.selfSM`-equivalent parser exists, so no sample can ever carry an `identity.*`
    metric. Verified directly: `tests/test_gate.py::test_check_coverage_flips_contamination_when_freemix_is_examined`.
    See [qc_metrics.md](qc_metrics.md#fail-closed-rules--qc-missing--qc-expected-key-ws-01-2026-07-12)
    for the full account (incl. the 2026-07-12 as-shipped state this corrects). Backs the honest
    "N ran / M not examined" card prose that replaced the old "all checks passed" claim.)*
    · generated_by · model ·
    **content_hash** · created_at · supersedes_card_id?. *(`is_current` is a projection, not
    stored truth.)*

### Provenance / events (append-only — ADR-0002)
11. **ProvenanceEvent** (`evt_`) — event_type *(vocabulary below)* · analysis_run_id ·
    run_id · sample_id · ticket_id? · actor (`system|rule_engine|agent|human:<id>`) ·
    **inputs[]** / **outputs[]** (EntityRef) · payload (typed by event_type) ·
    **trace_id** · **correlation_id** · ts.
12. **EntityRef** — entity_type (`artifact|metric|finding|card|ticket|experience|knowledge`) ·
    id · content_hash? *(required for artifacts; present on immutable findings/cards; null on mutable)*.

### Agents / corpora (ADR-0009) — MVP-deferred
13. **TriageNote** — finding_id/signature · agent (`qc_triage|pipeline_repair`) ·
    **addresses_rule_ids[]** / **addresses_signatures[]** *(the rule_ids and semantic finding
    signatures this note addresses — both existed on `triage/models.py` since T-015; this doc
    entry was missing `addresses_signatures` until a 2026-07-11 sweep caught the frontend
    `types.ts` mirror had also drifted behind it, T-132)* ·
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
       (non-PROCEED) cards notify; live Slack send is opt-in (`BAYLEAF_SLACK_LIVE`) and
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
`ticket.actioned` · `resolution.recorded` · `data.exported` *(one per de-identified share/report
egress — `POST /api/runs/{id}/share`, ADR-0018 D3, 2026-07-11; an egress transform only, never a
gate input — see [provenance.md](provenance.md#the-ledger) for why it lives in a separate,
gitignored `share.events.jsonl` rather than the gate's own `EventLedger`)*.

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
6. **Execution-job bookkeeping (`api/job_store.py`, 2026-07-11) is API-layer, not a core record.**
   Unlike items 1–5 above (which mirror `src/bayleaf/models.py`), a job (`kind`, `run_id`,
   `status: queued|running|held|scheduled|complete|failed|lost`, `error`) tracks a background
   driver launch that `api/routers/intake.py`/`pipeline_run.py` triggers — it never enters
   `RunArtifacts`, `MetricValue`, or the JSONL ledger, and it is mutable (not content-hashed /
   immutable like the records above). `lost` is a restart-recovery terminal status: a job whose
   owning process died with no result dir on disk. **`held` and `scheduled` are operator-parked
   states (ADR-0021, `HELD_STATUSES`):** a `mode=hold`/`mode=schedule` submit registers the job
   without launching a driver, and `POST /api/runs/{id}/release` transitions it → `running`. A
   parked job has no thread and no data dir, so restart-reconcile treats it as parked and **never**
   mis-reconciles it to `lost` the way a genuinely died-mid-run `queued`/`running` job is.
   `scheduled` stores a `scheduled_at` but is **honest-but-inert** — no timer/cron auto-fires it; an
   operator releases it manually (the time-based auto-release scheduler is a deferred seam, ADR-0021). Persisted via the SAME jsonl/sqlite pluggable-store shape as the
   product stores above, but deliberately with **no Postgres backend** (node-local scratch, not
   shared product state) — see [ADR-0016 item 8](../adr/ADR-0016-postgres-port.md). **Additive,
   2026-07-11 (W4 continuation):** `IntakeStatus` (`api/routers/intake.py`) gains
   `samples: list[SampleStatus]` — `{sample: str, status: str}` per submitted sample, mirroring
   the run-level `status` for every `processed` sample (`queued`→`running`→`complete`/`failed`)
   while a `skipped` sample (no panel reads on disk) is frozen at `skipped`. An older persisted
   job with no `samples` key yields `[]`, not an error — the field is additive, so nothing that
   read the pre-existing `processed_samples`/`skipped_samples` string lists breaks. This is
   per-sample UI progress, not a new ledger/DB record; see
   [functional.md REQ-F-095](../requirements/functional.md).
7. **`LibraryEntry` (`api/library_store.py`, 2026-07-11, T-135) is API-layer product state, not a
   core record — the accept-time counterpart to item 6's job bookkeeping.** A `LibraryEntry` wraps
   a node-authoring `NodeProposal`
   ([functional.md REQ-F-096](../requirements/functional.md)) a human has **accepted**:
   `{id, tool, version, status: "draft"|"approved", submitted_by, created_at, updated_at, proposal}`.
   `proposal` is the embedded `NodeProposal` as-is (ports/locators/citations/version stamps —
   **metadata only**, never a `script:`/`stub:` command body); `status` starts and today stays
   `"draft"` (no code path yet sets `"approved"`). Each accept **appends** a fresh, immutable entry
   (`add`/`get`/`list`, no in-place update) — mint-per-accept, not upsert-per-tool. Persisted via
   the same pluggable-store shape as items above (`LibraryStore` Protocol,
   `JsonlLibraryStore`/`SqliteLibraryStore`, `BAYLEAF_LIBRARY_STORE=jsonl|sqlite`,
   degrade-to-JSONL), but — like the job store — **deliberately with no Postgres backend**: a small,
   node-local corpus of accepted drafts, not shared product state
   ([ADR-0016 item 9](../adr/ADR-0016-postgres-port.md)). Never enters `RunArtifacts`,
   `MetricValue`, or the JSONL provenance ledger, and never re-enters the gate (ADR-0001) — a
   library entry cannot set or move a verdict/finding/confidence by construction (the embedded
   `NodeProposal` has no such field, and `check_conformance()` — see
   [design/agent-authoring-contract.md](../design/agent-authoring-contract.md) — asserts this at
   accept time before an entry is ever stored).

> **`frontend/src/types.ts` is a hand-maintained TypeScript mirror of this contract, not generated.**
> It can drift behind the pydantic source of truth above — a 2026-07-11 sweep (T-132) found and
> fixed five such drifts (`QCThreshold.our_key`/`.required`, `Runbook.trace_failure_statuses`/
> `.route_to_human`, `DecisionCard.metric_values` wrongly marked optional, `IntakeStatus.status`
> too narrowly typed, `TriageNote.addresses_signatures` missing) — none required a Python-side
> change; every field already existed here. Treat a `types.ts` claim as provisional until checked
> against this doc or the model source.

## Invariants

1. Findings are immutable; state lives on IssueSignature/Ticket/ExperienceRecord.
2. IssueSignature identity is **semantic**, decoupled from rule_version.
3. AI is **advisory** — never sets or overrides a verdict (ADR-0001).
4. One DecisionCard per (sample × analysis_run); current-card is a projection.
5. JSONL authoritative; DB projection rebuildable — no dual-write truth.
6. Every Finding/Card cites Evidence traceable to an artifact + hash.
