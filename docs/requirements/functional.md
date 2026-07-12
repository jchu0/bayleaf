# Functional Requirements

| Field | Value |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-07-12 (MST) |
| **Audience** | software / all |
| **Related** | [scope-and-wishlist.md](scope-and-wishlist.md), [nonfunctional.md](nonfunctional.md), [constraints.md](constraints.md), [HISTORY.md](../HISTORY.md) (archived wave/batch narrative), [design/architecture.md](../design/architecture.md), [design/agents.md](../design/agents.md), [data-platform-and-archivist.md](../design/data-platform-and-archivist.md), [metric_registry.md](../data/metric_registry.md), [qc_metrics.md](../data/qc_metrics.md), [schemas.md](../data/schemas.md), [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md), [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md), [ADR-0008](../adr/ADR-0008-issue-taxonomy-suppression-escalation.md), [ADR-0009](../adr/ADR-0009-corpora-retrieval-upskilling.md), [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md), [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md), [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md), [ADR-0016](../adr/ADR-0016-postgres-port.md), [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md), [ADR-0018](../adr/ADR-0018-variant-interpretation-advisory-evidence.md), [ADR-0020](../adr/ADR-0020-operator-authored-custom-processes.md), [ADR-0021](../adr/ADR-0021-operator-gated-scheduled-pipeline-processing.md), [journal 2026-07-10 wave6](../journal/2026-07-10-wave6-route-to-human-deid.md), [journal 2026-07-09 frontend-batch2](../journal/2026-07-09-frontend-batch2.md), [journal 2026-07-09 frontend-batch3](../journal/2026-07-09-frontend-batch3.md), [journal 2026-07-10](../journal/2026-07-10-provenance-qc-builder-auth.md), [journal 2026-07-10 batch5](../journal/2026-07-10-batch5-builder-card-admin-prefs.md), [journal 2026-07-10 batch6](../journal/2026-07-10-admin-settings-builder-wiring.md), [journal 2026-07-10 batch7](../journal/2026-07-10-builder-modals-and-run-selector.md), [journal 2026-07-10 batch8](../journal/2026-07-10-batch8-theme-monitoring-recharts.md), [journal 2026-07-10 wave4](../journal/2026-07-10-wave4-submit-parsing-and-api-errors.md), [journal 2026-07-10 confirm-dialog](../journal/2026-07-10-confirm-dialog-audit-gate.md), [journal 2026-07-10 settings-agent-table](../journal/2026-07-10-settings-agent-table.md), [journal 2026-07-10 wave7](../journal/2026-07-10-frontend-batch7.md), [journal 2026-07-10 wave8](../journal/2026-07-10-frontend-wave8.md), [journal 2026-07-10 wave9](../journal/2026-07-10-frontend-wave9.md), [journal 2026-07-10 wave10](../journal/2026-07-10-wave10-node-author-uic.md), [journal 2026-07-11](../journal/2026-07-11-d2-d3-share-egress.md), [journal 2026-07-11 nextflow](../journal/2026-07-11-nextflow-codegen-execution.md), [journal 2026-07-11 audit+W1-W4+E2E](../journal/2026-07-11-audit-hardening-w1-w4-e2e.md), [journal 2026-07-11 P3 backlog](../journal/2026-07-11-p3-backlog.md), [journal 2026-07-11 fleet](../journal/2026-07-11-fleet.md), [journal 2026-07-12 builder-agent-hardening](../journal/2026-07-12-builder-agent-hardening.md), [design/ui-conventions.md](../design/ui-conventions.md), [design/builder-cards/](../design/builder-cards/), [design/node-authoring-agent.md](../design/node-authoring-agent.md), [design/nextflow-codegen.md](../design/nextflow-codegen.md), [design/agent-authoring-contract.md](../design/agent-authoring-contract.md) |

## Overview

What PipeGuard must *do*, as traceable capability requirements (**REQ-F-NNN**). Each
traces to an ADR, the architecture, or a grounded data doc. Quality attributes
(determinism, security, performance) live in [nonfunctional.md](nonfunctional.md);
boundaries in [scope-and-wishlist.md](scope-and-wishlist.md). Requirements describe
in-scope MVP behavior; deferred items are marked *(wishlist)*.

> **Naming (Fact).** The product surface was renamed **PipeGuard → bayleaf** (2026-07-11,
> commit `41330fe`) — README, frontend, FastAPI title, and UI copy. The importable Python
> package (`src/pipeguard/`), the `PIPEGUARD_*` env vars, and these engineering docs deliberately
> keep the `pipeguard` name; "PipeGuard" throughout this doc refers to the same system now
> presented as bayleaf.

## Decision gate

1. **REQ-F-001 — Per-sample verdict.** For each sample in a run, the system produces
   exactly one **DecisionCard** with a verdict of **proceed / hold / rerun /
   escalate** (one card per sample × analysis-run). *Trace:* [architecture.md](../design/architecture.md),
   [schemas.md](../data/schemas.md) §DecisionCard.
2. **REQ-F-002 — Cited evidence.** Every finding and card cites **Evidence**
   traceable to a source artifact + field (and, where present, a content hash), with
   observed vs expected values. No number appears without a source. *Trace:*
   [schemas.md](../data/schemas.md) invariants, ADR-0001.
