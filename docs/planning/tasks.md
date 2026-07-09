# Task & Progress Tracker

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-09 (MST) |
| **Purpose** | Top-layer session input (read alongside the ToC): tracks development, timeline, and flags parallel-safe work so non-blocking items can fan out to background agents. |

## Timeline

Due **Mon Jul 13, 2026, 6:00 pm MST** (9:00 pm ET). Day buckets, not hour
estimates — adjusted as we go.

| Day (MST) | Bucket | Focus |
|---|---|---|
| Tue Jul 7 | Design / research | Concept lock, docs, ADRs, Phase 0 |
| Wed–Thu Jul 8–9 | Build | Provenance/event seam, real-QC ingest, AI layer, dashboard |
| Fri Jul 10 | Harden | Eval vs truth data, error handling, security, doc refresh |
| Sat Jul 11 | Demo | Demo plan, one-pager/deck, UI states |
| Sun Jul 12 | Flex | Overflow, agent #2, risks, dry run |
| Mon Jul 13 | Buffer / submit | Final checks; submit before 6 pm |

## How to use

- **Statuses:** `todo` · `in-progress` · `blocked` · `done`.
- **Parallel-safe** = no unfinished dependency and an isolated area of the repo;
  safe to run concurrently or hand to a background agent.
- Keep this current in the same change as the work. It is the shared board across
  sessions — read it (with the [table of contents](../TABLE_OF_CONTENTS.md)) at
  session start to see what is claimable.

## Roadmap (phases)

| Phase | Focus | State |
|---|---|---|
| 0 | Foundation & hygiene (uv, mypy, ruff, hooks) | done |
| 1 | Design capture + provenance/event seam | in-progress |
| Port | Productionization: FastAPI read-API + React frontend (ADR-0014) | in-progress |
| 2 | Persistence + real QC data | in-progress |
| 3 | Scoped agents + real confidence (triage agent T-015 done) | in-progress |
| 4 | Cloud & IaC | wishlist |

## Task board

