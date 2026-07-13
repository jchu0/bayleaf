# Documentation — Table of Contents

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-13 (MST) — **public-readiness pass:** added [`audit/README.md`](../audit/README.md) (frames the `audit/` dir as acted-on, point-in-time snapshots — findings tracked in `tasks.md`, not current-state truth); a README **"engineering archive"** pointer routing casual readers past `journal/` + `audit/`; and **pinned the Vite dev port to :5173** (`strictPort`, `frontend/vite.config.ts`) so the code's already-hardcoded-5173 assumptions (the API CORS allowlist, the Admin `/metrics` origin swap) can't silently break when Vite drifts to :5174. Also **purged stale Streamlit references** from the canonical docs (the Streamlit MVP was removed in `7dab033`; `app/`, `pyproject.toml`, `uv.lock` already clean): ADR-0014 **amended** (decision reversed, original preserved), REQ-F-043/NF-042/NF-050/C-003 + `architecture.md` (incl. the component-map diagram) / `one-pager.md` / `run-of-show.md` / `nf-core-conventions.md` / `telemetry-connectors.md` / `CLAUDE.md` updated; dated `journal/` + `audit/` snapshots left **as-is** (historical record). Also ran a **doc-freshness audit** (7 read-only agents cross-checking docs vs current code) and applied **25 fixes across 15 docs**: the test census (789 tests / 65 files — was `727/55`, and a stale `320/19` in the judge one-pager), the `route-to-human → flag-for-review` rename the CLAUDE.md code map had missed, the **12 → 13** operator-screen/PageId count (System Agents page) across 6 docs, `NODE_W 232 → 320`, the Accept-to-library button (docs said deferred; it shipped) across 4 docs, EventType 10 → 12, ADR-0019 Slice-1-realized, and data-contract/registry accuracies; dated `journal/`+`audit/` archives and milestone records left as history. Also **removed `docs/demo/`** (demo_plan / run-of-show / one-pager) — inbound links in `README`, `requirements/{functional,nonfunctional,constraints}.md`, `quality/{evaluation,risks}.md`, and `DOCUMENTATION_HABITS.md` cleaned (the §Fallbacks traces repointed to REQ-NF-042); `journal/`+`audit/`+`tasks.md` archive links left as history. Prior same-day: **agent-hardening design set (Proposed):** ADR-0023 (advisory vs tool-agent + action boundary), ADR-0024 (scope-by-wiring file access), ADR-0025 (versioned/reversible tool-card config); design docs for the System-agents chat surface, per-agent capability upgrades, and the monitoring tool-agent. Label casing → sentence case (Sample metadata, System agents; UIC-21). See [journal/2026-07-13-agent-hardening-design.md](journal/2026-07-13-agent-hardening-design.md). Prior same-day: repo-wide rename **route-to-human → flag-for-review** (`VAR-FFR-001`, `FlagForReviewPolicy`; the variant-interpretation ToC row + ADR-0018/qc_metrics/schemas/evaluation/functional updated); operator **page-name simplification** (Sample accessioning→Sample Metadata, Submit samplesheet→Samplesheet, Intake gate→Intake, Decision cards→Decisions, Agent triage→Triage, Pipeline builder→Pipeline) + a new **System Agents** page (repair+archivist split off Triage) — labels match `frontend/src/access.ts`. See [journal/2026-07-13-flag-for-review-rename-and-page-naming.md](journal/2026-07-13-flag-for-review-rename-and-page-naming.md). Prior: 2026-07-12 (MST) — ADR-0022 agent-observation-binding (Builder agent-attachment is a persisted, read-only `AgentBinding` off the compiled graph; a scoped, de-identified node-read path; pipeline-vs-system agent taxonomy); `bayleaf` rebrand (product renamed; the Python package/`BAYLEAF_*` env vars stay `bayleaf`); ADR-0021 operator-gated/scheduled processing; ADR-0020 operator-authored custom-script processes + sandboxed `GET /api/files` browse + compiler robustness hardening; node-author corpus **9** (NGSCheckMate retired-but-pinned); dated build chronology relocated to [HISTORY.md](HISTORY.md) |
| **Audience** | all (contributors and Claude Code) |