3. **REQ-F-003 — Rules decide, deterministically.** Verdict and (when present)
   confidence are computed by the deterministic rule/aggregation layer, **never** by
   the LLM. *Trace:* [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
   `synthesis/base.py`.
4. **REQ-F-004 — Immutable, content-hashed findings.** Findings are immutable and
   content-hashed; each derives its gate and a rule-version-independent signature.
   Suppression/resolution never mutate a finding. *Trace:* [schemas.md](../data/schemas.md)
   §Finding, ADR-0008.
5. **REQ-F-005 — Confidence omitted until grounded.** Confidence is nullable and is
   omitted rather than fabricated when not grounded; when shown it is labelled a
   heuristic, not a calibrated probability. *Trace:* CLAUDE.md guardrails, T-019.

## Three-gate model & verdict policy (ADR-0013)

1. **REQ-F-010 — Three checkpoints.** Findings and verdicts are labelled by gate:
   **preflight** (intake), **qc** (per-sample QC), **variant** (Phase 2). *Trace:*
   [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md), [architecture.md](../design/architecture.md).
2. **REQ-F-011 — Preflight gate.** Check barcode/index integrity, sample identity,
   required metadata, and per-sample FASTQ sanity before the processing queue, with a
   manual-override path for genuinely-sparse edge cases. *Trace:* ADR-0013,
   [qc_metrics.md](../data/qc_metrics.md) Gate 1.
3. **REQ-F-012 — QC gate.** Evaluate yield/Q30, coverage **depth and breadth**,
   contamination, and sample-swap; surface depth and breadth as **distinct** signals.
   *Trace:* [qc_metrics.md](../data/qc_metrics.md) Gate 2, ADR-0013.
4. **REQ-F-013 — Variant gate.** *(Phase 2)* Per-variant DP/GQ/allele-balance plus
   gnomAD/ClinVar annotation; caller-aware. *Trace:* [qc_metrics.md](../data/qc_metrics.md)
   Gate 3.
5. **REQ-F-014 — Surface-and-decide verdict mapping.** Borderline → **HOLD**;
   provenance/identity → **ESCALATE**; operational/file-system failure → **RERUN**;
   clean → **PROCEED**; worst verdict wins. *Trace:* ADR-0013,
   [qc_metrics.md](../data/qc_metrics.md) §Verdict policy.
6. **REQ-F-015 — Config-driven thresholds.** Thresholds come from an operator-owned
   runbook **profile** keyed on **assay × sample type**; no hardcoded universal
   thresholds. *Trace:* [qc_metrics.md](../data/qc_metrics.md) §Principles, ADR-0005.
7. **REQ-F-016 — Metrics normalized through the registry; gate on canonical values.**
   Each QC metric is resolved to its canonical `our_key` and normalized to a **canonical
   decimal** via the **metric registry** before gating; the gate compares the normalized
   value against a canonical-decimal runbook threshold (both on the registry's scale), so
   a change in a source's raw unit cannot silently move a verdict, and verdicts stay
   byte-identical. The registry is **on the QC-gate critical path**; a missing field yields
   no `MetricValue` (a signal, not a crash). *Trace:* [metric_registry.md](../data/metric_registry.md),
   [schemas.md](../data/schemas.md) §QC (units contract), `rules.py`, T-024/T-025.
8. **REQ-F-017 — Execution-trace ingestion (EXEC-001).** The gate **reads** an optional
   Nextflow/nf-core `trace.txt` when the run produced one and maps a **failed pipeline
   process** to **RERUN** — the structured sibling of the free-text run-log check (PIPE-001).
   A task attaches to its sample by an **exact** nf-core `tag` match (so a zero-padded id can't
   cross-fire the way a substring would), and a task is a failure when its status is in the
   runbook's failure-status set **or** its exit code is nonzero (an OOM/time-kill fires even
   when the status isn't literally `FAILED`), yielding a cited, immutable `Finding` (PIPELINE
   category, **preflight** gate) whose suggested verdict is RERUN. It **composes ≠ executes**:
   it *reads* a trace the run already emitted and **never runs a process** (ADR-0001/0003). A
   missing, absent, or garbled trace yields **no** finding (a signal, not a crash — the pinned
   demo runs carry no `trace.txt` and are unaffected). Downstream it is **advisory only**: the
   EXEC-001 finding's recurring signature flows to the pipeline-repair agent (REQ-F-023) via the
   monitoring rollup, giving that agent a **structured executor-failure** feed distinct from
   PipeGuard's own gate findings. The **verdict policy is unchanged** — an operational/execution
   failure → RERUN (REQ-F-014). *Trace:* [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md),
   [qc_metrics.md](../data/qc_metrics.md) §Verdict policy,
   [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md)/[ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md),
   `rules._check_execution_trace`, [tasks T-061](../planning/tasks.md).
9. **REQ-F-018 — Route-to-human policy (VAR-RTH-001), off by default.** The system can route a
   sample to **mandatory human review** when an externally-annotated candidate variant carries an
   operator-armed ClinVar significance. **Disarmed by default** (`RouteToHumanPolicy.significances`
   is an empty tuple) — the stock runbook never routes, and every pinned demo verdict is
   unaffected. When armed, a deterministic rule (`rules._check_route_to_human`) emits a cited,
   immutable `Finding` (category `variant`, **variant** gate) whose suggested verdict is
   **ESCALATE**; it **quotes the source ClinVar classification verbatim** (never PipeGuard's own
   determination — ADR-0004) and cites the accession/review status. The action space is only
   `{route-to-human}` — no Pathogenic/Benign verdict, no probability; the variant **QC** gate
   (REQ-F-013, DP/GQ/AB) is untouched. A qualified human clears the hold via the existing
   RBAC-gated review queue (REQ-F-063, ADR-0017) — no new access pattern. The system **reads** an
   externally-produced annotated variant table (`variants.csv` → `models.VariantCall`, parsed by
   `parsers.parse_variant_calls`); it never runs an annotator (compose ≠ execute, ADR-0003).
   **Fires end-to-end against a committed run (2026-07-11):** `api.main._active_runbook(run_id)`
   is the deployment-config seam that arms the policy **per run** from an optional
   `route_to_human` marker file in the run dir; `data/RUN-2026-07-11-CLINVAR-RTH/`
   (`origin=contrived`) is a committed, test-pinned fixture that ESCALATEs HG002 via
   `VAR-RTH-001` when evaluated through the live API, closing the earlier "never fires
   end-to-end" gap — every unmarked run stays disarmed. *Trace:*
   [ADR-0018](../adr/ADR-0018-variant-interpretation-advisory-evidence.md) decision D2 +
   [Realized](../adr/ADR-0018-variant-interpretation-advisory-evidence.md#realized-2026-07-11),
   [qc_metrics.md](../data/qc_metrics.md) §Route-to-human policy, [schemas.md](../data/schemas.md)
   `VariantCall`, [tasks T-109, T-119](../planning/tasks.md).

## Advisory triage agent (ADR-0009/0012)

1. **REQ-F-020 — On-demand triage.** For a flagged card, the system can produce an
   advisory **TriageNote** (likely cause, suggested action, citations) grounded in a
   curated knowledge corpus via a retrieval interface. *Trace:* [architecture.md](../design/architecture.md)
   §Triage agent, ADR-0009.
2. **REQ-F-021 — Advisory only, off the critical path.** The triage agent never sets
   or overrides a verdict/confidence and is not on the deterministic path; its output
   is labelled advisory. *Trace:* [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
   ADR-0012.
3. **REQ-F-022 — Outbound notify.** For each *actionable* card (HOLD/RERUN/ESCALATE;
   clean cards are skipped), the system can emit a per-verdict, evidence-cited notification
   through a swappable notify port (`PIPEGUARD_NOTIFIER=stub|slack`, stub-first, $0). The
   hook is **optional and off by default** — `run_gate(notifier=…)` is wired only when a
   notifier is injected, and with none the event trail is byte-for-byte unchanged. It
   **formats what the gate decided, never a verdict** (ADR-0001); the live Slack post is
   opt-in via `PIPEGUARD_SLACK_LIVE`, degrades to the stub on any error, and every send is
   recorded as a `notification.emitted` ledger event. `python -m pipeguard.notify <run_dir>`
   is the CLI. *Trace:* [architecture.md](../design/architecture.md) §Outbound notify seam,
   [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md).

## Advisory agent roster — pipeline-repair, archivist & node-authoring (ADR-0001/0008/0012)

Three further advisory agents (roster #2/#3/#5, [agents.md](../design/agents.md) §Roster) join the
QC-triage agent (REQ-F-020/021). Each shares the same contract as triage: **advisory, on-demand,
and OFF the deterministic gate** — like every agent (ADR-0001) it never sets, routes, or overrides
a verdict or confidence; it is **stub-first ($0, offline)** and env-flippable to live; and its
output is an immutable, content-hashed record whose organizational/remediation fields and citations
are **deterministic**, with only the free prose optionally model-authored (the shared invariant now
holds across **six** seams — the synthesizer plus the five advisory agents: triage, feedback,
pipeline-repair, archivist, and node-authoring, all now built, REQ-F-050).

1. **REQ-F-023 — Advisory pipeline-repair agent.** On a **recurring issue signature** rolled up
   from the monitoring view (the same `Finding.signature` counter `GET /api/monitoring` uses — now
   including structured pipeline-executor failures via EXEC-001, REQ-F-017, not only PipeGuard's own
   gate findings), the system can produce a cited **RepairProposal** {`summary`, `attach_to` (pipeline stage), `scope`
   (gate)} proposing a **human-reviewed** remediation grounded in a curated remediation corpus
   (ADR-0008 taxonomy + the runbook; **no invented thresholds**). `advisory` is pinned `True` and the
   record has **no verdict/confidence field**; `attach_to`/`scope` and every citation are
   deterministic (from the corpus + the addressed rule/signature), only the prose may be
   model-refined. It is exposed **on-demand** at
   `GET /api/monitoring/signatures/{signature}/repair` (404 if the signature does not recur in the
   window) — explicitly **not** the deferred ~3× auto-escalation trigger — and **never edits a
   pipeline** (compose ≠ execute; a fix changes nothing on the gate until a human approves + the
   builder emits a new `run_layout.yaml`). Env `PIPEGUARD_PIPELINE_REPAIR_AGENT=stub|claude`
   (Opus-high, `PIPEGUARD_PIPELINE_REPAIR_MODEL`), stub-default, degrade-to-stub on any error.
   *Trace:* [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
   [ADR-0008](../adr/ADR-0008-issue-taxonomy-suppression-escalation.md),
   [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md),
   [agents.md](../design/agents.md) §Roster #2, `src/pipeguard/pipeline_repair/`,
   [tasks T-058](../planning/tasks.md).
2. **REQ-F-024 — Advisory archivist (librarian) agent.** The system can index/summarize
   already-decided runs into an **ArchiveDigest** (an organizational digest + a prepared export
   manifest + a cross-run index) — **organizational, not diagnostic**. It runs on a **least-privilege**
   input (no `subject_id`/tissue/`submitted_by`), **never opens/moves/deletes a file or relabels an
   `origin`**, `advisory` is pinned `True`, and it carries no verdict/confidence (ADR-0001); every
   organizational number is deterministic and only the summary prose may be model-authored. Its
   `released`-lifecycle readiness flag is an **organizational** state, never a per-sample verdict
   (REQ-F-003 holds). Exposed on-demand at `GET /api/runs/{id}/archive-digest` (one run) and
   `GET /api/archive/index` (cross-run). Env `PIPEGUARD_ARCHIVIST_AGENT=stub|claude` (Haiku,
   `PIPEGUARD_ARCHIVIST_MODEL`), stub-default, degrade-to-stub. *Trace:*
   [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
   [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md) §model-tiering,
   [data-platform-and-archivist.md](../design/data-platform-and-archivist.md) §5,
   [agents.md](../design/agents.md) §Roster #3, `api/archivist.py`,
   [tasks T-059](../planning/tasks.md).
3. **REQ-F-025 — Advisory node-authoring agent (retrieval over a curated corpus).** Given a
   natural-language request or bare tool name, the system can produce a cited **NodeProposal** —
   a proposed tool node (name, pinned version, typed input/output ports, suggested locators,
   rationale) — for the Pipeline Builder palette. `advisory` is pinned `True`, no verdict/confidence
   field; the tool, version, ports, and locators are **deterministic** (from the corpus), only the
   `summary`/`rationale` prose may be model-refined. A port kind outside the real, closed
   `ARTIFACT_KINDS` vocabulary is surfaced `reserved`, **never fabricated as a live wire**
   (`PortSpec.known` is computed against that vocabulary — structural, not a convention). A
   request that matches no curated card (or is blank) returns a conservative "defer to a human"
   proposal with no invented tool or ports. Env `PIPEGUARD_NODE_AUTHOR_AGENT=stub|claude`
   (`PIPEGUARD_NODE_AUTHOR_MODEL`, default mid/Sonnet), stub-default, degrade-to-stub on any error
   (incl. a safety refusal). **Narrower than the roster's original design** (see
   [node-authoring-agent.md](../design/node-authoring-agent.md) "What actually shipped"): the
   corpus is a fixed **9 curated cards** (this pipeline's own 7 tools + 2 reference nodes —
   verified via `load_tool_card_corpus()`, 2026-07-12). Two cards were retired *after* the original
   11: Branch A of the custom-script-card effort (2026-07-11) dropped the unwired **Truth VCF**
   reference node (→ 10; see REQ-F-098 and [ADR-0020](../adr/ADR-0020-operator-authored-custom-processes.md)),
   then commit `dff2cef` retired **NGSCheckMate** from the *proposable* set (→ 9) — retired-but-pinned:
   the JSON line stays commented in `tool_cards.jsonl` (and the `ngscheckmate` kind stays in
   `ARTIFACT_KINDS`), so it can be un-commented without loss but is not currently proposed.
   Corpus file: `src/pipeguard/node_author/knowledge/tool_cards.jsonl`, not a parser over a dropped
   `nextflow_schema.json`/`--help`/README, so the agent can only propose a tool already known to
   the corpus via `propose_node()` — it does not yet onboard a genuinely new/arbitrary tool through
   its main retrieval path. `GET /api/builder/node-proposal` + Pipeline-Builder wiring now exist
   (REQ-F-089, 2026-07-11); a separate `POST /api/builder/node-proposal/accept` +
   `nextflow_schema.json` doc-drop importer now exist too, backend-only (REQ-F-096, 2026-07-11) — see
   that requirement for what those close. 19 tests (`tests/test_node_author.py`), all offline/$0.
   *Trace:* [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
   [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md),
   [ADR-0009](../adr/ADR-0009-corpora-retrieval-upskilling.md),
   [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md),
   [agents.md](../design/agents.md) §Roster #5, `src/pipeguard/node_author/`,
   [tasks T-046](../planning/tasks.md).

## Provenance & persistence (ADR-0002/0003)

1. **REQ-F-030 — Append-only event ledger.** Every gate execution emits an
   append-only event trail (`analysis_run.started` → per-sample
   `sample.registered` / `finding.emitted` / `verdict.decided` →
   `analysis_run.completed`) into an EventLedger (in-memory + optional JSONL). *Trace:*
   [provenance.md](../data/provenance.md), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md).
2. **REQ-F-031 — Log is authoritative; DB is a projection.** The relational DB is a
   rebuildable projection reached only through a `Repository` port; the core never
   touches a DB directly. *Trace:* [provenance.md](../data/provenance.md), ADR-0003.
3. **REQ-F-032 — rebuild-db.** A `rebuild-db` command replays a JSONL ledger into a
   fresh projection deterministically and idempotently. *Trace:* [provenance.md](../data/provenance.md)
   §DB projection.
4. **REQ-F-033 — Origin labelling.** Every artifact/record is tagged `real-giab` /
   `synthetic` / `contrived`; the label is carried through the ledger and schemas.
   *Trace:* [strategy.md](../data/strategy.md), ADR-0007.

## Read API & operator screens (ADR-0010/0014)

1. **REQ-F-040 — Read API.** A FastAPI read-API serves decision cards, provenance
   events, run **artifacts** (`GET /api/runs/{id}/artifacts` — per-stage data I/O with real
   sha256 + on-disk size + origin tag; raw reads above an 8 MiB cap are size-listed, not
   hashed), export, and config over the framework-agnostic core (the production seam).
   *Trace:* [architecture.md](../design/architecture.md), ADR-0010/0014.
2. **REQ-F-041 — On-demand advisory-agent endpoints.** The API exposes per-card triage plus the
   pipeline-repair (REQ-F-023) and archivist (REQ-F-024) calls, each invoking an advisory agent
   **without re-entering the verdict path** — all read-only over already-decided artifacts.
   *Trace:* [architecture.md](../design/architecture.md), [agents.md](../design/agents.md), ADR-0010.
3. **REQ-F-042 — Operator screens.** The UI presents **12 operator screens** (was 11 when this
   entry was last corrected; Sample accessioning — REQ-F-082 — is new as of Wave 9, T-117),
   rebuilt to the refreshed design prototype
   (`docs/design/frontend/`, 2026-07-09) in a **three-group nav** — **Operate** (reordered
   2026-07-10, Wave 8, T-110, G4, to Notification→Action→Steps, then Wave 9, T-117, to lead the
   Steps sub-sequence with accessioning): Inbox (REQ-F-077), review queue
   (tickets w/ role-gated actions, REQ-F-063), sample accessioning (a CRM subject/sample
   registration step upstream of the samplesheet — REQ-F-082), submit samplesheet (register a run's
   SampleSheet/FASTQ and hand off to the `POST /api/runs` execution boundary — REQ-F-067;
   compose≠execute still holds at the core), runs overview (per-verdict counts + needs-attention +
   a client-side scale kit: search/facet/sort/date-range/paginate; the top-bar run switcher shares
   the Runs list's status-derived dot via `RUN_STATUS_META`, fixing a bug where the switcher's dot
   read `n_attention` instead of the real lifecycle `status`), intake/preflight (run-level QC
   rollup + per-sample admission with manual override, plus lazy-loaded preflight metadata —
   REQ-F-080), decision cards (verdict + per-gate strip + a QC-readout hero from
   REQ-F-064/REQ-F-068 + cited evidence); **Analyze:** provenance (Lineage / Event trail /
   Artifacts — REQ-F-078), agent triage (advisory note + citations + offline/live), monitoring
   (windowed aggregate, REQ-F-047); **Configure:** pipeline builder (REQ-F-045, on-canvas editing
   REQ-F-079) and settings (runbook thresholds, labelled illustrative). A separate Admin
   governance screen sits outside this operator nav, gated on the login identity's **`isAdmin`**
   (a frontend-only governance capability layered over the wire roles, **not** "any approver" —
   REQ-F-066/REQ-F-069) — off the deterministic gate, it is not counted among the 12. A shared
   `RoleContext` (reviewer|approver) drives every RBAC-gated control, and now exposes a
   full `setActor(actor)` (id+role together) consumed by Admin's "Act as" (REQ-F-066). A
   **second, distinct** frontend-only governance layer, the page-access **view-gate**
   (REQ-F-082), additionally filters which of these 12 screens a given user's nav even shows —
   layered over, not replacing, `RoleContext`. Screens
   state their data boundary rather than fabricate instrument/compute artifacts the FASTQ-first
   build doesn't capture; one honest gap is explicitly rendered empty rather than invented:
   Monitoring's Median-review KPI (no backend field — its signature-level `first_seen`/
   `last_seen`/`trend`/`affected_run_ids` fields ARE shipped, REQ-F-047). (Provenance artifact
   links, once a similar honest gap, are now real — `RunArtifact.url` is populated, REQ-F-070.)
   *Trace:* [demo_plan.md](../demo/demo_plan.md),
   [architecture.md](../design/architecture.md),
   [tasks T-022/T-022b/T-037/T-044/T-062/T-108/T-110](../planning/tasks.md),
   [journal 2026-07-09 frontend-batch2](../journal/2026-07-09-frontend-batch2.md),
   [journal 2026-07-10 wave8](../journal/2026-07-10-frontend-wave8.md).
4. **REQ-F-044 — In-app feedback (off-gate telemetry).** The app captures product feedback
   via the app's first write endpoint (now one of several off-gate product-domain writes),
   `POST /api/feedback` — a per-decision agree/disagree signal
   (keyed to verdict + gate + rule ids + card hash) and a global product note, each tagged with
   the originating UI `source`. It is **off the deterministic gate** (never mutates a
   verdict/provenance event; ADR-0001), carries **no operator identity** (`extra="forbid"`
   structural guard), and resolves `origin` server-side. The sink is a **pluggable store**
   (JSONL default / SQLite / Postgres, `PIPEGUARD_FEEDBACK_STORE`) with its own table, separate
   from the decision projection and degrading to JSONL (ADR-0016). An **advisory feedback agent**
   (`python -m api.feedback_agent`, stub/claude) categorizes the corpus structurally out-of-band.
   *Trace:* [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md),
   [ADR-0016](../adr/ADR-0016-postgres-port.md), [tasks T-042/T-043](../planning/tasks.md).
5. **REQ-F-043 — Offline fallback view.** A Streamlit app renders the same core
   offline, in one process, as the guaranteed-working demo fallback. *Trace:*
   [demo_plan.md](../demo/demo_plan.md), ADR-0014.
6. **REQ-F-045 — Pipeline Builder (compose ≠ execute).** An editable node-graph screen
   (the superset of the Provenance canvas) lets an operator configure the germline pipeline
   and **emit `run_layout.yaml`** across profiles. It **composes, never executes** (the
   primary action is Emit, never Run), and renders the load-bearing invariants as visible
   guarantees: agents are port-less side-nodes (an agent→gate data edge is unrepresentable),
   the deterministic gate is a terminal locked node with no verdict control, and every emitted
   locator's `origin` is `unknown` (config locates, never relabels provenance). A composed graph
   **saves + versions** via `POST/GET /api/pipelines` — a **product-domain store off the gate**
   (pluggable JSONL/SQLite/Postgres, `PIPEGUARD_PIPELINE_STORE`, degrade-to-JSONL, ADR-0016),
   storing the graph as a **tolerant versioned envelope** (arbitrary payload kept as-is) with a
   server-authored monotonic per-name version. It **reserves** a `draft→save→approve` review
   lifecycle (`status` + reviewer/approver fields, server-authored, no identity via the
   `extra="forbid"` body); the approve transition + auth are now realized in REQ-F-061
   (`api/routers/pipelines_lifecycle.py` + `api/auth.py`,
   [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md)). **Frontend rebuild
   (2026-07-09, Wave 3):** the screen now also ships free composition (add/drag/delete
   user nodes from the palette), a typed-port **Connect mode** (kind-matched wiring only,
   INV-e), a minimap, and editable Locators with live YAML regen. **Write-wiring fix
   (2026-07-09 maintainer batch, commit `586f832`):** Save now chains `savePipeline` →
   `submitPipeline` (draft → pending_review, so Approve's `pending_review` precondition is
   met — previously 409'd) and the doc name is slugified for the backend; Save/Approve both
   **await the response and reconcile local `version`/`status` from it** (toasted
   success/failure via the new `Toast` system), no longer fire-and-forget. **Dry-run/Diff wired
   to the real endpoints (2026-07-10, T-096, commit `4208f0b`, "Item E"):** once the graph is
   Saved (exists in the pipeline store), the console's Dry-run tab calls `POST
   /api/pipelines/{name}/dry-run?run_id=…` (REQ-F-061) — via a plain run-id text input —
   rendering the
   real per-locator matched/ambiguous/missing/invalid resolution + summary, and the Diff tab
   calls `GET /api/pipelines/{name}/diff` (REQ-F-061), rendering added/changed/removed vs the
   approved baseline (or "no baseline yet"); both fall back to the earlier client-side preview
   before Save. This closes the previous "known, labelled limitation" (Dry-run/Diff existed in
   `api.ts` but the Builder screen never called them — not a fabricated success, since the
   console rendered from local state and never claimed a server round trip). **Run-selector +
   advisory-modal wiring + saved-profiles (2026-07-10, commits `34bca5d`→`adfd7aa`, T-069/T-070,
   closing both):** the Dry-run run-id text box is now a reusable, searchable `RunSelector`
   (`frontend/src/components/RunSelector.tsx`, T-070 — an 8-row-capped combobox sharing the
   top-bar switcher idiom, real `RUN_STATUS_META` status dot per F17, self-fetching `api.runs()`
   lazily with an honest "Couldn't load runs" on failure). The "Pipeline-repair" / "Archivist"
   modals — previously **static UI previews** labelled `phase-2` in-app — now call the live
   advisory-agent endpoints (T-069, REQ-F-041): `PipelineRepairModal` → `GET /api/monitoring`
   (a recurring-signature picker) + `GET /api/monitoring/signatures/{sig}/repair` → the real
   `RepairProposal`, each corpus citation labelled with a **"heuristic" score, never
   "confidence"** ("Send to review queue" navigates to `/queue`, never fabricates a ticket);
   `ArchivistModal` → `GET /api/archive/index` → the real cross-run `ArchiveDigest` ("Queue
   archive" stays inert — no write endpoint exists). The `RunHandoffModal` now shows the real
   composed `run_layout.yaml`, and a new toolbar **"Open"** action lists `GET /api/pipelines` and
   hydrates the canvas from a chosen saved graph (closing the earlier "saved-profiles has no
   backend seam" gap) — approved graphs open read-only, re-saving mints a new draft, and a
   foreign/topology-less envelope loads empty with a labelled toast rather than fabricated nodes.
   **Only the "Author a tool node" modal remains a static `phase-2` preview** — see
   [tasks T-046](../planning/tasks.md), a proposed-not-built design note, unaffected by this
   batch. **Editable template fix (2026-07-09, commit `01ba673`,
   [tasks T-075](../planning/tasks.md)):** "New → From template" previously re-showed the
   read-only seeded DAG, so the demo's own pipeline couldn't be modified in Edit;
   `germlineTemplate()` now instantiates the same fastp→…→MultiQC chain as real, editable
   `UserNode`/`UserEdge`s, and `showSeeded` is gated on `isLinked` so **only** the original
   linked pipeline still renders read-only — Save now sends the true composed 7-node graph
   (was empty for the seeded doc). **Canvas + palette polish (2026-07-10, commits
   `14c9f3c`/`c6a6210`, T-085/T-086):** Tidy is now a **flow-preserving auto-layout** — each
   node's longest-path depth from a source is relaxed over the composed edges, then placed in
   the column of its depth with parallel nodes stacked, so upstream→downstream reads
   left→right instead of one row losing the connection structure; a **Cancel** button
   (draft-only) discards an in-progress build and returns to the linked pipeline in View; the
   minimap moved bottom-right→top-right. The palette gained a **References** section
   (Reference FASTA/Panel BED/Truth VCF — no-input source nodes emitting their reference
   artifact, typed-wired so a fasta can't land on a fastq port), fixing the earlier "no way to
   add bed/vcf/reference cards" gap, and its sections are now **collapsible** (chevron +
   per-section count, overridden by an active search). **Edge clarity + toolbar consolidation +
   off-canvas decision boundary (2026-07-11, commits `a03704f`→`3d531de`, T-124,
   [journal](../journal/2026-07-11-builder-boundary-and-edges.md)):** wired ports now split into
   one sub-anchor per edge so no two wires share an endpoint, and an occlusion-aware reference
   placement clears most wire-behind-card cases (layout-only; the graph model is untouched).
   Editable wires now stroke by their source port's `kind` (matching the seeded-wire color
   family), and the two-row toolbar collapsed into one compose bar (Save · Validate · Emit
   primary) plus an "⋯ More" overflow for occasional actions, with the run identity shown once
   (was duplicated). **This corrects a claim in this REQ's own opening paragraph above:** *"the
   deterministic gate is a terminal locked node"* described the gate as an on-canvas node — as of
   this pass **it no longer is**. The gate and its deterministic-ingest predecessor were removed
   from `BuilderCanvas.tsx` entirely (an intermediate step first made them movable canvas cards,
   commit `73b2a68`, before the maintainer's follow-up synthesis removed them, commit `3d531de`;
   canvas node count 15→13) and replaced by a new read-only `DecisionBoundaryModal.tsx`
   (Composed pipeline → Deterministic ingest → Decision gate → Verdict, opened from "⋯ More →
   Decision boundary"), captioned "rules decide; not part of what you compose." Both remaining
   gate-verdict color bars were also removed the same day — **the Builder now renders no verdict
   palette anywhere**; agent attach/detach became edit-only, with View showing a read-only
   indicator on already-attached tools. `Save`/`Emit`/`POST /api/pipelines/compile` are
   unaffected — they always serialized only `{nodes: userNodes, edges: userEdges}`, and still do;
   the gate/ingest/agent canvas state was never part of that payload. See
   [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) Realized §3 for why this is a UI
   reinforcement of the existing decision, not a new one. *Trace:*
   [pipeline-builder-brief.md](../design/frontend/pipeline-builder-brief.md) (the original design
   brief — still describes an on-canvas gate/ingest band; superseded by the above, kept unedited
   as a design deliverable),
   [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md),
   [journal 2026-07-09 frontend-batch2](../journal/2026-07-09-frontend-batch2.md),
   [journal 2026-07-10 batch5](../journal/2026-07-10-batch5-builder-card-admin-prefs.md),
   [journal 2026-07-10 batch6](../journal/2026-07-10-admin-settings-builder-wiring.md),
   [journal 2026-07-10 batch7](../journal/2026-07-10-builder-modals-and-run-selector.md),
   [journal 2026-07-11](../journal/2026-07-11-builder-boundary-and-edges.md),
   [tasks T-044/T-049/T-062/T-069/T-070/T-085/T-086/T-096/T-124](../planning/tasks.md).
7. **REQ-F-046 — Honest run lifecycle status + run metadata.** `RunSummary` carries a real
   `status` — `running` (no completion event yet) / `needs_review` (completed, actionable
   samples) / `released` (completed, none) — derived from the provenance ledger, **not** inferred
   from `n_attention` (which mislabeled a still-running, 0-attention run as Released). It also
   surfaces `platform` + `run_date`, parsed tolerantly from the SampleSheet `[Header]`. `status`
   is a run-lifecycle label, never a per-sample verdict (REQ-F-003 holds). *Trace:*
   [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md),
   [schemas.md](../data/schemas.md), [tasks T-047](../planning/tasks.md).
8. **REQ-F-047 — Server-side monitoring aggregate + runs pagination.** `GET /api/monitoring`
   returns a pre-aggregated, optionally time-windowed (7d/14d/30d/all) dashboard payload (KPIs,
   per-run rows, per-gate pass-rate, ranked recurring signatures) so the UI needn't fan out every
   run's detail; its throughput ratio is a labelled **heuristic**, not a calibrated value. Each
   ranked signature ADDITIVELY carries `first_seen`/`last_seen` (earliest/latest `[Header]` run
   date, `None` when undated — never fabricated), `trend` (up/down/flat, a display heuristic
   comparing the window's recent vs older half by count — not a calibrated rate), and
   `affected_run_ids` (distinct, chronological); the payload stays backward-compatible. A
   Median-review-time KPI stays a documented, not-yet-built seam. `GET /api/runs` accepts
   additive `verdict/q/sort/page/limit` (no params → byte-identical body;
   count/page/limit on response headers). **Signatures-list pagination (2026-07-09, commit
   `e5d5043`, [tasks T-076](../planning/tasks.md)):** `Monitoring.tsx` now paginates the
   recurring-signatures grid client-side (25/50/100 + pager), mirroring the Runs-list pattern —
   distinct from [tasks T-072](../planning/tasks.md), the *per-run* `rows: list[MonitoringRunRow]`
   on the same response. **Per-run pagination, frontend half (2026-07-10, commit `34bca5d`,
   [tasks T-072](../planning/tasks.md)):** the throughput card's per-run columns now paginate the
   same way (25/50/100 + pager, "Showing X–Y of N runs," independent state, reset on
   window/date-range/per-page change) — **this closes only the frontend half**; the `rows[]`
   payload itself is still returned uncapped by `get_monitoring`, so T-072 stays open for the
   backend cap. **Superseded the same day (commit `f8a6f35`, [tasks T-100](../planning/tasks.md)):**
   the throughput card is now a Recharts `ComposedChart` (`recharts@3.9.2`, MIT — the frontend's
   first real charting dependency) FROZEN to a ~14-day column frame that scrolls sideways beyond
   it, and **the per-run pager above was removed**, not narrowed — a pager made no sense once
   the chart scrolls instead of paginating (the signatures pager is unaffected). The chart now
   renders every fetched run as a bar with no client-side cap either, so `GET /api/monitoring`'s
   `runs[]` remained uncapped in **both** directions until the backend gained `page`/`limit`.
   **Closed 2026-07-11 (T-132, commit `deee99f`):** `GET /api/monitoring` now accepts additive
   `page`/`limit` on `runs[]`, mirroring `GET /api/runs` exactly (same param names, the same
   `X-PipeGuard-{Total-Count,Page,Limit}` response headers); the KPI roll-up, per-gate pass rates,
   and ranked signatures are computed BEFORE the slice, so a page can never distort them — only the
   throughput array itself is sliced. `Monitoring.tsx` wires a `<Pager>` to the new params; the
   chart still renders every run **on the current page** as a scrolling bar (T-100's chart framing
   is unaffected — this is the backend cap T-072 tracked, not a return to a client-side row limit).
   [tasks T-072](../planning/tasks.md) is now `done`. The same T-100 commit adds a **grounded hover
   tooltip** (real per-run verdict
   counts, no synthesis) and a "Flagged (trend)" line (hold+rerun+escalate), and gives each
   ranked signature a unique, stable, client-rendered display id (`SIG-<first 8 chars of the
   signature hash>`) plus a REVERSIBLE, `localStorage`-persisted clear-from-view/restore — a
   pure client-side view filter (never a DB purge, never an `api/` write) that hides a signature
   from the default list into a collapsible "Cleared · N" section without dropping it from
   search or escalation; neither addition changes the wire contract. *Trace:*
   [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md),
   [architecture.md](../design/architecture.md), [tasks T-048/T-072/T-100](../planning/tasks.md).

## AI configurability (ADR-0006)

1. **REQ-F-050 — Env-flippable AI, off by default.** Every AI seam flips via env, each
   defaulting to `stub` ($0, offline): the synthesizer (`PIPEGUARD_SYNTHESIZER`) plus five
   advisory agents — QC-triage (`PIPEGUARD_TRIAGE_AGENT`), off-gate feedback
   (`PIPEGUARD_FEEDBACK_AGENT`), pipeline-repair (`PIPEGUARD_PIPELINE_REPAIR_AGENT`), archivist
   (`PIPEGUARD_ARCHIVIST_AGENT`), and node-authoring (`PIPEGUARD_NODE_AUTHOR_AGENT`, REQ-F-025,
   2026-07-10) — all `stub|claude`; model via `PIPEGUARD_*_MODEL`. *Trace:*
   [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md), [architecture.md](../design/architecture.md)
   §Swappable seams, [agents.md](../design/agents.md).
2. **REQ-F-051 — Deterministic fallback on failure.** If an AI call is disabled,
   errors, or is refused by a safety classifier, the system degrades to the stub;
   the deterministic verdict and findings still stand. *Trace:* ADR-0006,
   [demo_plan.md](../demo/demo_plan.md) §Fallbacks.

## Authoring lifecycle, RBAC & operator surfaces (ADR-0010/0014/0016/0017)

Backend surfaces layered **over** the read-API, all **additive/backward-compatible**,
**off the deterministic gate** (never set/override a verdict, confidence, or provenance
event; ADR-0001), and **offline-testable** with no auth wiring. They realize the
`draft→approve` review lifecycle, RBAC, and operator-workflow endpoints the
[backend-contracts handoff](../design/frontend/handoffs/2026-07-09-backend-contracts.md)
had reserved or listed as *not-yet-built*.

1. **REQ-F-060 — Identity + RBAC primitive (DEV SHIM).** `api/auth.py` gives the
   write/authoring surfaces one shared current-user + role source: a `Role`
   (**viewer | reviewer | approver**), an `Actor{id, role}`, `current_actor()` reading the
   `X-PipeGuard-Actor` / `X-PipeGuard-Role` request headers with a **permissive DEV-DEFAULT**
   (`id=dev`, `role=approver`) so the offline demo and tests need no auth wiring, and
   `require_role(*roles)` (raises **403** on an insufficient role). It is explicitly a
   documented **DEV SHIM** — it *trusts* the headers, so it is trivially **spoofable** and is
   **not** real authentication — behind a single swap point for a production identity provider.
   It grants access only; it never touches a verdict or finding (ADR-0001). *Trace:*
   [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md) §"NOT built #2",
   [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md),
   [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md),
   [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md).
2. **REQ-F-061 — Pipeline approve lifecycle.** `api/routers/pipelines_lifecycle.py` realizes
   the `draft→save→approve` review flow that REQ-F-045 previously only **reserved** on the
   pipeline envelope: `POST /api/pipelines/{name}/submit` (draft → **pending_review**,
   reviewer+), `/approve` (pending_review → **approved**, **approver-only**, stamps
   `approved_by` + records the diff baseline), `/dry-run?run_id=…` — a **READ-ONLY** locator
   resolver that checks a composed graph's locators against a real run directory
   (**compose ≠ execute**: it never triggers a run — ADR-0001/0003), and
   `GET /api/pipelines/{name}/diff` (vs the last emitted/approved version). Role gates come from
   `require_role` (REQ-F-060). *Trace:*
   [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md) §4/§"NOT built #2",
   [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md),
   [ADR-0016](../adr/ADR-0016-postgres-port.md),
   [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md)/[ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md),
   [tasks T-049](../planning/tasks.md).
3. **REQ-F-062 — Config/settings authoring store *(wishlist T-051)*.** `api/routers/settings.py`
   + `api/settings_store.py` add `draft→save→approve` **config-override** authoring with
   reviewer/approver RBAC (REQ-F-060), an audit trail, and **lenient sanity guardrails** (range
   checks, not clinical thresholds), storing each override as a **tolerant versioned envelope** in
   a pluggable store (`PIPEGUARD_SETTINGS_STORE=jsonl|sqlite|postgres`, degrade-to-JSONL, ADR-0016),
   mirroring the pipeline store (REQ-F-045). The override `name` is a server-validated **slug**
   (`^[A-Za-z0-9][A-Za-z0-9._-]*$`); the Settings screen now **slugifies** the display assay
   string before POSTing (2026-07-09 maintainer batch — the un-slugified name 422'd save and
   404'd approve). It **does NOT mutate the live runbook** — actually
   applying an approved override to a run is a documented **off-gate seam**, not yet wired, so
   REQ-F-015 (runbook profiles decide thresholds) still holds. **Sample-type dropdown
   (2026-07-10, T-095, commit `869cf55`, "S1"):** `SettingsAssayTable.tsx`'s threshold matrix
   previously showed Whole-blood and Saliva as two side-by-side columns; a Sample-type dropdown
   beside the Assay selector now picks one tissue at a time and the table shows a single value
   column — a pure presentation change (cleaner, scales as more sample types are added).
   Editing/save/approve, the per-tissue values, and the audit lifecycle above are unchanged
   (still keyed on assay × sample type). *Trace:*
   [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md) §"NOT built #1",
   [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md),
   [ADR-0016](../adr/ADR-0016-postgres-port.md),
   [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
   [journal 2026-07-10 batch6](../journal/2026-07-10-admin-settings-builder-wiring.md),
   [tasks T-051/T-095](../planning/tasks.md).
4. **REQ-F-063 — Review-queue / ticket domain.** `api/routers/review_queue.py` +
   `api/review_store.py` back the review-queue screen (REQ-F-042) with a persisted ticket
   domain: create/list tickets plus a **role-gated action lifecycle**
   (acknowledge / resolve / escalate / suppress / reopen — **all reviewer+approver** via
   `require_role`, REQ-F-060; RBAC relaxed 2026-07-09 (commit `586f832`) from an earlier
   approver-only resolve/suppress to match the design's reviewer-resolves-hold/rerun-ticket
   model — an escalate ticket's approver-only nuance stays a UI-level distinction, not this
   backend gate), a ticket `status`
   ∈ **open | in_review | resolved**, and recorded review-action timestamps. It is **off-gate** —
   a ticket, suppression, or resolution never changes a verdict or a finding (ADR-0001,
   consistent with REQ-F-004). **Selection UX redesign (2026-07-10, Wave 8, T-110, commit
   `1bc0072`, RQ2/RQ3) — frontend-only, no wire/write-path change:** the status filter is now the
   canonical `Tabs` selector (G5, REQ-F-042); a page-scoped Select-all/Clear-all sits above the
   list (RQ2 — scoped to the visible page, not the whole filtered set, so a batch-confirm count is
   never surprising); each run group is bound by an accent-lit `border-l-2` rail with the
   subheader select-all and every ticket checkbox aligned in one fixed gutter (RQ3, replacing an
   earlier floating-checkbox layout). *Trace:*
   [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md),
   [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md),
   [ADR-0016](../adr/ADR-0016-postgres-port.md),
   [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), REQ-F-042,
   [journal 2026-07-10 wave8](../journal/2026-07-10-frontend-wave8.md).
5. **REQ-F-064 — Decision-card QC readout (pure projection).** `api/card_readout.py` exposes
   `GET /api/runs/{id}/cards/{sid}/qc-readout` → an **API-layer projection** that joins the
   card's `metric_values` with the runbook `QCThreshold`s into a **gate-grouped
   Metric · Observed · Threshold · Status** table for the MetricsPanel (REQ-F-042 / T-045). It is
   read-only and **derives nothing new** — the core `DecisionCard`, its findings, and the gate are
   untouched (ADR-0001); Status is a deterministic restatement of the already-decided gate, not a
   re-evaluation. An ungated metric row is labelled with the registry's **display name** (e.g.
   "Ts/Tv ratio"), not the raw `our_key` (2026-07-10, `a9b06ad`). *Trace:* [schemas.md](../data/schemas.md) §DecisionCard/QC,
   [qc_metrics.md](../data/qc_metrics.md),
   [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [tasks T-045](../planning/tasks.md).
6. **REQ-F-065 — Runs-list reconciliations (Tier-0).** `GET /api/runs` gains, on top of the
   additive params in REQ-F-047: a `status` filter (**running | needs_review | released**, keyed to
   the honest lifecycle of REQ-F-046), `q` now matching **run_id OR platform** (case-insensitive,
   was run_id only), friendly sort aliases (**recent / urgent / date** over the raw sort keys), and
   **per-status facet counts** returned on an `X-PipeGuard-Status-Counts` response header. All
   optional and additive — no params still yields a byte-identical `RunSummary[]` body (REQ-F-047).
   *Trace:* [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md) §2,
   [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md), REQ-F-046/REQ-F-047,
   [tasks T-048](../planning/tasks.md).
7. **REQ-F-066 — Admin panel (`isAdmin`-gated governance, off-gate).** A `frontend/src/screens/Admin.tsx`
   screen at `/admin`, visible only when the LOGGED-IN identity's `isAdmin` is true — nav-gated in
   `Sidebar.tsx`, not a backend permission of its own. **Corrected 2026-07-10 (T-081,** commit
   `0f7e85f`**):** `isAdmin` is a **frontend-only governance capability** (`frontend/src/auth.ts`
   `ADMIN_IDS`, derived from the demo login roster — REQ-F-069) layered over the wire roles
   (viewer/reviewer/approver), distinct from "any approver" — an admin is an approver who *also*
   holds governance; `isAdmin` follows the **login** identity (`session`), not the "Act as" actor,
   so an admin can preview another role and still return. (Originally gated on "any approver";
   that framing is now stale and superseded by this row.) Three tabs: **(a) Users & roles** — an explicit **client-mock** roster (there is no
   backend user store; `api/auth.py` is a header dev-shim) with a per-user role selector and an
   "Act as" control wired to `RoleContext.setActor` (switches id+role together) so an operator can
   preview any seeded actor's RBAC surface, plus a persistent "dev auth shim, not an identity
   system" banner. **Role-staging (2026-07-10, T-092, commit `5774143`, "A1"):** a role change
   no longer applies on the first click of a toggle (a stray click could reassign a role) —
   the control is a dropdown, and a change **stages into a draft** ("unsaved" badge) behind an
   explicit Save/Discard bar; only Save writes the roster (re-syncing the live actor if its own
   role changed), and "Act as" now confirms before impersonating. Still the same client-mock
   roster ([risks.md](../quality/risks.md) RISK-035) — this hardens the legitimate UI path, not
   the underlying (already non-production) security boundary; **(b) Activity log** — a REAL, zero-new-backend audit feed merging
   `GET /api/settings/thresholds` + `GET /api/pipelines` + `GET /api/review/tickets` into one
   append-only when/actor/kind/target/status table, facet-filterable by kind (threshold/pipeline/
   ticket). **Paginated + expandable (2026-07-10, T-093, commit `8a14661`, "A2"):** the
   previously flat, uncapped list now paginates 25/50/100 with a numbered pager ("Showing X–Y of
   Z," resets on filter change), and each row is a compact summary expanding on click to a
   labelled Detail/Target/Actor/When panel (one open at a time); no backend change; **(c) System**
   — REAL reads of `GET /api/health` (new, trivial liveness endpoint) +
   the runbook's gate count + the metric-registry version/gated-count, labelled
   illustrative-not-clinical. **Built out (2026-07-10, T-094, commit `7c56564`, "A3/A4"):** gained
   an **Artifact-store** stat card (`local` · the `PIPEGUARD_ARTIFACT_STORE` s3 seam, built
   [tasks T-039](../planning/tasks.md), [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md)
   §3) and an **Observability** section linking the read-API's `/metrics` exporter,
   Prometheus (`:9090`), and the Grafana "PipeGuard — QC decision gate" dashboard (`:3000`, built
   under the telemetry-connector work) as off-demo-path links, with a note on bringing up the
   `deploy/telemetry/` compose stack; Users & roles also gained a per-user
   **password/email-reset** action — a labelled production seam (no live mail) that toasts what
   would happen rather than sending anything. Admin decides **who** may perform an off-gate product write and
   whose id lands in an audit `*_by` field — it never sets, overrides, or displays a
   verdict/finding/confidence, and carries **no confidence meter** (ADR-0001; life-science
   guardrail 2). *Trace:* [architecture.md](../design/architecture.md) §4,
   [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
   [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md), REQ-F-060, REQ-F-069,
   [journal 2026-07-09 frontend-batch2](../journal/2026-07-09-frontend-batch2.md) (commit
   `ce396f7`), [journal 2026-07-10 batch5](../journal/2026-07-10-batch5-builder-card-admin-prefs.md)
   (commit `5774143`),
   [journal 2026-07-10 batch6](../journal/2026-07-10-admin-settings-builder-wiring.md) (commits
   `8a14661`, `7c56564`), [tasks T-066/T-092/T-093/T-094](../planning/tasks.md).
8. **REQ-F-067 — Samplesheet submission triggers the real pipeline (execution boundary).**
   `POST /api/runs` (new `api/routers/intake.py`) registers a submitted samplesheet and
   **triggers** `scripts/run_giab_pipeline.py` as a background subprocess (an in-process job
   registry; `require_role(reviewer|approver)`; 409 on a duplicate run id), turning
   `data/<run_id>/` into a gate-able run; `GET /api/runs/{id}/intake-status` polls
   `queued|running|complete|failed`, **now widened to `|lost`** (2026-07-11, REQ-F-091): a job whose
   owning process died mid-run (e.g. a backend restart) recovers to `lost`, not an indefinite
   `running`. This demo build only has real reads on disk for `HG002` —
   other submitted samples are **honestly skipped** (registered, reported, never fabricated a
   run for), and a submission with no processable sample 422s. **Compose ≠ execute still holds
   at the core:** `src/pipeguard/` never runs a tool — only the API layer triggers the external
   driver, mirroring the Pipeline Builder's hand-off concept (REQ-F-045) but now wired end to
   end. Reframes the earlier "Submit never runs anything" framing to "Submit hands off to an
   execution boundary." **Update (2026-07-11, T-123):** the triggered driver is now
   **Nextflow-first** — it no longer calls fastp/bwa-mem2/samtools/… itself; it runs `nextflow run
   pipelines/germline/main.nf` (the committed reference pipeline — see REQ-F-085) via
   `subprocess.run` and parses the published QC outputs. This endpoint's own contract (job
   registry, RBAC, polling, HG002-fixture scope) is unchanged — only what the subprocess does
   internally changed. Verified live on real GIAB HG002 reads (`completed=7 failed=0`, matching
   the pre-Nextflow QC numbers). *Trace:* [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
   [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md),
   [design/nextflow-codegen.md](../design/nextflow-codegen.md),
   [journal 2026-07-09 frontend-batch3](../journal/2026-07-09-frontend-batch3.md) (commit
   `e77c2e6`), [journal 2026-07-11](../journal/2026-07-11-nextflow-codegen-execution.md),
   [tasks T-057, T-123](../planning/tasks.md).
9. **REQ-F-068 — Honest three-gate decision-card readout.** The QC-readout hero always shows
   all **three** gates (preflight → qc → variant), never silently dropping one. `GET
   /api/runbook`'s `RunbookThreshold` carries `pipeline_gate: Gate` (from the metric registry),
   distinct from the numeric `gate` threshold *value* — the two were previously conflated, so a
   client-side filter comparing a value to the gate enum silently never matched and the
   preflight/variant groups vanished. Per gate: a real measured-metric group if the card
   populated one; else the runbook's thresholds rendered as `not_measured` placeholder rows
   (REQ-F-064); else an **honest empty-state note** — preflight is rule-based (scored via the
   gate strip + cited evidence, not a metric table) and variant extracts no gating metrics in
   this build — never a fabricated row. The gate stays byte-for-byte unchanged; no
   preflight/variant thresholds were added to the runbook (doing so would spuriously flag every
   card via `rules.py`'s QC-\*-NA path). *Trace:*
   [qc_metrics.md](../data/qc_metrics.md) §Verdict policy, REQ-F-064,
   [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md),
   [journal 2026-07-09 frontend-batch3](../journal/2026-07-09-frontend-batch3.md) (commit
   `12ffa30`), [tasks T-073](../planning/tasks.md).
10. **REQ-F-069 — Demo login gate (frontend, NOT production auth).** A login screen
    (`frontend/src/screens/Login.tsx`) fronts every route; `App.tsx`'s `RequireAuth` redirects an
    unauthenticated visit to `/login` and preserves the intended destination. Four demo accounts
    (`frontend/src/auth.ts`: viewer / reviewer / approver / admin, one shared password) map to the
    same `Actor{id, role}` the API already consumes via `X-PipeGuard-Actor`/`-Role` (REQ-F-060) —
    login simply chooses which actor the app acts as; the session (`{id, role}` only, **no
    token/password**) persists to `localStorage` so a refresh stays signed in. Every production
    seam is a **labelled placeholder, not implemented**: OAuth/OIDC against a real IdP, server-side
    password hashing (argon2/bcrypt — passwords never reach the client), an httpOnly/Secure/
    SameSite session cookie or JWT+refresh, a real CAPTCHA, signed password-reset links, and TLS.
    A generic "Incorrect email or password" message never reveals which field missed. This is a
    **demo-only client-side gate** — it adds no server-side protection; `api/auth.py`'s header
    dev-shim (REQ-F-060) is unchanged and remains the actual (also non-production) authorization
    boundary. *Trace:* [architecture.md](../design/architecture.md) §4,
    [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md) §Realized addendum,
    REQ-F-060, REQ-F-066, [risks.md](../quality/risks.md) RISK-035,
    [journal 2026-07-10](../journal/2026-07-10-provenance-qc-builder-auth.md) (commit `0f7e85f`),
    [tasks T-081](../planning/tasks.md).
11. **REQ-F-070 — Provenance artifact download + full-digest reveal.** `GET
    /api/runs/{id}/artifacts/{name}` (`api/main.py`) serves the named artifact's bytes
    (`FileResponse`); the name must be a bare filename and the resolved path must stay inside the
    run directory (traversal-hardened — a `..`/absolute name 404s, never serves outside the run
    dir). `RunArtifact` gained a `url` field pointing at it, closing the earlier "no download URL"
    gap. The Provenance screen's digest column now offers a "show full" toggle revealing all 64 hex
    characters, and — a defense-in-depth UI choice, not a wire-format change — labels the field
    "hash"/"content hash" rather than naming "sha256" on screen (Provenance + the Archivist
    manifest modal); the underlying field is unchanged content-hash sha256
    ([schemas.md](../data/schemas.md) §ArtifactRef). The artifact-stage map (`_ARTIFACT_STAGE`)
    now attaches each file to a **list** of `(stage, role)` edges (was one), so
    `demux_stats.csv`/`reads` are both the demux stage's OUTPUT and the QC stage's INPUT — the
    same bytes feed the QC node in the Provenance compute-DAG (REQ-F-042), which previously
    rendered with no input edge at all. **View vs. download split (2026-07-10, T-090, commit
    `de5fa94`):** the endpoint gained `download: bool = False` — `Content-Disposition` is
    `inline` by default (name-click views the artifact at its location) and `attachment` only on
    `?download=1` (the Download button); previously both hit the same always-attachment URL and
    both forced a save. The Provenance screen also gained a hover explainer distinguishing
    `sample_metadata.csv` (intake · LIMS/subject sheet) from `SampleSheet.csv` (demux · Illumina
    barcode manifest) — the difference previously lived only in the stage grouping. *Trace:*
    [architecture.md](../design/architecture.md) §4,
    REQ-F-040, [journal 2026-07-10](../journal/2026-07-10-provenance-qc-builder-auth.md) (commits
    `71a06d6`, `eb7d016`),
    [journal 2026-07-10 batch5](../journal/2026-07-10-batch5-builder-card-admin-prefs.md) (commit
    `de5fa94`), [tasks T-077/T-080/T-090](../planning/tasks.md).
12. **REQ-F-071 — QC enrichment: registered preflight/QC/variant metrics wired end-to-end.** The
    core `QCMetrics` model, `parsers.parse_qc_metrics`, and the QCMetrics→registry mapping gain 8
    additional registered fields beyond the frozen-CSV five (`preflight.phix_aligned`;
    `qc.breadth_20x`/`breadth_30x`/`pct_mapped`/`on_target`; `variant.dp`/`gq`/`titv`,
    [schemas.md](../data/schemas.md)), each `None`-tolerant so a run that omits them is unchanged.
    `runbook.QCThreshold` gains `required: bool = True`; 5 of the 8 gain an **optional**
    (`required=False`) threshold that scores a value that IS present but never NA-flags one that's
    absent (REQ-F-016 still holds — gating stays on the registry's canonical, normalized value).
    This closes a real gap: the decision-card readout's **preflight** and **variant** gate groups
    (REQ-F-068) previously showed an empty-state note for *every* run, with no code path that
    could ever populate them; they now populate with real measured rows when a run's QC report
    carries the data. The synthetic generator emits all 8 (contrived, comfortably passing, so
    failure-mode coverage stays exactly on the original frozen five); the real GIAB HG002 driver
    additionally writes its own real `breadth_20x`/`breadth_30x` from mosdepth (not contrived) —
    the metric catalog is now 10 gated / 10 ungated of 20 registered `our_key`s
    ([metric_registry.md](../data/metric_registry.md) §Wiring status), and 7 registered metrics
    remain unwired (an honest, pre-existing gap, not introduced by this change). Gate verdict
    logic and every pinned demo verdict are unchanged. *Trace:* [qc_metrics.md](../data/qc_metrics.md)
    §Implementation status, REQ-F-012/REQ-F-013/REQ-F-064/REQ-F-068,
    [journal 2026-07-10](../journal/2026-07-10-provenance-qc-builder-auth.md) (commits `a8fc73b`,
    `a9b06ad`), [tasks T-082](../planning/tasks.md).
13. **REQ-F-072 — Gate dependency: an unclear upstream gate blocks its downstream ones
    (re-presentation).** The maintainer's two-tier gate model: sequencing-tier QC (preflight)
    gates sample **processing**; sample-tier QC gates **downstream analysis** (variant). Every
    gate the QC-readout hero renders now carries `blocked_by: Gate | None`
    (`api/card_readout.py`'s `GateReadout`): `build_qc_readout` marks a gate "not clear" when the
    card carries a non-`PROCEED` `gate_result` for it, then `_blocking_gate()` returns the
    nearest **upstream** not-clear gate. A gate blocked this way renders "blocked · clear
    \<upstream\> first" instead of "all clear" (a `hold`-toned pill, taking priority over
    "all clear"/`not_measured`), so a QC hold no longer looks like the sample proceeded to
    variant calling. **Pure re-presentation, no rule or verdict change** — the card's verdict
    already reflects the upstream finding (REQ-F-003, REQ-F-014 hold); confirmed by diff that
    `rules.py`/`synthesis/` are untouched. The frontend (`MetricsPanel.tsx`'s `Rollup`,
    `RunDetail.tsx`'s `CardBody`) mirrors the same nearest-upstream computation for the
    placeholder/empty gate groups it synthesizes client-side (REQ-F-068), so the presentation is
    consistent whether or not the API returned real rows for that gate. New test
    `test_qc_hold_blocks_the_downstream_variant_gate` (`tests/test_card_readout.py`). This is
    "part 1" of the two-tier model per the maintainer. **Part 2 — user-clearable HOLD/ESCALATE,
    individually + in batches — shipped 2026-07-10 (T-097, commit `a8fd059`):** the review-queue
    screen (`ReviewQueue.tsx`, REQ-F-042/REQ-F-063) now gives reviewers+ a select checkbox on every
    still-open (open/in-review) ticket plus a per-run select-all in the group subheader; selecting
    ≥1 raises a sticky batch bar ("N selected — Resolve selected / Suppress selected / Cancel")
    that reuses the **same backend-persisted** per-ticket `act()`/`toggleSuppress()` path
    (materialize ticket → `ticketAction`), so a bulk clear persists exactly like a single click
    (verified across a reload: Open 88→86, Resolved 1→3). Selection resolves against the live
    ticket list each render, so a key that has since left the clearable set can't re-fire an
    action; viewers see no checkboxes. The DC2 model's "HOLD is a *state*, ESCALATE is *requesting
    input*, both clearable" is thus realized — off-gate (clearing a ticket never moves a verdict,
    ADR-0001). *Trace:*
    [architecture.md](../design/architecture.md) §4, REQ-F-003, REQ-F-014, REQ-F-042, REQ-F-063,
    REQ-F-064, REQ-F-068,
    [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
    [ADR-0008](../adr/ADR-0008-issue-taxonomy-suppression-escalation.md),
    [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md),
    [journal 2026-07-10 batch5](../journal/2026-07-10-batch5-builder-card-admin-prefs.md) (commit
    `545c893`), [journal 2026-07-10 batch6](../journal/2026-07-10-admin-settings-builder-wiring.md)
    (commit `a8fd059`), [tasks T-087/T-097](../planning/tasks.md).
14. **REQ-F-073 — Persisted user preferences (theme, density).** A new
    `frontend/src/context/PrefsContext.tsx` makes the Settings dialog's Theme
    (light/dark/system) and Density (split/brief/dense) controls real, `localStorage`-persisted
    preferences, replacing local state wired to nothing. Theme resolves `system` via
    `matchMedia('(prefers-color-scheme: dark)')` and stamps `document.documentElement.dataset.theme`,
    following the OS live while on `system`; a full dark theme in `index.css`
    (`:root[data-theme="dark"]` overriding the `@theme --color-*` custom properties — page/card/
    surfaces/text/accent + dark verdict bg/border/fg + shadows) retargets every existing Tailwind
    utility with **no per-component change**. Density is now **one** setting read/written by
    both the Settings dialog and `RunDetail.tsx`'s own card-Layout control (previously two
    independent, disconnected `useState`s), so the operator's choice survives across runs and a
    page refresh. This is a **client-only demo preference store**, not a server-synced profile
    (a production seam, like the auth session, REQ-F-069) — it never touches a verdict, finding,
    or the provenance ledger. *Trace:* [design/frontend/README.md](../design/frontend/README.md)
    §4, [journal 2026-07-10 batch5](../journal/2026-07-10-batch5-builder-card-admin-prefs.md)
    (commit `08a42ad`), [tasks T-091](../planning/tasks.md). **Amended 2026-07-10 ("Wave 7," T-105,
    commit `52124d3`):** theming now extends to the **left nav**, previously dark in both modes.
    A new `--color-nav*` var family is LIGHT in the base `@theme` (white nav, dark text,
    accent-tinted active pill) with the original dark-nav values moved into the
    `:root[data-theme="dark"]` override; `Sidebar.tsx` consumes every var end-to-end. The same
    commit also **reverted** the light-mode content palette from T-098's warm japandi trial back
    to a cool clinical palette (`--color-page #eef1f5`, `--color-card #f9fbfd`) — a maintainer
    aesthetic call, not a new capability; the theme/density mechanism itself (this requirement) is
    unchanged.
15. **REQ-F-074 — Submit: real samplesheet + `sample_metadata.csv` parsing (closes the
    registration-only-mock limitation).** `Submit.tsx`'s Upload panel previously had no `<input
    type=file>` and a hardcoded "Parsed 4 samples" chip; it now parses **for real** on drop or
    Browse, tolerant of a missing/renamed column (a signal, not a crash — CLAUDE.md Data-handling
    2). Two formats: an **Illumina v2 SampleSheet** (`[Header]` key-values + a `[*_Data]` section,
    auto-detecting run name/study/assay/platform) and a **plain CSV**
    (`Sample_ID,Sample_Type,index,index2,Study`). A new **`sample_metadata.csv`** attach (the
    LIMS/subject sheet — previously no upload path existed for it at all) parses
    `Sample_ID,Subject_ID,Tissue`, merges tissue into the sample's type column, and shows the
    subject id under each sample name. **`subject_id`/`tissue` are held client-side only** — a
    labelled seam, not persisted: `POST /api/runs`'s `SubmitRunIn`/`SampleIn`
    (`api/routers/intake.py`) carry no subject field and `extra="forbid"` would reject one; server-
    side persistence is the next Submit step, gated by the data-platform design's G-PII/G-DEID
    guardrails ([data-platform-and-archivist.md](../design/data-platform-and-archivist.md)) which
    are unaffected by this change. Sample-table pagination (25/page) and a scale-aware submit
    toast (summarize past 5 names, never `join()` 100 of them) keep a large mixed flowcell
    navigable. A companion fix (`api.ts`'s `httpError()`) surfaces the backend's real FastAPI
    `detail` — string or 422 `[{msg}]` array — in every failed write's toast instead of a bare
    status line, app-wide; no wire-contract change. `POST /api/runs`'s execution boundary
    (REQ-F-067), its `HG002`-only fixture scoping, and honest sample-skip behavior are all
    **unchanged** — only the input to that boundary is now real. Verified live with a generated
    100-sample mixed DNA/RNA sheet + a 100-row metadata sheet (parse, auto-detect, subject/tissue
    merge, 4-page pager) and an honest 422 (shown with the backend's real message) for a
    no-fixture sample. **Bulk-edit rework (2026-07-10, Wave 8, T-111, commit `24fe2e3`, S1-S3) —
    frontend-only, no wire change:** the sample-type cell is now a real `<select>` (S1, was a
    click-to-cycle button); per-row trash icons are replaced by checkbox multi-select + an
    indeterminate header select-all + a confirmed, draft-only "Remove N" (S2); "Add sample"
    becomes a bounded (1–500) bulk-add-N (S3), so a 100-sample plate isn't 100 clicks. *Trace:*
    REQ-F-067, [architecture.md](../design/architecture.md) §4,
    [journal 2026-07-10 wave4](../journal/2026-07-10-wave4-submit-parsing-and-api-errors.md)
    (commits `f8d9ea0`, `1bb79b8`),
    [journal 2026-07-10 wave8](../journal/2026-07-10-frontend-wave8.md) (commit `24fe2e3`),
    [tasks T-101/T-111](../planning/tasks.md).
16. **REQ-F-075 — Explicit-confirm gate on stakes-y off-gate writes.** A reusable
    `ConfirmDialog`/`useConfirm()` primitive (`frontend/src/components/ConfirmDialog.tsx`; a
    `ConfirmProvider` mounted at the app root, `App.tsx`) requires a named, explicit
    confirmation before any cascading/state-changing off-gate write fires — realizing the
    standing rule that no single accidental click may trigger one. **Review queue**
    (REQ-F-063/REQ-F-072): Resolve/Escalate/Reopen confirm first, each naming its effect and
    that it lands in the audit log; Suppress uses a DANGER-toned confirm naming the cascade
    (future occurrences of the rule, across runs, hidden until un-suppressed); batch
    Resolve/Suppress confirm the selected count. **Acknowledge and un-suppress stay direct
    one-clicks** — low-stakes, non-destructive, matching the T-097 batch-clear framing.
    **Admin Act-as** (REQ-F-066) swaps its native `window.confirm` for the same branded
    dialog. **No wire-contract or persistence change** — every confirmed action still calls
    the exact backend write it always did (`ticketAction` / `RoleContext.setActor`), so it
    lands in the Admin Activity audit feed exactly as before; this is a client-side
    deliberateness gate, not a new capability or a new audit source (confirmed by
    `git diff --stat 9733842 d65c9c1 -- src/ api/ tests/` = empty). *Trace:* REQ-F-063,
    REQ-F-066, REQ-F-072,
    [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md) (realized addendum),
    [architecture.md](../design/architecture.md) §Invariants,
    [risks.md](../quality/risks.md) RISK-035,
    [journal 2026-07-10](../journal/2026-07-10-confirm-dialog-audit-gate.md),
    [tasks T-102](../planning/tasks.md).
17. **REQ-F-076 — Settings: agent roster as a scale-aware table with explicit edit.** The
    Settings model-tiering card (REQ-F-042) is now `SettingsModelTier.tsx`'s table of the full
    advisory-agent roster — **Agent · Purpose · Model · Status · Edit**, capped 10 rows/page —
    replacing the earlier 3-item dropdown-applies-on-change card. Rows: synthesizer, QC-triage,
    pipeline-repair, archivist, feedback-categorizer, node-author (roster #5, still
    design-note-only per [agents.md](../design/agents.md)), and a new **metrics-expansion agent**
    row — a proposed **phase-2** idea (ST2: propose new QC metrics to track + wiring) with **no
    backend agent module or env var** (confirmed: `PIPEGUARD_METRICS_AGENT` appears nowhere under
    `src/`/`api/`), explicitly not to be read as a shipped roster addition. Each row edits behind
    a pencil into a staged draft (model + live toggle); **nothing applies until an explicit
    Save** (Cancel discards) — the same deliberateness principle REQ-F-075 established for
    stakes-y writes, applied here even though this table has no backend write at all (Save only
    updates local React state; the T-045 "UI-only, not wired to `PIPEGUARD_*_MODEL`" gap is
    unchanged). A "New agent" button links to the Pipeline Builder (`/builder`), the closest
    existing agent-authoring surface. Verdicts stay rule-derived — this is an operator *view* of
    config, never a control that can move a gate (ADR-0001). `git diff --stat c79f62c 7b579bb --
    src/ api/ tests/` empty (frontend-only). *Trace:* REQ-F-042, REQ-F-075,
    [design/agents.md](../design/agents.md),
    [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md),
    [tasks T-103](../planning/tasks.md),
    [journal 2026-07-10](../journal/2026-07-10-settings-agent-table.md).
18. **REQ-F-077 — Inbox: a personal, off-gate notification/triage workspace.** A new `/inbox`
    surface (`frontend/src/screens/Inbox.tsx` + `context/InboxContext.tsx` + a top-bar
    `NotificationBell.tsx`) replaces the dead top-bar bell with an intentional way for an operator
    to organize what needs doing, realizing the standing maintainer complaint that "a scrolling
    list isn't enough, users get lost, changing pages loses their place, no way to flag/unflag."
    **Entirely off the deterministic gate** (the same posture as the in-app feedback widget,
    REQ-F on feedback) — it never sets or reads a verdict, finding, or confidence, and requires
    **no new backend endpoint**: notifications are DERIVED, client-side, from the already-off-gate
    review-queue's `api.listTickets({status: 'open'|'in_review'})` (escalate/rerun/hold tickets).
    The operator's overlay on each item — read/unread, flag, priority, kanban column, due date,
    a note — plus any self-authored reminders are stored in `localStorage`, **scoped per operator**
    (keyed by `actor.id`, re-read whenever the acting identity changes — including Admin's "Act as,"
    REQ-F-066 — so a re-fetch never clobbers triage state and a page change never loses it, per the
    maintainer's ask). Four tabs: **Inbox** (filterable All/Unread/Flagged stream, each row
    expanding to priority/column/due/note/open-in-queue), **Board** (a 4-column native
    drag-and-drop kanban — Inbox/To do/In progress/Done; moving a card marks it read), **Calendar**
    (a month grid dotting due dates + a day-detail panel + a reminder composer), **Notes** (a
    note-to-self composer + inline-editable notes on any item). The Sidebar gains an "Inbox" nav
    item (Operate group) and the top-bar bell dropdown (`NotificationBell.tsx`) both read the same
    shared `unreadCount`, so the badge and the workspace can never drift apart. Shared visual
    tokens (source/priority/column/due-status meta, `timeAgo`, `dueStatus`) live in `inbox.ts`;
    `dueStatus`/`todayYmd` deliberately use **local** `yyyy-mm-dd`, not `toISOString()` (UTC), so a
    reminder due "today" can't read as overdue across a UTC-date rollover. **Distinct from the
    outbound `notify/` port (ADR-0010, Slack/Teams/Discord)** — that is a server-side push to an
    *external* channel triggered by `run_gate`; Inbox is a client-only, per-browser personal
    organization layer over data the operator can already see in the Review queue, and never
    leaves the browser. **Honest limitation:** this is per-browser `localStorage` state, not
    synced across devices — clearing site data or switching machines loses an operator's
    triage/board/reminders (the same class of limitation as `PrefsContext`, REQ-F-073, and the
    Monitoring clear/restore-signatures view filter). Verified live (light + dark): all four tabs,
    drag-and-drop updates every badge, a calendar reminder lands as "Due today," the bell dropdown
    triages inline, no console errors. `git diff --stat b4c3672 d832553 -- src/ api/ tests/` empty
    (frontend-only). tsc + oxlint clean. **Amended 2026-07-10 (Wave 8, T-113, commit `2865dac`,
    IB1-3,5-8) — frontend-only, no wire change:** mark-all-unread (IB2); the calendar composer
    drops its redundant date suffix (IB3); notes are gated read-only until Edit is clicked (IB5,
    was a live always-editable textarea); each note shows created/edited timestamps
    (`InboxContext` tracks `updatedAt` on an explicit save, IB6); delete moves inside edit mode +
    a confirmed checkbox mass-delete (IB7); a folder system — add/delete/move/filter, deleting a
    folder re-points its notes to Unfiled so nothing orphans (IB8); Google/Outlook calendar
    connectors render as labelled phase-2 seams, no real OAuth (IB1). **IB4 (per-reminder
    Slack/Discord/Teams/email notification + cadence) stays explicitly DEFERRED** — the
    commit body's own words, "the largest, next"; no notification-channel code exists yet. *Trace:*
    REQ-F-042 (review-queue tickets), REQ-F-066
    (Act-as), REQ-F-073 (the `localStorage`-preference precedent),
    [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md) (the outbound-notify contrast),
    [architecture.md](../design/architecture.md), [design/frontend/README.md](../design/frontend/README.md)
    §5.11, [journal 2026-07-10 wave7](../journal/2026-07-10-frontend-batch7.md) (commit `d832553`),
    [journal 2026-07-10 wave8](../journal/2026-07-10-frontend-wave8.md) (commit `2865dac`),
    [tasks T-108/T-113](../planning/tasks.md).
19. **REQ-F-078 — Provenance: Lineage / Event trail / Artifacts (PV1).** `Provenance.tsx`
    (2026-07-10, Wave 8, T-114, commit `0e64fad`) becomes a thin container over a persistent
    version-pins band + a `Tabs` switch of three views. **Lineage** — the original left→right
    stage DAG + per-stage I/O drill-in, preserved as the default. **Event trail** (new
    centerpiece, `components/provenance/EventTrail.tsx`) — a filterable (type/sample/actor +
    search + oldest/newest order), paginated timeline of the REAL events `run_gate` emits
    (verified: `src/provenance.ts` derives its vocabulary "ONLY from what the ledger actually
    emits," five types — `analysis_run.started`/`sample.registered`/`finding.emitted`/
    `verdict.decided`/`analysis_run.completed` — cross-checked against
    `src/pipeguard/provenance.py`'s six-member `EventType` enum, whose sixth member
    `NOTIFICATION_EMITTED` `run_gate` itself never emits, only the separate notify port does, so
    the frontend's "five emitted, everything else generic" framing holds); expanding a row is a
    trace-back — `finding.emitted` → its cited evidence in place, `verdict.decided` → the decision
    card + a deep link. **Artifacts** (new, `components/provenance/Artifacts.tsx`) — a
    grouped-by-name artifact index, filterable by stage/origin/role. **Needed zero backend
    change** — `RunDetail.events` (`types.ts:145`) already shipped to the client and the
    pre-rewrite screen simply discarded it; no new endpoint, no wire-contract change. 100%
    read-only: no verdict/confidence set, every finding/verdict shown is quoted verbatim from the
    event the rule engine authored (ADR-0001). Scale-aware: present-only filter options + 25/page
    pagination for a ~500-event run. Also lands the shared `components/Pager.tsx` (the "Showing
    X–Y of Z" idiom, deduplicated out of Runs/Monitoring/Admin/AgentTriage) and fixes a stale-error
    bug (the fetch effect now clears `error` on a runId switch). *Trace:* REQ-F-042, REQ-F-070
    (the artifact-download seam this view's Artifacts tab reuses),
    [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
    [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md),
    [provenance.md](../data/provenance.md), [architecture.md](../design/architecture.md),
    [design/frontend/README.md](../design/frontend/README.md) §5.6,
    [journal 2026-07-10 wave8](../journal/2026-07-10-frontend-wave8.md) (commit `0e64fad`),
    [tasks T-114](../planning/tasks.md).
20. **REQ-F-079 — Pipeline Builder: on-canvas editing (PB2).** `PipelineBuilder.tsx` +
    `BuilderCanvas.tsx` (2026-07-10, Wave 8, T-115, commit `109557e`) gain node selection (ring +
    a `UserNodeInspector` + double-click inline rename), wire deletion (hit-path select or
    midpoint ×), undo/redo (`hooks/useTopologyHistory.ts`, a bounded 50-entry ring snapshotting
    `{nodes, edges}` — **scope is topology only; `locEdits`/`refLoc` locator/reference authoring
    is NOT yet covered**, per the hook's own code comment) + toolbar/keyboard shortcuts, marquee
    multi-select + a `SelectionActionBar.tsx` (align/distribute/duplicate/delete), node/edge/
    canvas context menus (`BuilderContextMenu.tsx`), live alignment guides + snap, and
    drag-to-connect from output ports (the same typed/dedup validation as click-arm-click Connect
    mode). All work is over the local `userNodes`/`userEdges`/`locEdits` draft — **compose ≠
    execute still holds**; dry-run/diff (REQ-F-045) and the gate are untouched. **Anti-cascade:**
    any delete severing ≥1 edge, or any multi-node delete, routes through the existing
    `useConfirm` (REQ-F-075) naming the wire count — **stricter** than the design spec's "≥2
    edges" threshold, which was not shipped; every delete emits a "⌘Z to undo" toast, so all
    deletes are reversible. A module-init temporal-dead-zone crash (`BuilderShared`'s
    `ARTIFACT_KINDS` read `GIAB_LOC` before its declaration, blanking the app at runtime though
    `tsc` didn't flag it) was fixed by reordering the declarations. **Open item:** a new
    `components/Truncate.tsx` full-text-on-hover primitive shipped this commit has **no call
    sites yet** anywhere in `frontend/src` besides its own definition — added, not yet applied.
    *Trace:* REQ-F-045, REQ-F-075, [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md)
    (compose≠execute), [architecture.md](../design/architecture.md),
    [design/frontend/README.md](../design/frontend/README.md) §6,
    [journal 2026-07-10 wave8](../journal/2026-07-10-frontend-wave8.md) (commit `109557e`),
    [tasks T-115](../planning/tasks.md).
21. **REQ-F-080 — Intake gate: preflight sample-metadata grid (IG1).** The expanded sample-
    admission card in `Intake.tsx` (2026-07-10, Wave 8, T-112, commit `1052e15`) gains a metadata
    grid — Sample type / Library prep / Origin, **lazy-loaded** from the per-sample
    `CardReadout` header (`api.qcReadout`) **only when a row is expanded** (verified against the
    guard condition — `isOpen` is gated on the row's open/sparse/flagged state — scale-aware,
    never N+1 for a 100-sample run), plus run-level Platform / Run date and the sample's Verdict
    (already on hand, no extra fetch). A pending field shows a skeleton; a loaded-but-null field
    reads "not captured" — never a fabricated value. The yield bar is capped `max-w-[340px]`
    (mirroring the Runs verdict-bar convention), not a full-card sweep. Real, preflight-
    appropriate fields only — no analyzed/downstream data. *Trace:* REQ-F-042, REQ-F-064 (the
    `CardReadout` projection this reuses), [architecture.md](../design/architecture.md),
    [design/frontend/README.md](../design/frontend/README.md) §5.3,
    [journal 2026-07-10 wave8](../journal/2026-07-10-frontend-wave8.md) (commit `1052e15`),
    [tasks T-112](../planning/tasks.md).
22. **REQ-F-081 — Canonical Bar component + Truncate applied (G3/G2).** `components/Bar.tsx`
    (2026-07-10, Wave 9, T-116, commit `3e592d8`) gives every distribution/meter bar in the app
    ONE geometry (`h-2 · rounded-[5px]`, 2px segment gaps — was three heights, two radii, two gap
    sizes across the app). **`SegmentBar`** (a proportional multi-segment distribution; zero-value
    segments drop out so a strip never lies about the mix) now backs the Runs verdict bar, the
    Decision-cards `DecisionVerdictBar`, and the Review-queue `ReviewStatusBar` — verified: all
    three now `import { SegmentBar } from './Bar'` / `'../components/Bar'`. **`MeterBar`** (a
    single value against a track) now backs the Intake yield bar and the Monitoring gate-pass bars
    — verified the same way. Colors pass as full Tailwind utility classes (not string-interpolated)
    so the compiler emits them and theming holds in light+dark. Separately, `components/
    Truncate.tsx` (shipped Wave 8/T-115 with zero call sites) is **applied for the first time**, to
    the decision-card headline in `RunDetail.tsx` (verified: `grep -n Truncate RunDetail.tsx` →
    one import + one JSX use at line 288; `grep -rln Truncate frontend/src` now returns exactly
    `RunDetail.tsx` plus the component's own file). **This narrows, not closes, the open item this
    doc's Notes/deferred §4 previously tracked** — a broader sweep of other truncated card strings
    (run ids, sample names, artifact paths) remains explicitly open. Frontend-only (`git diff
    --stat 109557e 3e592d8 -- src/ api/ tests/` empty). *Trace:*
    [design/frontend/README.md](../design/frontend/README.md) §5.2/§9,
    [journal 2026-07-10 wave9](../journal/2026-07-10-frontend-wave9.md) (commit `3e592d8`),
    [tasks T-116](../planning/tasks.md).
23. **REQ-F-082 — Page-access RBAC view-gate + sample-accessioning CRM screen (G1).** A second
    frontend-only governance capability (2026-07-10, Wave 9, T-117, commit `66b14e4`), layered
    over the wire roles exactly like the existing `isAdmin` capability, and — the maintainer's
    explicit distinction — **NOT authorization**: `api/auth.py`'s `require_role` is verified
    unchanged in the diff and remains the sole server-side write check. `access.ts` — a closed
    12-page `PageId` catalog (`admin` intentionally excluded so an admin can never be page-gated
    out of governance), 6 read-only `ACCESS_PROFILES` (accessioning/wetlab/analysis/review/
    approval/governance), a per-user `UserGrant{profiles, overrides}`, and an `ACCESS_FLOOR` (Runs
    + Decision cards) re-asserted LAST in `effectivePages()` so no deny override can strand a user
    (verified: the floor re-assertion is the final statement in the function body).
    `context/AccessContext.tsx` resolves `canSee = isAdmin || !enforce || canSeePage(...)` against
    the ACTING actor (`actor.id`), so Admin's "Act as" naturally previews the impersonated user's
    nav; `localStorage`-persisted; every mutation appends a client-side `AccessAuditEntry` that
    merges into the Admin Activity log (badged "client-side," never confused with the three
    backend-persisted feed kinds). `App.tsx`'s new `<RequirePage page=…>` wraps every gated route
    → `components/PageAccessDenied.tsx`; `/admin`'s own route carries no `page` prop, so it stays
    governed solely by its pre-existing `isAdmin` guard, unaffected. `Sidebar.tsx`'s `useNav` now
    filters every nav item through `canSee` and drops any group left empty. Admin gains a fourth
    "Page access" tab (`components/AccessEditor.tsx`) — a paginated roster, a staged draft (profile
    checkboxes + a tri-state Inherit/Allow/Deny override per page), a live effective-nav preview,
    Save behind `useConfirm` (REQ-F-075), an Enforcement On/Off master switch, Reset to defaults,
    and a prominent "gates VIEWS not API enforcement" banner. New `screens/Accession.tsx`
    (`/accession`, leading the Operate "Steps" sub-sequence ahead of Submit — REQ-F-042) composes
    an `AccessionRecord[]` (drop a `sample_metadata.csv` via a tolerant parser — a missing/renamed
    column degrades to an empty cell, never a crash — or add subjects by hand, paginated,
    controlled-vocab dropdowns for tissue/sex/consent, checkbox multi-remove behind `useConfirm`),
    Export CSV, Save draft, and "Send to wetlab intake" (behind `useConfirm`) → a client-side
    `{subject_id, tissue}` `localStorage` one-shot handoff that `Submit.tsx` (REQ-F-074) now reads
    on mount and pre-attaches, then clears. **PII/PHI seam, verified against the actual guard:**
    no `AccessionRecord` field is ever sent over the network — `Accession.tsx`/`lib/accession.ts`
    make zero `api` calls; the screen's own banner cites `POST /api/runs`'s `SubmitRunIn`/
    `SampleIn` (`api/routers/intake.py`, confirmed unmodified) carrying no subject field and
    `extra="forbid"`, so subject/PII persistence is a labelled, not-yet-built data-platform seam
    (see [nonfunctional.md REQ-NF-023/REQ-NF-024](nonfunctional.md)); DOB/MRN are deliberately not
    modeled as fields (PHI) — only lab-operational fields (collection date, accession #, site)
    exist, and even those never leave the browser. `lib/csv.ts` extracts the shared tolerant CSV
    parser (`splitCsv`/`colIndex`/`csvCell`) out of `Submit.tsx`, behavior-identically, so both
    screens use one implementation. Frontend-only (`git diff --stat 3e592d8 66b14e4 -- src/ api/
    tests/` empty). *Trace:* [design/frontend/README.md](../design/frontend/README.md) §4/§5.12/
    §11, [architecture.md](../design/architecture.md),
    [journal 2026-07-10 wave9](../journal/2026-07-10-frontend-wave9.md) (commit `66b14e4`),
    [tasks T-117](../planning/tasks.md).
24. **REQ-F-083 — UI convention batch: shared primitives + per-screen safety/scale features
    (UIC-1..16).** (2026-07-10, "Wave 10," T-118, commit `6b571a4`, 33 files) implements the
    convention registry recorded in [design/ui-conventions.md](../design/ui-conventions.md) — that
    doc is now the source of truth for the full per-`UIC-N` spec + shipped status; this entry
    records only the functionally meaningful ones (pure re-styling — framed Tabs UIC-2, flavor-text
    removal UIC-1, nav reorder UIC-15 — is tracked there, not duplicated here). Built by a
    structured parallel workflow (4 shared-primitive agents behind a barrier, then 9 per-screen
    agents on disjoint files); tsc + oxlint clean, verified in-browser across every screen;
    frontend-only (`git diff --stat 71d4ff9 6b571a4 -- src/ api/ tests/` empty). All off the
    deterministic gate (ADR-0001).
    a. **UIC-3 — shared range-select checkbox model.** New `hooks/useRangeSelect.ts` (shift-click
       anchor→target range-select, Finder/Gmail semantics, + `setMany()` for parent→children) +
       `components/Check.tsx`; adopted in Review queue, Submit, and the Settings agent table
       (verified: `grep -rl useRangeSelect frontend/src` returns exactly those three screens).
    b. **UIC-7 — 3 light + 3 dark themes.** `index.css` `data-palette` blocks (Clinical/Sand/Slate
       light, Midnight/Carbon/Indigo dark) + `PrefsContext` palette state + a picker in
       `UserSettingsDialog`. Verdict/gate colors are inherited, never re-themed, so a palette
       choice cannot make a verdict illegible; contrast was hand-checked, not machine-audited.
    c. **UIC-11 — Submit: `sample_metadata.csv` required + a human-approved identity join.**
       `sample_metadata` is no longer optional; `Submit.tsx`'s `canSubmit` requires
       `join.metadataPresent && joinApproved`. `lib/accession.ts`'s `computeIdentityJoin()`
       corroborates `Sample_ID` **plus** tissue (never a single-column match) and classifies each
       row matched/weak/conflict/duplicate/unmatched; approval is bound to a join **signature** so
       any edit (a re-attached sheet, an added/removed row) auto-invalidates a prior approval — a
       human re-confirms identity after any change. Every join action is appended to a client-side
       `SubmitAuditEntry` log. Sample-identity mixups are the highest-consequence error this screen
       guards against. *See* [REQ-NF-025](nonfunctional.md).
    d. **UIC-13 — Admin: Act-as re-auth + immutable audit.** Impersonating another user now
       requires a password-confirm modal before it takes effect, and appends to an append-only
       `localStorage` audit log merged into Admin's Activity feed. **Labelled demo gap**: the
       re-auth step is a shared demo password, explicitly commented in-code and disclaimed in-UI
       as a production seam (real re-auth = an IdP step-up or a credential-request tool — a
       plaintext password field is never the intended production mechanism). Password-reset + role
       allocation moved into a dedicated per-user Edit view.
    e. **UIC-9 — Provenance: `fingerprint:` label + copyable event-trail code blocks.**
       `provenance/Fingerprint.tsx` renders the digest as `fingerprint:` + a show-full toggle (no
       leading partial, `overflow-x` so it never distorts the card); new `provenance/CodeBlock.tsx`
       backs `EventTrail.tsx`'s copyable code/error rendering.
    f. **UIC-10 — Review queue: run/sample checkbox hierarchy + reversible clear-from-view.** The
       run/flowcell checkbox sits left of a group line enclosing its sample tickets (`setMany`
       auto-toggles children); a reversible, localStorage-persisted clear/restore mirrors
       Monitoring's recurring-issue pattern (a "Cleared · N" section, never a DB purge).
    g. **UIC-12 — Settings: agent roster Active vs Available + mass-edit.** `SettingsModelTier.tsx`
       splits the roster into Active vs Available (the newly-built node-authoring agent, REQ-F-025,
       now surfaces as Available) and adds checkbox mass-select + remove + pagination.
    h. **UIC-14 — Inbox kanban: ids, body, comments, @-mentions, assignee.** Kanban cards gain a
       visible unique id, a body + comment section with @-mentions resolved to roster display
       names, and an assignee; the notification list paginates. **Open, noted at commit time**: a
       ticket derived from the review queue shows its raw internal id rather than the queue's
       `T-XXXX` display id — a cosmetic follow-up, not silently dropped.
    i. **UIC-16 — Builder canvas + palette.** The alignment dot grid now spans the full
       canvas at every zoom level; the tools palette shows the current pipeline's tools with a
       "≫ ALL" expander. **At the time, explicitly deferred**: the larger four-side-typed-port
       cards (the bigger rework `docs/design/builder-cards/` specifies) did not ship this batch.
       **Closed the next day (2026-07-11, commit `12a9913`):** cards grew to `NODE_W = 232` with
       typed half-circle ports on all four sides (`BuilderShared.portSide()`/`layoutPorts()`, one
       geometry source for render and wire math) — connection semantics unchanged, only card size
       and port placement. Only registering a few still-unused reserved kinds stays open
       ([builder-cards/README.md §5](../design/builder-cards/README.md#5-open--todo--spec-vs-shipped-updated-2026-07-11)).
    *Trace:* [design/ui-conventions.md](../design/ui-conventions.md) (the full per-item spec + status),
    [design/builder-cards/](../design/builder-cards/), REQ-F-025 above,
    [nonfunctional.md REQ-NF-025](nonfunctional.md), [tasks T-118](../planning/tasks.md),
    [journal 2026-07-10 wave10](../journal/2026-07-10-wave10-node-author-uic.md).
25. **REQ-F-084 — De-identified share/report egress, audited (ADR-0018 D3).** An **approver-only**
    `POST /api/runs/{run_id}/share` runs a run's already-decided cards (joined with intake identity)
    through `api.safe_harbor.redact_record` (the conservative Safe-Harbor-**style** scrub — direct
    identifiers dropped, dates generalized to year, free text mechanically redacted across the 18
    §164.514(b)(2) classes) and returns a `ShareBundle`: the scrubbed rows + a `ShareManifest`
    (policy id, row count, origin, a sha256 content hash of the exact emitted bytes, the event id,
    the 18 identifier classes, and an explicit non-compliance disclaimer). It is an **egress
    transform only** — reads already-computed `DecisionCard`s, never a rule/verdict/gate input
    (ADR-0001) — and records the egress as a `DATA_EXPORTED` `ProvenanceEvent` (a new, separate,
    pluggable sink, `api/share_store.py` — `PIPEGUARD_SHARE_STORE=jsonl|sqlite|postgres`,
    degrade-to-JSONL, matching the other four off-gate stores, [ADR-0016](../adr/ADR-0016-postgres-port.md)
    — distinct from the gate's own `EventLedger`; see
    [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md)) that `GET /api/runs/{id}`
    merges live into the run's Event trail. The Provenance screen
    (`frontend/src/screens/Provenance.tsx`) surfaces it as an approver-ONLY (absent, not merely
    disabled, for anyone else), `ConfirmDialog`-gated "Share (de-identified)" header action that
    toasts the manifest and refetches so the new trail row appears immediately. **Honest scope
    note:** this is **narrower** than the full Share window
    [design/variant-interpretation.md](../design/variant-interpretation.md) §4 describes — one
    fixed action (no scope/location/security-level selection, always the Safe-Harbor-style scrub,
    the bundle returned directly to the caller rather than staged anywhere), and the audited event
    lands in the run's own Provenance trail, not (yet) the Admin Activity feed. *Trace:*
    [ADR-0018](../adr/ADR-0018-variant-interpretation-advisory-evidence.md) decision D3 +
    [Realized](../adr/ADR-0018-variant-interpretation-advisory-evidence.md#realized-2026-07-11),
    [data/provenance.md](../data/provenance.md), [quality/evaluation.md](../quality/evaluation.md)
    EVAL-051, [tasks T-120](../planning/tasks.md),
    [journal 2026-07-11](../journal/2026-07-11-d2-d3-share-egress.md).
26. **REQ-F-085 — Pipeline codegen: compile a card graph → a runnable Nextflow pipeline
    (ADR-0003, realized).** A pure-text compiler (`src/pipeguard/nextflow/`) turns a Pipeline-
    Builder graph (`{nodes, edges}`, the Builder's exact save shape) into a runnable nf-core-style
    Nextflow DSL2 bundle (`main.nf`+`modules/*.nf`+`nextflow.config`+`README.md`) — it never
    invokes `nextflow` or any tool (compose ≠ execute, ADR-0001/0003). A curated `catalog.py`
    backs the 7 germline-chain tools with a real `script:` AND a `stub:` (bioconda +
    biocontainer packaging, typed ports keyed to the Builder's own artifact-kind vocabulary); an
    uncatalogued tool still compiles — wired for real — but as a labelled placeholder whose
    command fails loudly, **never a fabricated command**. The seeded germline chain compiles to
    the **committed reference pipeline** `pipelines/germline/`, pinned byte-for-byte by a drift
    test so "what the Builder emits" and "the canonical repo pipeline" are the same artifact.
    Exposed via **`POST /api/pipelines/compile`** (`api/routers/nextflow.py`, stateless, off-gate;
    `format=json` preview or `format=zip` download; a cycle/bad/empty graph → 422 with the
    compiler's reason) and the Builder's **"Export to Nextflow"** toolbar action
    (`NextflowExportModal`) — a capability addition alongside the pre-existing `run_layout.yaml`
    `Emit` (REQ-F-045): where Emit names which files feed which stage, this produces an
    actually-executable pipeline for the same graph. 14 new tests (`test_nextflow_compile.py`, 10,
    incl. a machine-gated live `nextflow run -stub-run` check that skips absent `nextflow`, never
    fails; `test_nextflow_api.py`, 4). *Trace:*
    [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
    [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md) (Realized 2026-07-11),
    [design/nextflow-codegen.md](../design/nextflow-codegen.md), REQ-F-045, REQ-F-067,
    [tasks T-123](../planning/tasks.md),
    [journal 2026-07-11](../journal/2026-07-11-nextflow-codegen-execution.md).
27. **REQ-F-086 — Approval-gated Builder pipeline execution (W1).** `POST /api/pipelines/run`
    resolves and compiles only a named pipeline's approver-blessed (`emitted`) baseline from
    `PipelineGraphStore` (`_resolve_approved`) — never a raw client-posted graph
    (`RunPipelineIn` is `extra="forbid"`, so a smuggled `graph` field 422s before anything
    compiles). A name with no approved version is a **409** (`"no approved version … submit and
    approve it before running"`), not a silent bypass; the Builder's "Run" action stays disabled
    until the current pipeline is approved. Closes the audit's P1-6/P3-14 finding — the endpoint
    previously ran the operator's live canvas graph with no approved-status check at all. A new
    committed helper, `scripts/seed_approved_germline.py`, idempotently composes→saves→submits→
    approves the seeded germline chain so a fresh store still has a runnable-by-name baseline for
    the demo/E2E "Run" beat. *Trace:* [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md)
    (Realized addendum 2026-07-11) — the draft→approve lifecycle now gates a real execution, not
    just config — REQ-F-054 (the Save→Submit→Approve lifecycle this consumes), REQ-F-085,
    [tasks T-126](../planning/tasks.md), [journal 2026-07-11](../journal/2026-07-11-audit-hardening-w1-w4-e2e.md).
28. **REQ-F-087 — RunDetail Report tab: a per-run QC Decision & Provenance report (W3).** A new
    `?view=report` tab on `RunDetail` (`RunReport.tsx`) renders a single-document report over
    data already on the wire (no new endpoint): verdict mix, a route-to-human hero panel quoting
    ClinVar significance **verbatim** (no authored pathogenicity, ADR-0004/G3/G4), per-sample gate
    outcomes with cited evidence, and a sign-off footer stating human sign-off is a labelled seam,
    not a button — PipeGuard never marks a report final on its own. Read-only; confidence stays
    omitted (T-019). Narrower than the full design: no interpretation agent, no per-variant
    evidence table, no persisted/signed report artifact. *Trace:*
    [ADR-0018](../adr/ADR-0018-variant-interpretation-advisory-evidence.md) Decision D1 (report
    framing) + [Realized](../adr/ADR-0018-variant-interpretation-advisory-evidence.md#realized-2026-07-11),
    [design/variant-interpretation.md §0](../design/variant-interpretation.md#0-build-status-update-2026-07-10-after-the-maintainers-d1d2d3-sign-off),
    [tasks T-128](../planning/tasks.md), [journal 2026-07-11](../journal/2026-07-11-audit-hardening-w1-w4-e2e.md).
29. **REQ-F-088 — Honest downstream provenance stages (`filter`/`review`/`share`) + the
    route-to-human lineage fix (W3).** The Lineage DAG (`Provenance.tsx`) grows from 6 to 9
    stages; `PipelineStage` (`types.ts`) gains `filter | review | share`, each reading "not run in
    this build" unless THIS build actually produced its artifact or fired its gate —
    `api/main.py`'s `_ARTIFACT_STAGE` gains the filename→stage seams (a `.norm.vcf.gz` →
    `filter`, a `route_to_human.json` → `review`, a `share_manifest.json` → `share`; none is
    emitted by any committed fixture, so all three read honestly empty today). **Fixes a real
    honesty bug**: a fired route-to-human ESCALATE (`VAR-RTH-001`, REQ-F not yet numbered — see
    ADR-0018 D2) used to render the review node as "skipped" (no VCF artifact) even though the
    rules had already escalated the sample; a fired gate now wins over the no-artifact default,
    so the review node reads ESCALATE, matching the decision the rules made. *Trace:*
    [ADR-0018](../adr/ADR-0018-variant-interpretation-advisory-evidence.md), REQ-F-078 (the
    Lineage/Event-trail/Artifacts Provenance rework this extends),
    [tasks T-128](../planning/tasks.md), [journal 2026-07-11](../journal/2026-07-11-audit-hardening-w1-w4-e2e.md).
30. **REQ-F-089 — Node-authoring agent read endpoint + the agent-authoring scaffold contract
    (W2).** A new read-only `GET /api/builder/node-proposal?request=…`
    (`api/routers/node_author.py`, off-gate, no RBAC write) makes the previously core-only
    `propose_node()` reachable over the wire; the Builder's `AuthorToolNodeModal` now renders the
    real `NodeProposal` (typed live/reserved port chips, a `platform_version` stamp, heuristic-
    labelled citation scores) instead of a static mock. `NodeProposal` gains `platform_version`
    (`identifiers.PLATFORM_VERSION`, sourced from `pyproject.toml`) so a proposal pins tool
    version + corpus + schema + platform. A new [design/agent-authoring-contract.md](../design/agent-authoring-contract.md)
    is the governing boundaries MD for any authoring agent (card or agent authoring): metadata-
    only output (never a `script:`/`stub:` body), the Nextflow-integration rules, UI dos/don'ts,
    and the seven-point convention for adding a 7th/8th advisory agent. **This corrects Notes
    item 7 below** — "no `api/` endpoint and no frontend wiring" is no longer true for the read
    path; the modal still never auto-adds a card (accept→draft-library-entry stays deferred).
    *Trace:* [design/node-authoring-agent.md](../design/node-authoring-agent.md),
    [design/agent-authoring-contract.md](../design/agent-authoring-contract.md), REQ-F-025,
    REQ-F-050, [tasks T-127](../planning/tasks.md),
    [journal 2026-07-11](../journal/2026-07-11-audit-hardening-w1-w4-e2e.md).
31. **REQ-F-090 — Nextflow executor profiles (local-serial / Slurm) + per-sample fan-out + full
    QC port wiring (W4).** The generated `nextflow.config` gains two baked-in profiles:
    `standard` (the demo default — local single-thread-serial) and `slurm` (env-driven queue/
    cluster-options, one sbatch job per process instance); `run_giab_pipeline.py` auto-detects
    `sbatch` on `PATH` and picks the profile. **Honest limit: CONFIG-verified, not
    CLUSTER-verified** — this repo's sandbox has no `sbatch`, so only the local-serial branch has
    actually executed; the Slurm profile has never run against a real cluster. Every catalogued
    process now carries the nf-core `[meta, files]` map and fans out per-sample
    (`ProcessSpec.per_sample`, default `True`; MultiQC is the one cross-sample aggregator,
    `per_sample=False`) — HG002 stays a degenerate fan-out of 1 in the LIVE driver; **the driver's
    post-run parse of a publish dir into N gate-able run-dir rows is now built (2026-07-11, W4
    continuation, REQ-F-095) and offline-verified against fixture publish dirs, but a genuinely
    live multi-sample Nextflow run stays unverified** (no second real sample's reads on disk in
    this sandbox — see REQ-F-095). `fastp_html`/`samtools_stats` are
    promoted from reserved/unwired to real, wireable optional ports (both are real commands the
    driver already ran); the mosdepth `regions`/`global_dist`/`region_dist` byproducts are wired
    too; MultiQC now ingests all 5 available QC streams (was 3). **This narrows, not closes,**
    REQ-F-085's "local execution only" limitation and REQ-NF-060's Slurm/cloud gap — see the
    updated Notes item 9 below and the REQ-NF-060 addendum. *Trace:*
    [design/nextflow-codegen.md](../design/nextflow-codegen.md),
    [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md) (Realized addendum 2026-07-11),
    REQ-F-085, REQ-F-095, [tasks T-129, T-134](../planning/tasks.md),
    [journal 2026-07-11](../journal/2026-07-11-audit-hardening-w1-w4-e2e.md).
32. **REQ-F-091 — Durable execution-job persistence + restart recovery.** The two execution
    routers (`api/routers/intake.py`'s `POST /api/runs`, `api/routers/pipeline_run.py`'s
    `POST /api/pipelines/run`) persist each background job's status via `api/job_store.py`
    (`JobStore` Protocol, `jsonl` default | `sqlite`, `PIPEGUARD_JOB_STORE`) instead of an
    in-process dict, so a backend restart no longer loses job state or leaves a poller hung on
    `running` forever. A restart-recovered job whose result dir is on disk resolves to `complete`;
    otherwise it resolves to a new terminal status, **`lost`** (distinct from `failed` — its owning
    process died, the work outcome is unknown), persisted so subsequent polls see a stable answer.
    Run-id reservation is **atomic**: the run-dir-exists check and the in-flight-job-set check
    happen together under one lock, so two concurrent submits of the same run id can no longer both
    proceed (one now gets a clean 409). The driver launch is now shared + process-group-aware
    (`run_driver()`, one `DRIVER_TIMEOUT_S`): a timeout `os.killpg`s the WHOLE Nextflow/JVM/tool
    subtree, not just the direct child, so a timed-out run leaves no orphaned subprocess.
    *Trace:* [ADR-0016](../adr/ADR-0016-postgres-port.md) item 8,
    [architecture.md](../design/architecture.md) §Swappable seams, REQ-F-067,
    [tasks T-131](../planning/tasks.md), [journal 2026-07-11 P3 backlog](../journal/2026-07-11-p3-backlog.md).
33. **REQ-F-092 — Pipeline preflight validation (fail loud, before the Nextflow launch).**
    `scripts/run_giab_pipeline.py` validates its inputs BEFORE handing them to Nextflow, so a bad
    input fails in milliseconds with an actionable message instead of burning a full launch (or,
    worse, silently yielding a wrong result): (a) FASTQ **pairing/format** — R1/R2 exist, are
    non-empty, look like FASTQ, and pair record-for-record on a mate-independent read id; (b)
    reference↔panel-BED **contig-naming** — every panel-BED contig must exist in the reference
    (catches a `20` vs `chr20` build mismatch, which would otherwise silently yield ~0% panel
    breadth); (c) reference-**index sidecar** presence (`.fai`, `.0123`, `.amb`, `.ann`,
    `.bwt.2bit.64`, `.pac`) — without these the run would launch, run fastp, and only then die deep
    inside bwa-mem2. Each guard raises a loud, actionable `sys.exit`; none ever silently proceeds.
    *Trace:* [design/nextflow-codegen.md §Pre-flight guards](../design/nextflow-codegen.md#pre-flight-guards--version-capture-2026-07-11-t-131),
    [tasks T-131](../planning/tasks.md), [journal 2026-07-11 P3 backlog](../journal/2026-07-11-p3-backlog.md).
34. **REQ-F-093 — Per-run resolved-version capture (`versions.txt`).** Every driver run writes
    `versions.txt` into the run dir: a best-effort snapshot of the resolved Nextflow/fastp/
    bwa-mem2/samtools/mosdepth/bcftools/multiqc versions actually on `PATH` at run time. This is
    **provenance capture only — it does NOT pin or change any container/conda tag** (a floating-tag
    re-pin stays out of scope, Medium risk per the audit); "deterministic reruns" for this project
    means wiring + gate re-derivation, not bitwise-identical tool output, so a per-run snapshot of
    what actually resolved is the honest reproducibility artifact available today. A probe failure
    (tool absent/erroring) is recorded, never fatal — capturing provenance must not break a run.
    *Trace:* [REQ-NF-005](../requirements/nonfunctional.md), [tasks T-131](../planning/tasks.md),
    [journal 2026-07-11 P3 backlog](../journal/2026-07-11-p3-backlog.md).
35. **REQ-F-094 — Per-variant Report table + read-only `GET /api/runs/{id}/variants` (W3
    continuation).** A new read-only endpoint (`api/main.py`) serves every `VariantCall` a run's
    `variants.csv` carries, parsed via the SAME `pipeguard.parsers.parse_variant_calls` the
    route-to-human rule (VAR-RTH-001) already uses — 404 for an unknown run, `[]` (never a 404 or
    a fabricated row) when a run has no `variants.csv`. `RunReport.tsx` renders it as a paginated
    table (Sample/Gene/HGVS/ClinVar significance quoted VERBATIM/review status/accession) beneath
    the route-to-human hero, with its own disclaimer that PipeGuard authors no pathogenicity and
    sets no verdict here (ADR-0004/ADR-0001). This closes the "no per-variant evidence table" gap
    REQ-F-087 and [variant-interpretation.md §0 item 3](../design/variant-interpretation.md)
    used to name — narrower than the full `AnnotatedVariant` model still design-only
    (no gnomAD population frequency, no inheritance-fit, no call-quality join). +3 tests
    (`tests/test_run_variants.py`). *Trace:*
    [ADR-0018 Realized item 5](../adr/ADR-0018-variant-interpretation-advisory-evidence.md#realized-2026-07-11),
    [design/variant-interpretation.md §0](../design/variant-interpretation.md),
    REQ-F-087, [tasks T-133](../planning/tasks.md),
    [journal 2026-07-11](../journal/2026-07-11-w-deferrals.md).
36. **REQ-F-095 — Multi-sample driver parse: N-sample publish dir → N-row run dir (W4
    continuation, offline-verified; live multi-sample run stays unverified).**
    `scripts/run_giab_pipeline.py`'s post-run parse is now genuinely N-sample capable:
    `discover_samples()` finds every sample from its per-sample `${id}.fastp.json`
    (dot-anchored + `glob.escape`, so a shared-prefix pair like `S1`/`S10` never cross-captures);
    `parse_publish_dir()` parses each into a `SampleMetrics`; `write_run_dir_multi()` writes the
    ONE run dir the gate already discovers, with N rows across every frozen-five CSV — the same
    "one run dir, N samples" shape `data/mock_run_01` already uses, so `run_gate_from_dir` yields
    N cards with **zero** read-API or gate change. A partial publish dir (a sample missing one
    required output) or an empty publish dir fails loud (`sys.exit`), never silently drops a
    sample or fabricates a metric. A fan-out of 1 (the live HG002 path) is BYTE-IDENTICAL to the
    pre-fan-out single-sample format. `api/routers/intake.py`'s `IntakeStatus` additively gains a
    `samples: list[SampleStatus]` field (per-sample `queued|running|complete|failed|lost|
    skipped` state; an older persisted job with no `samples` key yields `[]`, never an error).
    **Honest deferral (stated in the commit body verbatim):** this closes the parse/write/gate
    LOGIC gap only — proven against 7 fixture publish dirs
    (`tests/test_run_giab_multisample.py`), no Nextflow, no bioconda tools, no network. The LIVE
    driver still submits a **single-row** samplesheet (only HG002 has real reads on disk in this
    sandbox), so a genuinely live multi-sample Nextflow run — an N-row sheet driving a real
    fan-out, parsed by the logic above against Nextflow's real published output — has never been
    exercised. *Trace:* [design/nextflow-codegen.md §Multi-sample driver
    parse](../design/nextflow-codegen.md#multi-sample-driver-parse-2026-07-11-w4-continuation),
    REQ-F-090, REQ-F-067, [tasks T-134](../planning/tasks.md),
    [journal 2026-07-11](../journal/2026-07-11-w-deferrals.md).
37. **REQ-F-096 — Node-author accept → tool-card library, a conformance harness, and a structured
    doc-drop importer, ALL BACKEND-ONLY (2026-07-11, T-135, "W2 backend").** A new
    `POST /api/builder/node-proposal/accept` (`reviewer`/`approver`, `api/routers/node_author.py`)
    RE-DERIVES the proposal server-side from the submitted request (never trusts a client-supplied
    proposal), guards `matched`, runs it through a new deterministic
    `src/pipeguard/node_author/conformance.py` `check_conformance()` — mechanically asserting
    [agent-authoring-contract.md](../design/agent-authoring-contract.md)'s capability pins
    (`advisory` present and `True`; no `verdict`/`confidence` key anywhere in the candidate; no
    `script`/`stub` command-body key anywhere; every port kind is a real `ARTIFACT_KINDS` member or
    an explicitly-declared `reserved` one; `corpus_version`/`schema_version`/`platform_version`
    pinned, plus the tool `version` when matched) — and stores a `status="draft"` `LibraryEntry`
    (metadata only: ports, a pinned version, suggested locators, citations — **never** a
    `script:`/`stub:` command body) in a new pluggable `api/library_store.py`
    (`LibraryStore` Protocol, `PIPEGUARD_LIBRARY_STORE=jsonl|sqlite`, degrade-to-JSONL,
    **deliberately no Postgres adapter** — a node-local corpus of accepted drafts, not shared
    product state, [ADR-0016 item 9](../adr/ADR-0016-postgres-port.md)). `GET /api/builder/library`
    lists accepted entries (optional `tool`/`status` filters). A companion
    `src/pipeguard/node_author/importer.py` (`import_from_nextflow_schema`) deterministically parses
    an nf-core `nextflow_schema.json` into a `NodeProposal` for a tool **NOT** already in the
    curated 9-card corpus (was 11; see REQ-F-025 for the two post-11 retirements) — the structured, lowest-injection-risk half of the doc-drop importer
    REQ-F-025 notes is unbuilt; a `format: file-path` param maps to a real `ARTIFACT_KINDS` kind
    only on a confident, conservative name/pattern match, else a `reserved` slot (never invented).
    +34 tests (`test_library_store.py`, `test_node_author_accept_api.py`,
    `test_node_author_conformance.py`, `test_node_author_importer.py`). **Honest deferrals, named
    not dropped:** the Builder's own "Accept to library" button — no frontend caller of either new
    endpoint exists, verified: `grep -rn "node-proposal/accept\|builder/library" frontend/src`
    returns nothing, so the modal still never auto-adds a card; the `draft→approved` library-entry
    transition; the free-text `--help`/README half of the doc-drop importer (its own spike, per the
    module's own docstring); a roster-wide, CI-enforced conformance sweep (today's
    `check_conformance()` runs against one node-authoring candidate at accept time, not a
    parametrized test over the whole six-agent roster). *Trace:*
    [design/node-authoring-agent.md](../design/node-authoring-agent.md),
    [design/agent-authoring-contract.md](../design/agent-authoring-contract.md), REQ-F-025,
    REQ-F-089, [ADR-0016 item 9](../adr/ADR-0016-postgres-port.md),
    [tasks T-135](../planning/tasks.md), [journal 2026-07-11 fleet](../journal/2026-07-11-fleet.md).
38. **REQ-F-097 — A11y baseline extends to the shared view-selector/pagination/toggle primitives +
    form labels (2026-07-11, T-136, REQ-NF-070 addendum).** `components/Tabs.tsx` gains
    roving-tabindex + Arrow/Home/End keyboard navigation; `components/Pager.tsx` gains a `nav`
    landmark + `aria-current="page"`/`aria-label` per page button; `components/SegmentedControl.tsx`
    gains `role="radiogroup"` + `role="radio"`/`aria-checked` (+ an optional accessible `label`);
    `components/RunSelector.tsx` gains the combobox/listbox pattern (`role="combobox"`,
    `aria-expanded`/`aria-controls`/`aria-activedescendant`, arrow-key + Enter/Escape handling).
    `screens/Submit.tsx`/`Accession.tsx`/`Settings.tsx` gain `htmlFor`/`id` label↔input
    association, `aria-label` on grid-row inputs whose column headers are visual-only, and
    `aria-describedby` on hint text. Verdict-token contrast was **verified** (not assumed) to pass
    WCAG AA — all 8 fg/bg token pairings measure 5.5–9:1 — so no `index.css` change was needed; this
    is a verification result, not a new claim of full AA conformance app-wide (REQ-NF-070's scope
    caveat still holds). *Trace:* [design/ui-conventions.md](../design/ui-conventions.md) UIC-19,
    [nonfunctional.md REQ-NF-070](nonfunctional.md), [tasks T-136](../planning/tasks.md),
    [journal 2026-07-11 fleet](../journal/2026-07-11-fleet.md).
39. **REQ-F-098 — Operator-authored custom-script Nextflow processes ([ADR-0020](../adr/ADR-0020-operator-authored-custom-processes.md),
    2026-07-11, branch `feat/custom-script-io`).** A Builder card MAY carry a **human-authored**
    verbatim Nextflow `script:` body (plus optional `container`/`conda` packaging) — a third path
    alongside a catalogued tool and an uncatalogued placeholder. `NfNode`
    (`src/pipeguard/nextflow/compiler.py`) gains optional `script`/`container`/`conda` fields,
    absent on every ordinary card; a non-empty `script` marks the node `is_custom()`, and
    `_render_module` checks for it **before** the catalog, so the operator's body wins even if the
    card's tool name collides with a catalogued one — the catalog is never consulted for a custom
    node. The body is emitted **byte-for-byte** (only re-indented), never rewritten or fabricated;
    it is wired from the node's own typed `ins`/`outs` exactly like a catalogued per-sample process
    (meta-threaded). A **blank/whitespace** script is a `CompileError` (a 422 at
    `POST /api/pipelines/compile`) — PipeGuard never fabricates a command; an uncatalogued node with
    **no** script (`script is None`) is unaffected and keeps its existing labelled placeholder. The
    emitted process carries an honest header comment + `label 'operator_authored'` naming it
    operator-authored, not curated, and stating production needs sandboxing/allowlisting.
    `POST /api/pipelines/compile` (`api/routers/nextflow.py`) and `POST /api/pipelines/run`
    (`api/routers/pipeline_run.py`) both thread the three fields through additively — the seeded
    germline chain carries none, so its compiled output stays byte-identical (the drift guard
    holds). The Builder gains a **"Custom script"** palette card (amber/`warn`-toned) and a
    dedicated `CustomScriptInspector` (`BuilderModals.tsx`) — label, typed input/output ports
    (from the same `ARTIFACT_KINDS` vocabulary, never free-invented), the `script:` textarea, a
    runtime toggle (container OR conda — only the active one is sent), and locator authoring with a
    server-side Browse picker (REQ-F-099). **Four-way safety (ADR-0020):** (i) a custom script
    reaches a compute host only inside a SAVED, APPROVED pipeline via the pre-existing W1
    `POST /api/pipelines/run` gate (the stateless `/compile` path emits text only); (ii) the honest
    header/label above; (iii) agents stay metadata-only — `NodeProposal`/`PortSpec` carry no command
    field, so this card is the human-authoring surface
    [agent-authoring-contract.md](../design/agent-authoring-contract.md) already presupposed; (iv)
    the core (`src/pipeguard/`) still never executes — only the out-of-core drivers shell out,
    unchanged. 9 tests (`tests/test_nextflow_custom_process.py`, pure-offline: verbatim rendering +
    label, catalog-bypass-on-collision, blank-script rejection, uncatalogued-placeholder unchanged,
    a novel output kind wired by name, compose≠execute, germline-drift-green) + 2 more in
    `tests/test_nextflow_api.py` (a custom node compiles over the wire; a blank script 422s).
    **Honest deferral:** the custom script itself runs with **no PipeGuard-side runtime
    sandbox/allowlist** — safety is the approval gate + the honest label + deployment-side
    sandboxing (an ADR-0020 Assumption, not something PipeGuard builds); an operator's declared
    output glob is not yet enforced by the emitted command (`path("*")` captures the whole work
    dir); a custom process is always meta-threaded per-sample, so a non-per-sample (aggregator or
    no-input source) custom process is an unhandled edge case (ADR-0020 §Revisit when). *Trace:*
    [design/nextflow-codegen.md §Operator-authored custom-script processes](../design/nextflow-codegen.md#operator-authored-custom-script-processes-adr-0020-compilerpy--apiroutersnextflowpy),
    [ADR-0020](../adr/ADR-0020-operator-authored-custom-processes.md),
    [design/agent-authoring-contract.md](../design/agent-authoring-contract.md),
    [design/builder-cards/README.md](../design/builder-cards/README.md),
    [journal 2026-07-11 custom-script-io](../journal/2026-07-11-custom-script-io.md).
40. **REQ-F-099 — Sandboxed server-side file browser (`GET /api/files`, 2026-07-11, branch
    `feat/custom-script-io`).** The GB-scale genomics inputs (FASTQ folders, reference FASTAs,
    panel BEDs, VCFs) live on the compute host, not the browser, so the Builder's locator/custom-
    script "Browse…" picker needs a **server-side** listing. `GET /api/files?root=<key>&path=<rel>`
    (`api/routers/files.py`, off-gate, any-authenticated-role — `require_role("viewer",
    "reviewer", "approver")`) lists the directories + files directly under an **allowlisted** root,
    one level at a time, returning **metadata only** (`name`, `is_dir`, `size` for files, an
    extension-inferred `kind` or `null` when unrecognized — never file content). `root` is a
    **key** into a small configured map (`PIPEGUARD_BROWSE_ROOTS`, a `key=abs_path` comma-separated
    override; default `{"data": <repo>/data}`), never a raw filesystem path, so a caller can only
    ever browse a root an operator deliberately exposed. Traversal-hardened (REQ-NF-027) exactly
    like the existing artifact-download idiom. Powers a new `FileBrowser.tsx` component (a
    breadcrumbed, kind-filterable picker) wired into `CustomScriptInspector`'s locator fields via
    `frontend/src/api.ts`'s `browseFiles()` — **additive**: the manual type-a-path input stays, so
    Browse is a convenience, not the only way to set a locator. 10 tests
    (`tests/test_files_api.py`, `TestClient`-driven, pure-offline). *Trace:*
    [ADR-0020](../adr/ADR-0020-operator-authored-custom-processes.md) (the file browser shipped
    alongside the custom-script card as the same Branch B), REQ-NF-027,
    [journal 2026-07-11 custom-script-io](../journal/2026-07-11-custom-script-io.md).
41. **REQ-F-100 — Operator-gated, scheduled sample processing on authored pipelines ([ADR-0021](../adr/ADR-0021-operator-gated-scheduled-pipeline-processing.md),
    2026-07-12).** Closes two gaps in the intake execution path (`POST /api/runs`). **(1) Intake can
    run an authored pipeline.** `SubmitRunIn` gains an optional `pipeline` name (+ optional
    `pipeline_version`); when present, intake resolves + compiles that saved pipeline's
    approver-blessed (`emitted`) snapshot through the **same approval gate** the Builder-Run path
    (`POST /api/pipelines/run`, REQ-F-054/ADR-0014) uses — both routers now share ONE gate + ONE
    compile path via `api/authored_pipeline.py` (`resolve_approved`/`compile_record`/`materialize_bundle`),
    so neither ever runs a raw client-posted graph. A name with no approved version is a **409**;
    absent → the committed `germline-panel` reference as before (byte-preserved, drift-proven). Running
    a non-default authored pipeline needs reviewer/approver (`require_role`). **(2) A processing gate.**
    `SubmitRunIn` gains `mode`: `immediate` (default — fire the driver now, unchanged), `hold` (register
    in a new **`held`** state, do not fire), or `schedule` (store a required `scheduled_at` ISO-8601 +
    register **`scheduled`**, do not fire). `POST /api/runs/{id}/release` (reviewer/approver)
    transitions a `held`/`scheduled` run → `running` and fires the driver from the persisted job
    record (409 if not parked, 404 if unknown). The Submit screen gains a pipeline picker + a
    processing-mode control + a Release action. **Honest deferral:** a **time-based auto-release
    scheduler is deliberately not built** — `scheduled` is `hold` plus a stored timestamp + an honest
    note; no cron/timer/thread wakes it, the operator releases it manually (called out in
    `api/job_store.py`'s `HELD_STATUSES` + the `release_run` docstring). Compose ≠ execute holds — the
    core still never runs a tool; only the out-of-core driver shells out. 15 tests
    (`tests/test_intake_scheduling.py`, offline — the background driver is monkeypatched, so no thread
    runs `nextflow`). *Trace:* [ADR-0021](../adr/ADR-0021-operator-gated-scheduled-pipeline-processing.md),
    `api/routers/intake.py`, `api/authored_pipeline.py`, `api/job_store.py`, REQ-F-054, REQ-F-057.
42. **REQ-F-101 — Agent-observation binding + a scoped, de-identified node-observation read
    (2026-07-12, T-142).** An advisory agent can be *attached* to one Builder graph node as a typed,
    persisted **`AgentBinding { agent, node, grants: ('outputs'|'logs')[] }`** (`frontend/src/types.ts`),
    stored in a `graph.agent_bindings` envelope key **the compiler NEVER dereferences** — the
    Builder's compile/run payload is only `{nodes, edges}` and `api/routers/nextflow.py`'s
    `CompileRequest` is pydantic `extra="ignore"`, so a binding structurally cannot touch the emitted
    Nextflow or a verdict (compile is byte-identical with/without bindings; ADR-0001 + compose ≠
    execute by construction). Default grant `outputs`; `logs` is opt-in. Phase 4 makes the grant
    *readable*: a new read-only **`GET /api/runs/{run_id}/nodes/{node_id}/observations?grants=outputs[,logs]`**
    (`api/routers/node_observations.py`, `require_role` viewer+, off-gate) returns the agent's granted
    view of that node's results for a run — a **narrowing** of what agents already observe, not a
    widening. `grants=outputs` (default) lists the node's PUBLISHED artifacts scoped by matching the
    tool's catalogued output-port globs against the run's Nextflow publish dir (never the whole run);
    `grants=logs` (off by default) returns a **DE-IDENTIFIED** tail of the node's `.command.log`/
    `.command.err` via `api.deid.scrub_text` (subject ids from `sample_metadata.csv` pseudonymized +
    email/6+-digit PII redacted, REQ-NF-028) — NEVER raw stderr. Read-only, post-hoc, traversal-hardened
    like the artifact download, and **honest-empty**: a fixture-only committed run (no scratch dir) or an
    uncatalogued/unresolved node returns an empty view with a `note`, never fabricated outputs; an
    authored-pipeline node absent from the seeded `germline_graph()` degrades to honest-empty (the
    run→authored-graph linkage is not yet tracked). `gather_node_observations()` is the
    **triage-consumption seam**; the agent actually *consuming* the scoped view and a UI display are
    labelled deferred follow-ups (the QC-triage agent stays a pure narrator over rule findings today).
    Taxonomy change: Pipeline-repair + Archivist move OUT of the Builder palette to Agent-triage
    launchers; the Builder keeps QC-triage (node-attachable) + Node-authoring. 8 tests
    (`tests/test_node_observations.py`, offline). *Trace:*
    [ADR-0022](../adr/ADR-0022-agent-observation-binding.md) (the binding is a persisted, read-only
    observation off the compiled graph),
    [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
    [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md) (node-scoped least-privilege),
    REQ-F-045, REQ-F-085, REQ-NF-028, [quality/evaluation.md EVAL-019/EVAL-052](../quality/evaluation.md),
    [tasks T-142](../planning/tasks.md), [journal 2026-07-12](../journal/2026-07-12-builder-agent-hardening.md).
43. **REQ-F-102 — Reserved Builder ports become real Nextflow channels or are removed (no
    superficial ports) (2026-07-12, T-143).** Every port shown on a Builder tool card now maps to a
    REAL emitted Nextflow channel or was deleted — a dangling "reserved" slot that never resolved to a
    published artifact is not shown as if it could be wired. **Promoted** to real published channels
    (with the matching `script:`/`stub:` edit in `catalog.py`, all genuine byproducts of the existing
    command): fastp `unpaired_fastq` (`--unpaired1/2`) + `failed_fastq` (`--failed_out`), bcftools norm
    `vcf_index` (the `.csi` from the existing `bcftools index` step), MultiQC `multiqc_html` (always
    written unless `--no-report`). **Removed** as non-real: bwa `read_group` (a string, not a file),
    mosdepth `per_base` (`--no-per-base` suppresses it), bcftools norm `panel_bed` (norm is
    genome-wide), MultiQC `fastqc_zip`/`bcftools_stats`/`picard_hsmetrics`/`ngscheckmate`. **Left
    honestly-reserved:** fastp `adapter_fasta` (a real optional INPUT; positional promotion into the
    script deferred). Separately, the mosdepth card advertised **five** outputs while the catalog
    declared only two — the arity gap tripped the compiler's output-drift guard and **422'd
    Export-to-Nextflow of the default Builder view**; the three real byproducts of the same
    `mosdepth --by … --thresholds` command (`regions`/`global_dist`/`region_dist`) are now catalogued,
    so a full-5-output node compiles while the seeded `germline_graph()` (trimmed to
    summary+thresholds) stays a valid subset. Reserved ports are also rendered honestly non-armable in
    the Builder (a Connect-mode tooltip; edge-less ports sort clear of the wired band). Germline
    regenerated, byte-for-byte drift guard green; +5 tests (`tests/test_nextflow_promoted_ports.py`) +1
    (the mosdepth 5-output regression in `test_nextflow_compile.py`). Pure text codegen — compose ≠
    execute. *Trace:* [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md),
    [design/nextflow-codegen.md](../design/nextflow-codegen.md), REQ-F-085, REQ-F-090 (the earlier W4
    port-wiring pass this continues), [quality/evaluation.md EVAL-019](../quality/evaluation.md),
    [tasks T-143](../planning/tasks.md), [journal 2026-07-12](../journal/2026-07-12-builder-agent-hardening.md).
44. **REQ-F-103 — Builder inspector Save/Delete footer row (2026-07-12, T-143).** Both the standard
    and custom-script node inspectors now show `[Delete node] [Save]` in a single footer action row
    (`Save card` renamed to `Save`), replacing an in-body Delete + a separate-footer Save. Cosmetic/
    layout only: `onSaveCard`/`onDeleteNode` behavior and the edit-vs-view gating are unchanged (Delete
    stays `userNode`-only). *Trace:* REQ-F-045,
    [tasks T-143](../planning/tasks.md), [journal 2026-07-12](../journal/2026-07-12-builder-agent-hardening.md).

## Notes / deferred

1. **Notify port** is built + verified — **Slack** (T-015b, live-verified) plus **Teams +
   Discord** webhook adapters (T-035, stdlib `urllib.request`, per-adapter live flag,
   stub-default). Only the **Jira** ticket-create adapter and wiring notify into the
   read-API/ticketing flow remain *(wishlist)*.
2. **Variant gate** (REQ-F-013) is Phase 2 and depends on real variant-level data.
3. **IB4 — Inbox per-reminder external notification + cadence** (Slack/Discord/Teams/email,
   REQ-F-077) remains deferred as of Wave 8 (T-113) — the largest remaining Inbox item.
4. **`components/Truncate.tsx`** (a full-text-on-hover primitive, Wave 8/T-115) shipped with no
   call sites; **now applied to one site** (the decision-card headline, Wave 9/T-116, REQ-F-081) —
   a broader sweep of other truncated card strings (run ids, sample names, artifact paths) remains
   open.
5. **Subject/PII persistence** for the new Accession screen (REQ-F-082) is parsed and displayed
   client-side only, not yet persisted server-side — gated on the data-platform PII/de-id design
   (`POST /api/runs` stays `extra="forbid"` on any subject field).
6. **Page-access enforcement is client-side only** (REQ-F-082) — a UI view-gate, not a
   server-side authorization boundary; a production build would need to enforce page/read access
   in `api/`, not just hide nav items in `frontend/`.
7. **Node-authoring agent (REQ-F-025) now has a read-only `api/` endpoint + Builder wiring
   (REQ-F-089, 2026-07-11) — this item is CLOSED for the read path.** `GET /api/builder/node-proposal`
   makes `propose_node()` reachable and the Builder's "Author a tool node" modal now renders the
   real proposal — the "static preview, no transport" framing this note used to carry is stale.
   **Update (2026-07-11, T-135, REQ-F-096): accept→library, a conformance harness, and a structured
   doc-drop importer are now built too, backend-only.** `POST /api/builder/node-proposal/accept` +
   a governed `api/library_store.py` exist; `node_author/importer.py` can onboard a tool NOT in the
   curated corpus **from a `nextflow_schema.json`**. What is **still** true / deferred: the
   Builder's own "Accept to library" **button** is not built (no frontend caller of the accept/
   library endpoints exists, so the modal still never auto-adds a card; "Copy proposal" is the only
   UI action), the `draft→approved` transition is not built, and the free-text `--help`/README half
   of the doc-drop importer is not built — see
   [node-authoring-agent.md](../design/node-authoring-agent.md) "What actually shipped" and
   [agent-authoring-contract.md §Status](../design/agent-authoring-contract.md#status--what-is-wired-vs-deferred-honest).
8. **UIC-16's larger four-side-typed-port Builder cards remain unbuilt** (REQ-F-083i) — only the
   full-canvas dot grid and the current-tools palette expander shipped; ports stay left/right-only
   on the existing fixed-size cards, tracked in [builder-cards/](../design/builder-cards/) §5.
   **Closed the next day** (2026-07-11, T-121) — see [ui-conventions.md UIC-16](../design/ui-conventions.md).
9. **The Nextflow compiler's catalog (REQ-F-085) is curated, not general** — only the 7
   germline-chain tools have a real `script:`; any other tool (incl. a future node-authoring-agent
   proposal) compiles to a labelled, loudly-failing placeholder until a `ProcessSpec` is added for
   it. **Executor config narrowed, not closed (REQ-F-090, 2026-07-11)**: the generated
   `nextflow.config` now also declares `standard` (local single-thread-serial) and `slurm`
   (env-driven queue/cluster-options) profiles alongside `conda`/`docker`/`singularity`/`stub` —
   but the Slurm profile is **CONFIG-verified, not CLUSTER-verified** (no `sbatch` in this
   sandbox, so it has never executed against a real cluster); AWS-Batch/HealthOmics executor
   config remains fully unbuilt. That gap is the still-open half of
   [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md)'s compute-portability decision.
   Container images are named per the nf-core biocontainer convention but only the `conda`
   profile has been live-verified. **Also narrowed (REQ-F-090):** every catalogued process now
   fans out per-sample via the nf-core `[meta, files]` map, but the live intake driver still runs
   one sample (HG002) at a time — the driver's post-run PARSE of a publish dir into N run-dir rows
   is now built and offline-verified (REQ-F-095), but a genuinely live multi-sample Nextflow run
   remains deferred/unverified.

---

*Marker legend:* **Fact** · **Assumption** · **Decision** · **TODO**. In-scope vs
deferred boundaries are authoritative in [scope-and-wishlist.md](scope-and-wishlist.md).