| ID | Task | Phase | Status | Parallel-safe | Depends on |
|---|---|---|---|---|---|
| T-001 | Documentation workflow + ADRs 0001–0007 | 1 | done | — | — |
| T-002 | `data/qc_metrics.md` (grounded, cited, breadth-first runbook) | 1 | done | yes | — |
| T-002b | Concrete test-data QC profile ✅ — real GIAB HG002 panel reads through the **full** gate (`scripts/gate_giab.py`): `samtools fastq \| fastp` → real Q30 88.2% / dup 0.006% / reads-PF 99.3% + `mosdepth` 55.8× coverage, gated on the four metrics a fastq+BAM actually yields (cluster-PF is run-level SAV, not gated) → PROCEED. Registry normalizes each real value from its declared unit exactly as for a mock run | 2 | done | no | T-017 |
| T-003 | `reference/domain-primer.md` + `reference/glossary.md` | 1 | done | yes | — |
| T-004 | `requirements/{functional,nonfunctional,constraints}.md` | 1 | done | yes | — |
| T-005 | `design/architecture.md` ✅; the system-view slices (context, components, data-flow, interfaces, storage, workflows, deployment) are consolidated into it + the ADRs, not split into stubs (see ToC note) | 1 | done | partial | T-002 |
| T-006 | Config layer / profiles — consolidated into ADR-0005 + architecture.md §Swappable seams (no standalone doc) | 1 | done | yes | — |
| T-007 | Repo + data layout — consolidated into the CLAUDE.md code map (no standalone doc) | 1 | done | yes | — |
| T-008 | Data docs ✅ (provenance.md, schemas.md, metric_registry.md, licensing.md) | 1 | done | yes | — |
| T-009 | `quality/{evaluation,risks}.md` ✅ (+ demo/demo_plan.md) | 1 | done | yes | T-002 |
| T-010 | ADRs 0008–0014 (issue-taxonomy, corpora, ticketing/API, tooling, agent-scoping, gate-architecture, productionization) | 1 | done | yes | — |
| T-011 | Demo-ready ✅: production-framed `README.md` + `demo/run-of-show.md` (timed 5:00 script, pre-flight + fallback ladder) + `demo/one-pager.md` (judge handout) + `make emit-ledger` making the reproduce-from-log wow moment a clean two-command flow | 1 | done | no | T-005 |
| T-012 | Phase 0 tooling: uv + `pyproject.toml` single source, mypy/ruff, hooks (batch full-eval → Phase 2/T-009) | 0 | done | no | — |
| T-013 | Synthetic run generator ✅ (`pipeguard.synthetic`) + GIAB HG002 subset fetch script ✅ (`scripts/fetch_giab_hg002.py`, accessions manifest; real fetch needs the genomics toolchain → T-017) | 2 | done | partial | T-002, T-008 |
| T-014 | Event bus + provenance ledger (in-memory + JSONL; DB projection → T-023 ✅) | 1 | done | no | ADR-0002 |
| T-015 | QC-triage agent (advisory, stub-first, corpus + retrieval, /triage API) | 3 | done | no | T-014 |
| T-015b | Outbound notify port ✅ + wired into `run_gate` (`notifier=`; `NOTIFICATION_EMITTED` events) ✅ + live Slack send behind a `PIPEGUARD_SLACK_LIVE` opt-in, **verified end-to-end against a real workspace** + `python -m pipeguard.notify` demo CLI ✅ | 3 | done | no | T-015 |
| T-016 | Data strategy doc + label mock_run_01 origin | 1 | done | yes | — |
| T-017 | Real GIAB HG002 panel data through the QC gate ✅ (`scripts/gate_giab.py`): `mosdepth --by` on the fetched panel BAM → real 55.8× coverage + 99%/97% breadth → gated (PROCEED, clears the 30× gate) reusing `run_gate` + registry rules unchanged. Fetch also validated (truth VCF + `samtools -X` reads slice). **Fastq metrics (Q30/dup/reads-PF) now added via `samtools fastq \| fastp` → T-002b.** Contamination (verifybamid2) remains | 2 | done | partial | T-002 |
| T-018 | Frontend design brief + clickable prototype (`design/frontend/`) | 1 | done | yes | — |
| T-019 | Align confidence to "omit until grounded" (models.py `confidence` → Optional/None, drop demo Confidence tile, update README:32/:105) — part of the models→schemas.md rework | 1 | done | no | T-008 |
| T-020 | FastAPI read-API over the core (`api/`; production seam, ADR-0010/0014) | Port | done | no | — |
| T-021 | React frontend scaffold + design tokens (`frontend/`; Vite + Tailwind, ADR-0014) | Port | done | no | T-020 |
| T-022 | React screens ✅: run overview · decision cards · triage · provenance · monitoring · settings · review queue · intake/preflight (all prototype screens built) | Port | done | partial | T-021 |
| T-022b | Frontend **1:1 fidelity migration** ✅ — rebuilt all 8 screens (§1–§8) on the light content tokens to match the maintainer handoff (`design/frontend/`), verified screenshot-by-screenshot vs the prototype. Run-scoped Intake (§2) + Agent triage (§6, new) routes like Provenance; §4 review-queue tickets w/ reviewer-vs-approver RBAC + `rule_id`-keyed recurring-issue banner; §7 monitoring + §5 provenance compute-DAG. Legacy dark tokens removed. Screens state their data boundary (no fabricated InterOp/compute artifacts) | Port | done | yes | T-022, T-037 |
| T-023 | SQLite persistence: Repository port + event→row projector + rebuild-db (ADR-0002/0003) | 2 | done | no | T-014 |
| T-024 | Metric registry as code (`metrics/`; registry.yaml + typed loader + `MetricValue` + normalization, per metric_registry.md) — additive slice ✅ | 2 | done | partial | T-008 |
| T-025 | Metric registry on the critical path ✅ (step-by-step): QCMetrics→MetricValue mapping (`metrics/mapping.py`) → runbook keys on `our_key` in canonical decimals + units contract in schemas.md → rules gate on `normalized_value` (verdicts byte-identical; display renders back to raw units via `registry.denormalize`) | 2 | done | no | T-024 |
| T-026 | Restructure agents into `agents/<scope>/` — **deferred until agent #2 (pipeline-repair, ADR-0012) lands** (one agent doesn't justify the folder). Trigger: move `triage/` → `agents/triage/` + `agents/pipeline_repair/`. **Keep `synthesis/` (narration) and `notify/` (port) OUT** — they aren't agents (ADR-0001). Don't do it mid-dev on other tasks (import-path churn). | 3 | todo | no | T-015 |
| T-027 | Read-API policy + telemetry seams ✅ — `GET /api/runbook` (flattened QC thresholds, disclaimer + `units_note`: canonical-unit gates, illustrative-not-clinical) + `GET /metrics` (hand-rolled Prometheus text exposition; verdict/gate counts; no new dep) + frontend `MetricsPanel` surfacing per-sample `metric_values` on the card + Settings display-unit fix (canonical→display; relative borderline band). Both agent branches adversarially reviewed, fixes folded | Port | done | no | T-020, T-025 |
| T-028 | Design capture ✅ — agent-layer hub [`design/agents.md`](../design/agents.md) (roster + shared invariants + intake checklist) + data-platform/export/run-browser/archivist design [`design/data-platform-and-archivist.md`](../design/data-platform-and-archivist.md) (draft for review; tiered already-built/build-now/target-state; 7 open questions) | 1 | done | yes | — |
| T-029 | NGS analysis-output **layout** convention ✅ — expanded data-platform §3 (3.0–3.6) + Appendix C: a fact-checked tool-output catalog (10 stages, `(VERIFY)`-tagged for ungrounded sarek names) + artifact→disposition map (GATE-READ / FLATTEN-INPUT / INDEX-ONLY) + a coherent grouped tree + a storage policy (panel scale → nothing to delete; BAM→CRAM deferred; keep `fastp.json` as the QC keeper). Additive; the flat `run/` five-CSV ingest stays frozen. Surfaced a naming nuance: `pct_reads_identified` is a fastp pass-filter rate, not a barcode-ID metric (maintainer decision pending) | 2 | done | no | T-017 |
| T-030 | BUILD-NOW data slice (**approved D2, starting**) — read-only `GET /api/export` over the in-memory cards (`grain=decision` CSV + `grain=feature` JSONL = the ML corpus; single file on demand, not masses of files — D3) + month-scoped `RunsBrowser` + download button. `api/`+`frontend/` only; zero core change | Port | in-progress | no | T-028 |
| T-031 | Variant-gate substrate ✅ (**design done**, Appendix D) — layered **CMRG-spine panel** (CMRG ships its own truth VCF+BED; two-truths/two-BEDs routing so each region grades against its own answer key) + **caller-agnostic VCF ingest** + a load-bearing **framing contract** (banned phrasings; ClinVar is fixture-selection/annotation only, **never a runtime gate input**). **Build-now-if-time (zero core change):** `gate_giab.py --call` (bcftools on the on-disk panel BAM) → **EVAL-030** (hap.py/`isec` P/R/F1 vs NIST truth). **Phase 2:** `parse_vcf` + the variant **rules** (the registry already declares inert `variant.*` keys — §8). Guardrail: HG002 is a benchmark genome, not a patient; variants are ClinVar-labeled **test fixtures** | 2 | done | no | T-017 |
| T-032 | Config file for tool **output paths** (artifact-kind → path/glob; typed pydantic-settings + YAML like `metric_registry.yaml`; tolerant; default profile = the frozen five-CSV `run/` contract). Config layer [ADR-0005](../adr/ADR-0005-config-layer-and-profiles.md); the machine-readable seam a canvas (#11) would generate | 2 | todo | partial | T-029 |
| T-033 | Pipeline **run-state capture** → mission-control (per-step execution state, start→end, as ledger events → dashboard projection). Interact with Nextflow, don't reinvent (wishlist #20, Re:1a) | 3 | todo | no | — |
| T-034 | Rename `pct_reads_identified` → its fastp pass-filter semantics (metric registry key + `mapping.py` + runbook + docs). Document-now, rename-eventually (D14) | 2 | todo | yes | T-025 |
| T-035 | Notify webhook adapters: Teams + Discord (stdlib POST, SlackNotifier shape, offline-default, live opt-in) — Jira ticket-create deferred to ticketing phase | 3 | done | yes | T-015b |
| T-036 | Telemetry connector bundle (W17): vendor-neutral pull/scrape configs — Datadog OpenMetrics + Prometheus + OTel Collector (+ optional compose) — over the built /metrics seam, plus docs/ops/telemetry-connectors.md; defer in-app push SDK/OTLP exporter ✅ (branch `feat/telemetry-connectors`, unmerged) — configs in `deploy/telemetry/`, ops doc + ToC/wishlist crosslinks; config+docs only, no core/api change, no new dep; no-PHI claim verified against `_render_prometheus` | 3 | done | yes | T-027 |
| T-037 | Provenance canvas ✅ — built as the §5 **compute DAG** (intake→demux→qc→align→variant→gate) with the 3 gate checkpoints, per-stage status from real `gate_results`, and a data-I/O drill-in (name · sha256 · size · origin). New read-API `GET /api/runs/{id}/artifacts` grounds it: real streamed sha256 + on-disk size + run origin tag, **8 MiB hash cap** so raw reads are size-listed not slurped, SampleSheet→demux. Stages we don't execute (align/variant) shown as "not run in this build". **Supersedes** the earlier event-swimlane approach (W10) | Phase 2 (frontend) | done | yes | none |
| T-038 | Metric-catalog read-only view: GET /api/metrics/registry (all 20 registered metric types + gated-vs-registered flag) + Settings "Metric catalog" panel; read-only, zero core change ✅ (merged, 484cc5e) | Port | done | yes | T-024, T-027 |
| T-039 | ArtifactStore port + LocalArtifactStore (zero-dep) + guarded S3ArtifactStore (OFF by default, lazy boto3 in new [s3] extra, PIPEGUARD_S3_LIVE opt-in, degrade-to-local) + run_gate_from_store convenience; realizes ADR-0003 §3 artifact-store wishlist. Defer Box/Drive/OneDrive/DNAnexus/Databricks/Snowflake/BigQuery/Redshift connectors (scope-only) | 3 | done | yes | ADR-0003, T-015b |
| T-040 | Config-driven de-id policy at the export seam ✅ (`api/deid.py`: per-field DROP/HASH/GATE_BY_ORIGIN/PASSTHROUGH + origin-gated, pseudonymized `include=identity` cohort-key opt-in, `X-PipeGuard-Deid-Policy` header; routed through `_decision_rows`/`_feature_rows`; `api/` only, no new dep, stdlib hashlib; demo seam, NOT HIPAA; non-laundering §5e enforced — origin read-only, guarded set fixed) — branch `feat/deid-export-policy`, unmerged | Port | done | yes | T-030 |
| T-041 | Containerize API + built frontend (deploy/Dockerfile.api multi-stage + docker-compose + .dockerignore; env-configurable DATA_ROOT/CORS + optional StaticFiles mount in api/main.py) — the ADR-0003 containerization prerequisite; ship target-state Terraform (ECR + App Runner) UNAPPLIED, HealthOmics deferred to T-033 | 4 | todo | yes | — (api/ + frontend/ already built) |
| T-042 | In-app feedback capture ✅ (W12) — the app's **first write endpoint**, off the gate. `api/feedback.py` (FeedbackContext/In/Ack, `extra="forbid"` PII guard + disjoint-target model_validator, server-fixed env JSONL, locked json.dumps writer) + `POST /api/feedback` (201; server-authored id/received_at/origin-via-`_run_origin`; OSError→503 no-leak; CORS +POST). Two UI surfaces: per-decision thumbs footer (`DecisionFeedback`, keyed to verdict+gate+rule_ids+content_hash) + a global product FAB (`FeedbackWidget`, mounted in Layout so every screen stays byte-identical). Designed via a 3-angle panel (scoped hybrid) + adversarially reviewed (security/correctness/guardrails clean). 9 new tests; gitignored store; no core change | Port | done | yes | T-020, T-021 |
| T-043 | Postgres port ✅ (ADR-0016) — realize the `Repository` port's "SqliteRepository → Postgres later" seam + move feedback into a DB, all **OFF by default** (offline demo unchanged; mirrors the S3 seam). `PostgresRepository` (ON CONFLICT upserts, JSONB/TIMESTAMPTZ, pipeguard_meta version) + `get_repository()` (PIPEGUARD_REPOSITORY, degrade-to-SQLite, never leaks the DSN) + `rebuild-db` targets either backend. Feedback → pluggable `FeedbackStore` (jsonl/sqlite/postgres, `api/feedback_store.py`) with its own `feedback` table (never the Repository); SqliteFeedbackStore proven E2E in tests. Required `source` trace field (#3a). Advisory **feedback agent** (`api/feedback_agent.py`, stub/claude, PII-safe aggregate-only Claude path, #3b). `[postgres]` extra (psycopg) + mypy override + `deploy/postgres/docker-compose.yml`. FAB made icon-only-on-hover (#1). Adversarially reviewed (4 read-parity fixes: UTC-normalized TIMESTAMPTZ, seq insertion-order). **Validated live against real Postgres 16** (`tests/test_persistence_postgres_live.py`, compose-gated + skip-safe): projection byte-parity vs SQLite, idempotent replay, feedback JSONB round-trip — all pass, no adapter bug. 225 tests + 3 live-skipped | Port | done | yes | T-042, ADR-0003 |
| T-044 | Pipeline Builder MVP ✅ (#11 / W11) — the editable superset of the Provenance canvas (`frontend/src/screens/PipelineBuilder.tsx`): sub-header toolbar (Edit/View · profile switcher · Tidy/Validate/Emit) + three-pane workspace (palette · dot-grid H-scroll canvas · node inspector) + a validate/emit console with a live `run_layout.yaml` preview across default/giab_panel/sarek. Renders the 7 seeded germline tool nodes (pg-status badges, typed ports, reference hollow rings) + edges + reference nodes + the deterministic-ingest band + the terminal locked gate + the port-less advisory QC-triage agent. Composes-never-executes; hard invariants shown as visible guarantees. Built from the refreshed handoff; reuses the shell + tokens. Nav item under Configure | Port | done | yes | T-018, T-022b |