**Start here.** This index is the map of what exists — and its
**[Doc-update map](#doc-update-map)** is the authority on which docs a change obligates.
**Read lean, write complete:** open only the files relevant to your task (bulk-load only when
it genuinely needs broad context), but before you finish, sweep the Doc-update map and update
every doc your change made stale. Conventions: [DOCUMENTATION_HABITS.md](DOCUMENTATION_HABITS.md).
Claimable work: [planning/tasks.md](planning/tasks.md).

Status legend: ✅ written · 🚧 in progress · 📝 planned.

## Planning
| Doc | Status | Purpose |
|---|---|---|
| [planning/tasks.md](planning/tasks.md) | ✅ | Phases + task board with parallel-safe flags |

## Reference (learn the domain)
| Doc | Status | Purpose |
|---|---|---|
| [reference/domain-primer.md](reference/domain-primer.md) | ✅ | Rare-disease panels, GIAB HG002, gnomAD, ClinVar — for non-specialists |
| [reference/glossary.md](reference/glossary.md) | ✅ | Terms across bioinformatics, software, and clinical |

## Requirements (what the system must do)
| Doc | Status | Purpose |
|---|---|---|
| [requirements/scope-and-wishlist.md](requirements/scope-and-wishlist.md) | ✅ | In-scope, wishlist (with readiness), out-of-scope |
| [requirements/functional.md](requirements/functional.md) | ✅ | Capabilities (REQ-F-NNN) |
| [requirements/nonfunctional.md](requirements/nonfunctional.md) | ✅ | Reliability, provenance, security, performance (REQ-NF-NNN) |
| [requirements/constraints.md](requirements/constraints.md) | ✅ | Timeline, budget, licensing, domain-safety (REQ-C-NNN) |

## Design (how it is built)
| Doc | Status | Purpose |
|---|---|---|
| [design/architecture.md](design/architecture.md) | ✅ | System shape: three gates, component map, data flow, invariants, swappable seams, deployment |
| [design/agents.md](design/agents.md) | ✅ | Agent-layer hub: roster, shared invariants (captured once), intake checklist for new agent ideas |
| [design/agent-authoring-contract.md](design/agent-authoring-contract.md) | ✅ | Boundaries MD for how an *authoring* agent (card/tool authoring, or the general convention for adding a 7th/8th advisory agent) is built and constrained — what templates it may fill, Nextflow-integration rules, UI dos/don'ts; the node-authoring agent's `GET /api/builder/node-proposal` is its first realized instance, now joined by a backend-only `POST /api/builder/node-proposal/accept` → a governed library store + a `check_conformance()` harness (2026-07-11, T-135) |
| [design/data-platform-and-archivist.md](design/data-platform-and-archivist.md) | ✅ | Data-platform + export + run-browser + Archivist agent design (draft for review; tiered already-built / build-now / target-state) |
| [design/system-agents-chat.md](design/system-agents-chat.md) | 🚧 | **Built (P1 core, 2026-07-13)** — the System agents page is a **chat surface** (left agent-select panel + chat window over pipeline-repair/archivist) with **structured, ML-minable chat history** (`api/chat_store.py`; view-scoped archive/delete = soft-delete, records retained). Backend: `api/chat.py` + `api/agent_chat.py` (stub-first, live per the agent's env flag) + `api/routers/agent_chat.py`; UI: `frontend/src/screens/SystemAgents.tsx`. Advisory only (ADR-0001); live-verified on pipeline-repair. **Deferred:** archivist cross-run DB retrieval + scope-by-wiring grounding. |
| [design/agent-capabilities.md](design/agent-capabilities.md) | 🚧 | Per-agent grounding/authoring upgrades. **§1 archivist read-only cross-run DB retrieval BUILT** (P3, 2026-07-13, `api/archivist_retrieval.py`; projection-first + run-dir-derivation fallback; grounds the archivist chat; live-verified). **§2 pipeline-repair docs corpus BUILT** (P3, 2026-07-13, `pipeline_repair/knowledge/bayleaf_system.jsonl` + catalog-derived tool docs via `load_system_corpus`; grounds the repair chat; live-verified) — its **issues+resolutions half stays deferred** (needs the monitoring tool-agent). **§3 node-author BUILT** (P3, 2026-07-13): Accept-to-library button (`AuthorToolNodeModal` → `POST .../accept`, confirm+role-gated) **and scaffolds-as-assets** (`node_author/scaffolds.py` → `GET .../node-proposal/scaffolds` + a Builder "Starter scaffolds" viewer; DRAFT ProcessSpec + Nextflow process, command left a TODO). **Deferred:** §3 doc-upload → schema-delta + inline-edit/draft→approve + persisting scaffolds as versioned assets; §2 issues+resolutions half (→ monitoring tool-agent). All advisory. |
| [design/monitoring-agent.md](design/monitoring-agent.md) | 🚧 | **Proposed** — the monitoring **tool-agent** (ADR-0023): opt-in graph node that watches a run, classifies anomalies, **auto-retries or reports per operator-set issue-class policy** (versioned, ADR-0025), logs every issue to the store pipeline-repair consumes. Leans on Nextflow `errorStrategy` where it can; hard action boundary. |
| [design/node-authoring-agent.md](design/node-authoring-agent.md) | ✅ | Roster agent #5 — **built (T-046), narrower than proposed**: retrieval over a **9-card** curated corpus (verified `load_tool_card_corpus()`, 2026-07-12; was 11 — retired the unwired `source_truth_vcf` card, then NGSCheckMate **retired-but-pinned** from the proposable set, its `ngscheckmate` KIND kept in the vocabulary) from a natural-language request. A read-only `api/` endpoint + Builder wiring shipped 2026-07-11 (W2, T-127); accept→library, a conformance harness, and a structured `nextflow_schema.json` doc-drop importer shipped backend-only the same day (W2 backend, T-135) — the Builder's own "Accept to library" button, the `draft→approved` transition, and the free-text `--help`/README importer half stay deferred |
| [design/variant-interpretation.md](design/variant-interpretation.md) | 🚧 | Variant interpretation & reporting design (ADR-0018) — advisory ClinVar/gnomAD evidence + review-ordering + a cited `RunReport` + a PHI-scrub Share window; four pieces built and (2026-07-11) demonstrated end-to-end (flag-for-review `VAR-FFR-001` fires against a committed run; the conservative de-id module is wired to a narrower-than-designed `POST /api/runs/{id}/share` egress; a `RunReport` view; a read-only `GET /api/runs/{id}/variants` per-variant table over the `VariantCall`/ClinVar fields only), the rest (agent, the full `api/report.py` projection, gnomAD/inheritance-fit evidence, the full Share window) still design-only |
| [design/frontend/frontend-design-brief.md](design/frontend/frontend-design-brief.md) | ✅ | UI design brief (v1 + v2 additions) — the stable spec |
| [design/frontend/pipeline-builder-brief.md](design/frontend/pipeline-builder-brief.md) | ✅ | Wishlist #11 flagship — pipeline-builder design handoff (node/agent canvas → run-layout config), paste-and-go for a design tool |
| [design/frontend/handoffs/](design/frontend/handoffs/) | ✅ | Dated review→design handoff deltas (episodic) |
| [design/frontend/](design/frontend/) | ✅ | Frontend prototype (`bayleaf.html`) + design README |
| [design/ui-conventions.md](design/ui-conventions.md) | ✅ | Durable cross-cutting UI/product convention registry (`UIC-N` ids) — the single place a maintainer rule is recorded once and implemented against |
| [design/builder-cards/](design/builder-cards/) | ✅ | Pipeline-Builder card-design convention (`README.md`) + 7 per-tool port specs, grounded in real tool I/O — a **design target** the shipped `BuilderCanvas` implements a subset of (see its §5) |
| [design/nextflow-codegen.md](design/nextflow-codegen.md) | ✅ | Card-graph → Nextflow (DSL2) compiler (`src/bayleaf/nextflow/`): the tool catalog, wiring rules, the reference-index staging, the `pipelines/germline/` drift-guarded reference pipeline, the `POST /api/pipelines/compile` + Builder "Export to Nextflow" UI, and the now-Nextflow-first intake driver — realizes [ADR-0003](adr/ADR-0003-deployment-agnostic-ports.md); the driver's post-run parse is now N-sample capable offline (2026-07-11, W4 continuation), live multi-sample run still unverified. **Operator-authored custom-script processes ([ADR-0020](adr/ADR-0020-operator-authored-custom-processes.md), 2026-07-11)** now sit alongside the curated catalog — a human-supplied `script:` body compiles to a real, honestly-labelled process, wired like a catalogued tool, catalog never consulted; the compiler was robustness-hardened (Groovy-injection escaping of interpolated values, a File-input source fix, and collision / fan-in / duplicate-emit / port-drift guards). **Operator-gated / scheduled processing ([ADR-0021](adr/ADR-0021-operator-gated-scheduled-pipeline-processing.md), 2026-07-12)** lets intake run an approved *authored* pipeline by name and stage/schedule a run (`immediate`/`hold`/`schedule` + release). A sandboxed `GET /api/files` browse lets the Builder pick locator inputs from an allowlisted tree (path-traversal-guarded, read-only) |

> **Consolidated, not split.** The system-view slices once planned as separate docs
> (system-context, components, data-flow, interfaces, storage, workflows, deployment,
> configuration, structure) live as sections of
> [architecture.md](design/architecture.md) plus the ADRs — config/profiles →
> [ADR-0005](adr/ADR-0005-config-layer-and-profiles.md); ports/interfaces →
> [ADR-0003](adr/ADR-0003-deployment-agnostic-ports.md); storage/ledger →
> [ADR-0002](adr/ADR-0002-event-driven-core-provenance-ledger.md) +
> [provenance.md](data/provenance.md); repo/data layout → the code map in `CLAUDE.md`.
> We chose one coherent system doc over near-duplicate stubs (MVP-first); split a slice
> back out only if it outgrows its section.

## Decision records (ADR)
One decision per file, in [adr/](adr/). Self-identifying `ADR-NNNN-*` names.

| ADR | Title |
|---|---|
| [ADR-0001](adr/ADR-0001-deterministic-gate-advisory-ai.md) | Deterministic gate, advisory AI |
| [ADR-0002](adr/ADR-0002-event-driven-core-provenance-ledger.md) | Event-driven core with a provenance ledger |
| [ADR-0003](adr/ADR-0003-deployment-agnostic-ports.md) | Deployment-agnostic ports & adapters |
| [ADR-0004](adr/ADR-0004-vcf-first-giab-substrate.md) | VCF-first inputs on a GIAB substrate |
| [ADR-0005](adr/ADR-0005-config-layer-and-profiles.md) | Config layer and deployment/agent profiles |
| [ADR-0006](adr/ADR-0006-ai-off-by-default-fallback.md) | AI off by default with a deterministic fallback |
| [ADR-0007](adr/ADR-0007-ml-ready-structured-outputs.md) | ML-ready structured outputs |
| [ADR-0008](adr/ADR-0008-issue-taxonomy-suppression-escalation.md) | Issue taxonomy, suppression, escalation |
| [ADR-0009](adr/ADR-0009-corpora-retrieval-upskilling.md) | Knowledge + experience corpora, retrieval upskilling |
| [ADR-0010](adr/ADR-0010-ticketing-notify-read-api.md) | Ticketing: cards, notify ports, read API |
| [ADR-0011](adr/ADR-0011-tooling-and-reproducibility.md) | Tooling and reproducibility |
| [ADR-0012](adr/ADR-0012-agent-scoping-model-tiering.md) | Agent scoping and per-agent model tiering |
| [ADR-0013](adr/ADR-0013-gate-architecture-verdict-policy.md) | Gate architecture (preflight/QC/variant) + surface-and-decide verdict policy |
| [ADR-0014](adr/ADR-0014-productionization-fastapi-react.md) | Productionize with FastAPI + React (**amended 2026-07-13**: the Streamlit fallback was removed; the offline stub-first stack is the demo) |
| [ADR-0015](adr/ADR-0015-layered-data-contract.md) | Layered, immutable data contract across the gate (the data-structure decisions + why) |
| [ADR-0016](adr/ADR-0016-postgres-port.md) | Postgres port (guarded, off-by-default): the `Repository` Postgres adapter + five pluggable jsonl/sqlite/postgres off-gate stores (feedback/pipeline/review/settings/share) + a sixth and seventh, jsonl/sqlite-only stores — the durable job store (`api/job_store.py`) and the node-author library store (`api/library_store.py`, T-135) — neither with a Postgres adapter by design (node-local scratch/corpus, not shared product state) |
| [ADR-0017](adr/ADR-0017-identity-rbac-authoring-lifecycle.md) | Identity + RBAC (dev shim) + the draft→approve authoring lifecycle across pipeline/settings/review stores |
| [ADR-0018](adr/ADR-0018-variant-interpretation-advisory-evidence.md) | Variant interpretation as advisory cited evidence + heuristic review-ordering (NOT a clinical decision engine); the report + PHI-scrub share seam ([design](design/variant-interpretation.md)) |
| [ADR-0019](adr/ADR-0019-pipeline-versioning-run-pinning-edit-lock.md) | 🚧 Proposed — pipeline versioning + run→{name,version} pinning + edit-lock lifecycle (locked while a run is active, editable→new-version when complete; sample provenance immutable); git-versioned model, versioned-store implementation, git-backing as the production seam |
| [ADR-0020](adr/ADR-0020-operator-authored-custom-processes.md) | Accepted — operator-authored custom-script Nextflow processes: a HUMAN supplies a verbatim `script:` body on a Builder card (`NfNode.script`), compiled to a real process wired like a catalogued tool (catalog never consulted); four-way safety (W1 approval gate before any run · honest label on card + process · agents stay metadata-only, the human authors the script · core never executes); blank script → `CompileError`, never fabricated |
| [ADR-0021](adr/ADR-0021-operator-gated-scheduled-pipeline-processing.md) | Accepted — operator-gated, scheduled sample processing on authored pipelines: intake (`POST /api/runs`) can run an operator-**authored**, approver-blessed pipeline by name (one shared approval gate + compile path with Builder-Run, `api/authored_pipeline.py`; unknown/unapproved → 409) and a processing `mode` (`immediate`/`hold`/`schedule`) with `POST /api/runs/{id}/release`; `held`/`scheduled` are operator-parked states (never mis-reconciled to `lost`). **The time-based auto-release scheduler is a DEFERRED seam — no timer/cron fires a scheduled run; an operator releases it manually.** |
| [ADR-0022](adr/ADR-0022-agent-observation-binding.md) | Accepted — Builder agent-attachment is a persisted, read-only **`AgentBinding {agent, node, grants}`** (replaces the ephemeral `advisoryAttach` set) stored in a **sibling `graph.agent_bindings` envelope key the Nextflow compiler never dereferences** — a graph compiles byte-identical with/without a binding (compose ≠ execute by construction, ADR-0001/0003). Grants are least-privilege (`outputs` default; `logs` opt-in + de-identified via `api.deid.scrub_text`). A scoped node-read path (`GET /api/runs/{id}/nodes/{node}/observations`, Phase 4, `gather_node_observations()` = the triage-consumption seam) backs it; pipeline-vs-system agent **taxonomy** (node-attachable QC-triage/Node-authoring stay in the Builder; run-/org-scoped Pipeline-repair/Archivist move to Agent-triage launchers). Deferred: agent consumption, UI display, authored-graph node→file linkage. |
| [ADR-0023](adr/ADR-0023-agent-taxonomy-and-action-boundary.md) | **Proposed** — two agent classes: **advisory agents** (unchanged, off the gate) vs. **tool-agents** wired into the pipeline graph that MAY take *bounded operational actions* (auto-retry) under a hard **action boundary** (never a verdict/finding/data write). The monitoring agent is the first tool-agent; per-issue-class policy on its card, capped + logged to an issue store that feeds pipeline-repair. |
| [ADR-0024](adr/ADR-0024-scope-by-wiring.md) | **Accepted — enforcement shipped (P2, 2026-07-13).** An agent's file access = the tools it is **wired to** (server-enforced, advancing ADR-0022 from advisory hint to enforced): a run's executed-graph bindings are snapshotted at launch (`api/agent_binding_store.py`), and `GET .../nodes/{node}/observations?agent=X` 403s unless X is wired to the node, capping grants to the binding. Access ≠ authority (ADR-0001). Settings "Operator profile" bar removed (§6). **Deferred:** intake-authored capture + the auto agent-consumption `agent` pass. |
| [ADR-0025](adr/ADR-0025-versioned-reversible-agent-config.md) | **Proposed** — tool-card config (issue-class policy, custom watch specs, scope) is an **immutable, git-backed tagged revision**; rollback = re-pin (nothing destroyed); a run pins the exact config tag in force so every action is attributable + reversible. Structured for ML + audit. |

## Data (the artifacts and their lineage)
| Doc | Status | Purpose |
|---|---|---|
| [data/strategy.md](data/strategy.md) | ✅ | Data strategy: sourcing, origin labels, real/synthetic tracks |
| [data/schemas.md](data/schemas.md) | ✅ | Record contracts + persistence (the data spine) |
| [data/metric_registry.md](data/metric_registry.md) | ✅ | Canonical metric vocabulary (stable layer over MultiQC keys) |
| [data/qc_metrics.md](data/qc_metrics.md) | ✅ | QC metric set and gate thresholds (the decided runbook) |
| [data/qc_metrics-sources.md](data/qc_metrics-sources.md) | ✅ | Grounded reference: verified field names + cited thresholds |
| [data/qc_metrics-rare-disease.md](data/qc_metrics-rare-disease.md) | ✅ | Rare-disease gold standards: depth/breadth, cancer/pathogen comparison, tool licenses |
| [data/nf-core-conventions.md](data/nf-core-conventions.md) | ✅ | nf-core/sarek conventions → schema records (sample sheet, versions, MultiQC, artifacts) |
| [data/provenance.md](data/provenance.md) | ✅ | Event seam: AnalysisRun anchor, event vocabulary, append-only ledger |
| [data/licensing.md](data/licensing.md) | ✅ | Per-tool + data-source licenses; external-process invocation model |

## Quality (is it correct, what could go wrong)
| Doc | Status | Purpose |
|---|---|---|
| [quality/evaluation.md](quality/evaluation.md) | ✅ | What "good" means, checks (EVAL-NNN) grounded in the test suite, failure modes |
| [quality/risks.md](quality/risks.md) | ✅ | Technical / product / data / demo risks + mitigations (RISK-NNN) |

## Audit (release-hardening review, repo root — not under `docs/`)
| Doc | Status | Purpose |
|---|---|---|
| [audit/README.md](../audit/README.md) | ✅ | The `audit/` landing page — frames the dir as internal, point-in-time release-hardening snapshots (candid by design; findings acted on via `tasks.md`, not current-state truth) + an index of its contents |
| [audit/AUDIT_PLAN.md](../audit/AUDIT_PLAN.md) | ✅ | The Fable-5 release-hardening audit plan — two tracks (release-hardening findings, wishlist feasibility), 10 read-only specialist agents |
| [audit/SYNTHESIS.md](../audit/SYNTHESIS.md) | ✅ | The consolidated, adversarially-re-verified findings (P0–P3, deduped, CONFIRMED/UNVERIFIED/REFUTED) + the pre-recording go/no-go checklist — see [evaluation.md EVAL-060](quality/evaluation.md) |
| audit/{ui-ux,data-lineage,journeys,integration,reliability,agent-safety,science-repro,demo-readiness,contract,truthfulness}.md | ✅ | The 10 individual specialist reports `SYNTHESIS.md` consolidates |
| [audit/wishlist/w1.md](../audit/wishlist/w1.md)–[w4.md](../audit/wishlist/w4.md) | ✅ | Grounded 3-approach design panels on four wishlist items, feeding [tasks T-126–T-130](planning/tasks.md) |

> **Read-only deliverable, not a doc-owned area.** The audit is a point-in-time review snapshot
> (2026-07-11) — it does not get routine upkeep like the canonical docs above; its *findings* are
> what gets acted on (tracked as `planning/tasks.md` rows + code fixes), not the audit files
> themselves. Kept at the repo root (`audit/`, not `docs/audit/`) as delivered by the audit run;
> registered here so it isn't an orphaned, undiscoverable directory.

## Usage (operator-facing)
| Doc | Status | Purpose |
|---|---|---|
| [usage/README.md](usage/README.md) | ✅ | Operator usage/wiki home — what bayleaf is, the operator workflow, page index, roles & page access. Per [UIC-1](design/ui-conventions.md#uic-1--no-page-flavor-text-the-nav-names-the-page), explanatory prose that used to live in page chrome lives here instead |
| [usage/operator-guide.md](usage/operator-guide.md) | 🚧 | Per-page how-to (stub sections, one per operator screen); linked from the README page index |

## Ops (run it in an environment)
| Doc | Status | Purpose |
|---|---|---|
| [ops/telemetry-connectors.md](ops/telemetry-connectors.md) | ✅ | Point Datadog / Prometheus / OTLP APMs at the shipped `GET /metrics` seam (pull model, scrape-safe, no PHI); config bundle in [`deploy/telemetry/`](../deploy/telemetry/) |

## Meta
| Doc | Status | Purpose |
|---|---|---|
| [DOCUMENTATION_HABITS.md](DOCUMENTATION_HABITS.md) | ✅ | How we document |
| [_templates/](_templates/) | ✅ | Skeletons — check before creating any new doc |
| [journal/](journal/) | ✅ | Dated raw session logs, distilled into the docs above |
| [HISTORY.md](HISTORY.md) | ✅ | Build-history archive — the dated wave/batch/commit chronology relocated out of the canonical docs so they stay small-and-current. **Not loaded each session**; the canonical docs carry the decision + current status and point here for the play-by-play |

## Doc-update map

**This table is the single authority on which docs a change obligates** (it replaces the old "Doc-to-code map" and the two prose lists in DOCUMENTATION_HABITS). You may still **read lean**; after any change, **sweep this table and update every doc whose trigger fired, in the same change** — a doc you never had to open can still be one you now owe. Match the concrete condition in column 2. Tiers: 🔴 fires most sessions · 🟠 module-triggered · ⚪ occasional.

| Tier | When you do / touch X | Owe an update to… (why) |
|---|---|---|
| 🔴 | **ANY working session — build, design, decision, or review (unconditional; the one row with no "N/A")** | **`journal/YYYY-MM-DD-<topic>.md`** — this session's reasoning + one Decisions row per decision made. New file per day from `_templates/journal.md`. Write it as you go; distil durable parts into the canonical docs below at session end. No journal entry = incomplete session. |
| 🔴 | A task changes status (`todo/in-progress/blocked/done`) or is created | `planning/tasks.md` — the task row, roadmap phase, and `Last updated`. |
| 🔴 | You create / move / rename / delete a doc, or flip its status (📝→🚧→✅) | `TABLE_OF_CONTENTS.md` — the section row, the status legend, **and this map** if a code↔doc link changed. |
| 🔴 | `src/bayleaf/models.py`, `parsers.py`, or `persistence/` — new/renamed field, type, ID prefix, `schema_version`, missing-field semantics | `data/schemas.md` — the pydantic contract SQLAlchemy mirrors. Cross-check `provenance.md` (event vocab is duplicated) + `metric_registry.md` §units. *(Confirmed drift: the export/Parquet contract shipped without this.)* |
| 🔴 | You add / remove / rename any test under `tests/`, or define an EVAL case | `quality/evaluation.md` — it hardcodes a test census ("N tests / M files"); any change silently falsifies it. Fix the count + per-file breakdown + any `EVAL-NNN`. |
| 🟠 | `runbook.py` or `rules.py` — a threshold, a metric in the set, a gate assignment, verdict policy | `data/qc_metrics.md` (the decided runbook). If the *decision policy* changed → also `ADR-0013`; if grounding changed → cascade to `qc_metrics-sources.md`. |
| 🟠 | `src/bayleaf/metrics/` — registry, aliases, unit, direction | `data/metric_registry.md` (+ `schemas.md` §units). |
| 🟠 | `provenance.py` / `engine.py`, the `EventType` vocabulary, or the JSONL ledger format | `data/provenance.md` (+ `schemas.md` event vocab — **duplicated, update both**; `ADR-0002`). |
| 🟠 | A new **advisory agent anywhere** (`synthesis/`, `triage/`, or an off-gate one like `api/feedback_agent.py`), a model tier, a corpus, **an agent-attachment/observation binding** (`AgentBinding`, `graph.agent_bindings`, `api/routers/node_observations.py`), or the **pipeline-vs-system agent taxonomy** (which agents are node-attachable vs Agent-triage launchers) | `design/agents.md` (roster + invariants + observation-binding model + taxonomy) + `design/agent-authoring-contract.md` (attach-as-observation) + the relevant ADR (`0001/0006/0009/0012`; `0022` for the observation-binding model). If hub and ADR disagree, the ADR wins — update the ADR first. |
| 🟠 | `api/` endpoint or `frontend/` screen — new/changed capability | `design/architecture.md` + `design/data-platform-and-archivist.md` + `requirements/functional.md` (REQ-F). If `/metrics` / `_render_prometheus` gains or renames a series → also re-verify the exposed-series table and the no-PHI claim in `ops/telemetry-connectors.md`. |
| 🟠 | The maintainer states a new **durable, cross-cutting UI/product rule** (not a one-off screen tweak) | `design/ui-conventions.md` — append a new `UIC-N` row **and** implement against it (don't wait to be told twice). If it changes shipped screen behavior, also `functional.md` (REQ-F) + the map row below. |
| 🟠 | `BuilderCanvas.tsx` / `BuilderShared.tsx` (`BTOOLSPEC`, port geometry, card size) — a tool node's ports, sizing, or wiring convention | `design/builder-cards/` (the per-tool port spec + its §5 "spec vs shipped" gap) + `design/ui-conventions.md` UIC-16. |
| ⚪ | You **make** a load-bearing decision (or realize/supersede one) | A **new `adr/ADR-NNNN-*.md`** (one decision/file) or an existing ADR's Decision/Status + a journal Decisions row. **Never bury a decision in a design-doc appendix or a "D1-Dn" list.** *(Confirmed drift: D1-D14 + a 261-line design landed as appendices.)* |
| ⚪ | Scope / wishlist / "built" changes | `requirements/scope-and-wishlist.md` (+ mirror `functional.md`, `tasks.md`). A new wishlist item is a scope-guardrail checkpoint — push back if scope over-broadens. |
| ⚪ | Files moved across `src/`/`app/`/`data/`/`docs/`/`tests/`, a module added, **or a trigger in this map rotted** | `CLAUDE.md` "Current code map" + **this map** (the self-referential row: when layout moves, this table's triggers go stale — fix them here). |
| ⚪ | You run a structured multi-agent **audit** (release-hardening, freshness, or similar) | `audit/` (or wherever the run lands) for the raw deliverable + `quality/evaluation.md` (an EVAL entry recording the review discipline, e.g. EVAL-060) + `planning/tasks.md` (a task row per finding acted on) — the audit itself is a point-in-time snapshot, not a doc that gets routine upkeep; its *findings* are what the map above routes onward as normal code/doc changes. |

**Catch-all** (any module not listed above whose behavior/contract you changed): update the doc that owns it — see the "Necessary documentation stack" table. **Also occasional:** exact commands / port change → `README.md`; a new tool/dependency → `data/licensing.md` + `requirements/constraints.md`; a new *type* of doc with no template → create `_templates/<type>.md` **first**, then the doc.

**Coupled clusters — one code change moves several docs together:** `schemas.md ⇄ provenance.md` (duplicated event vocab) · `qc_metrics.md ⇄ qc_metrics-sources.md` · `scope-and-wishlist.md ⇄ functional.md ⇄ tasks.md` · `metric_registry.md ⇄ schemas.md §units`. *The journal (row 1) is the router — every session logs here, then distils into the canonical docs above; it is never itself the source of truth.*
