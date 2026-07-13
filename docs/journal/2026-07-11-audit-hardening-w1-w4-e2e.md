# Journal — 2026-07-11 (MST) — Release-hardening audit → P0/P1 hardening → W1–W4 → E2E acceptance test

> **Naming note (2026-07-13, MST):** this dated entry predates the rename **route-to-human → flag-for-review** (`VAR-RTH-001 → VAR-FFR-001`, `RouteToHumanPolicy → FlagForReviewPolicy`, `_check_route_to_human → _check_flag_for_review`, the `route_to_human` field/marker + `route_to_human.json` stage key → `flag_for_review*`, `tests/test_route_to_human.py → tests/test_flag_for_review.py`). The old names below are kept as accurate-at-the-time; current-state docs use the new names. See [2026-07-13-flag-for-review-rename-and-page-naming.md](2026-07-13-flag-for-review-rename-and-page-naming.md).

| Field | Value |
|---|---|
| **Focus** | Run a structured release-hardening audit against the shipped app, fix what it found (P0 + 6 P1s + a real approval-gate bypass), then build four wishlist-track increments the audit's feasibility panels grounded (W1 approval-gated execution, W2 node-author read path, W3 Report tab + honest downstream provenance, W4 executor profiles + fan-out + full port wiring), and close the loop with an offline end-to-end acceptance test. |
| **Participants** | maintainer (James Hu), Claude Code (a Fable-5 multi-agent audit run, then four sequential/parallel build passes) |
| **Outcome** | Audit: 84 findings → 26 deduped, 0 refuted; the one P0 + 6 P1s fixed same day. W1: the Builder's second execution path is now approval-gated, closing a real bypass. W2: the node-authoring agent gets its first read path + a governing contract doc. W3: a Report tab ships + a real lineage honesty bug is fixed. W4: an executor-profile layer (config-verified, not cluster-verified) + per-sample fan-out + full QC port wiring. E2E: one offline test threads the whole arc; **465 passed / 6 skipped** (was 427/29 collected → now 471/33), ruff+mypy+tsc+oxlint clean. |

## Discussion

### Why an audit, and why now

The repo had accumulated ~120 tasks of dense, fast-moving frontend/backend work (see `CLAUDE.md`'s
code map) with no independent adversarial pass checking whether the *demo-facing* surface still
told the truth about itself. The maintainer's standing "release-hardening audit" plan
(`audit/AUDIT_PLAN.md`, referenced in the project memory) called for a Fable-5 multi-agent run: 10
read-only specialists each auditing a different lens (UI/UX, data-lineage, user journeys,
integration, reliability, agent-safety, science-reproducibility, demo-readiness, API contract,
truthfulness), plus a second track running grounded 3-approach design panels on four wishlist
items to check they were actually buildable before committing to them.

**Discipline was the load-bearing design choice**, not just running the agents. Ten independent
specialists surfacing findings against the same 14-screen, ~30-router app inevitably produces
massive overlap ("Gate online" was independently flagged by 3 specialists; the node-author no-op
CTA by 5) — so the synthesis pass's job was consolidation (60 raw → 26 deduped) AND **adversarial
re-verification**: every Blocker/High finding got independently reproduced against the live app or
the cited `file:line` before being trusted, with an explicit three-way taxonomy (CONFIRMED /
UNVERIFIED / REFUTED) rather than silently accepting a specialist's confidence. Nothing was
REFUTED — a clean bill for the specialists' rigor — but that's a fact worth recording rather than
assuming; a synthesis that skipped re-verification would have had no way to know.

The other deliberate discipline: **Track A (release-hardening) was scoped to relabel/reword/wire
the minimum, never add new scope.** Several findings (P1-6, the second execution path with no
approval check) were real *bugs*, not just presentation gaps, and got fixed as bugs. Several others
(the node-author "add to palette" no-op, the Archivist "Queue archive" inert button) were
*honestly-labelled* `phase-2` seams whose only real defect was an over-confident CTA label — those
got relabeled, not built out, because building them would have been scope creep riding on an audit
finding rather than an actual audit recommendation. This is the same "scope guardrail" the
maintainer has stated before (see the project memory) — the audit made it operational rather than
abstract: P2/P3 items were explicitly deferred and named, not quietly built because an agent had
momentum.

### P0 + P1 hardening (commit `94c19da`)

The single P0 — `RunOverview`'s "Gate online" dot was a hardcoded `bg-proceed` green span with a
comment literally calling it "live," while the REAL health poll (`useApiHealth`, already built for
`TopBar`) sat 100 lines away in the same file, unused for this purpose. This is the canonical
"honesty drift" bug class the project's guardrails exist to catch: a UI element visually claiming
a live status it never actually checked. Fixed by wiring the existing hook — zero new surface
area, the fix was purely "use the thing that already exists."

The six P1s were a mix of doc-narration drift (the run-of-show pointed at a UI label
`ADVISORY · STUB` that was never actually rendered — the shipped code says `Advisory` +
`Rule-derived triage (offline)`), a copy-honesty fix (Intake's override note claimed something was
"recorded on the run" when it was `useState`, gone on reload), a fabrication guard (Submit showed
"Samples · 4" from seed data before any real upload, indistinguishable from a real parse), a real
scientific-display bug (`rules.py` rendered fraction QC metrics as raw decimals scaled by the wrong
factor — `0.85%` instead of `85%` — latent on the shipped fixtures but would be wrong the moment a
live run tripped a fraction threshold), a resilience gap (two client pollers spun "running" forever
on a 404/network blip with no terminal error state), and a doc-drift note (this file's own router
map hadn't caught up with `pipeline_run.py`).

**The most consequential P1 (P1-6) turned out to be load-bearing enough to become its own W1
increment, not just a relabel.** `POST /api/pipelines/run` — the Pipeline Builder's "Run" action —
compiled and executed the operator's **live canvas graph** with role-based auth
(`require_role("reviewer", "approver")`) but **no lifecycle/approval check at all**. This meant an
unapproved, unreviewed draft could execute for real against real Nextflow. The audit's own
disciplined framing (P1-6, "doc reconciliation is zero-risk; wiring an approval gate could break
the demo Run beat — do NOT do that pre-submission") deliberately deferred the actual fix to avoid
destabilizing the working golden path under audit pressure — this session picked it back up as W1
once there was room to build and test it properly.

### W1 — closing the approval-gate bypass (commit `94c19da`, same commit as the P0/P1 hardening)

The fix threads the existing draft→approve lifecycle (ADR-0017) through to execution rather than
inventing a new one. `RunPipelineIn`'s body now NAMES a saved pipeline (`name` + optional
`version`) instead of carrying a raw graph; `_resolve_approved()` looks up that pipeline's
approver-blessed (`emitted`) snapshot from `PipelineGraphStore` via `last_emitted()` — the exact
same function the pipeline-lifecycle router already used for diffing. A name with no approved
version is a 409, matching the existing status vocabulary (`draft`/`pending_review`/`approved`)
rather than adding new states. The old client-graph parameter is gone entirely — `extra="forbid"`
means a smuggled `graph` field 422s before any compilation happens, closing the bypass
structurally, not just by omission.

This is a good example of "the fix scope should match the finding's scope": the audit found an
*authz*/*lifecycle* gap, and the fix is exactly that gap, nothing broader — no new role, no new
store, no new UI beyond disabling the Run button pre-approval and a `409`-aware toast. The demo-gap
this created (a fresh pipeline store now has nothing pre-approved to run) got its own small,
deliberate fix: `scripts/seed_approved_germline.py`, a committed (not gitignored) idempotent script
driving the SAME lifecycle functions the API uses, so `germline-panel` is runnable by name out of
the box. Idempotency mattered here — a demo script that minted a new pipeline version every time
it ran would pollute the store and make "the approved baseline" ambiguous.

### W2 — the node-authoring agent gets a read path (commit `9616cab`)

The node-authoring agent (roster #5, T-046) had been core-only since 2026-07-10 — built, tested,
19 passing tests, but `grep -rn node_author api/` returned nothing. This session's job was making
it reachable, plus writing down the general contract for how ANY authoring agent — this one, or a
future 7th/8th roster member — is allowed to behave, since "an agent that proposes structured
metadata a human reviews" is a pattern the repo is clearly going to reuse.

The contract doc (`docs/design/agent-authoring-contract.md`) is deliberately "honest transcription"
— every rule in it cites a real `file:line`, so it can't drift into aspiration the way a
pre-written spec sometimes does. Its one load-bearing invariant, stated plainly: an authoring agent
emits **metadata, never a runnable command**. The `NodeProposal`/`PortSpec`/`ToolCardEntry` shapes
it fills have no field that could hold a `script:`/`stub:` body — that's not a convention the agent
happens to follow, it's structurally impossible for it to violate, because the Nextflow catalog's
`ProcessSpec.script`/`ProcessSpec.stub` live in a completely separate, human-curated module
(`bayleaf.nextflow.catalog`) the agent never touches. This is the same "compose ≠ execute" trust
seam ADR-0003 already established, restated at the agent-authoring layer: if it ever softened,
agent-authored metadata would become a route to arbitrary command execution.

The endpoint itself (`GET /api/builder/node-proposal`) is deliberately the simplest possible
shape — read-only, no RBAC write, mirroring the existing `GET
/api/monitoring/signatures/{sig}/repair` read pattern rather than inventing a new one. The
Builder's `AuthorToolNodeModal` swapped its static `STAR --help` mock for the real proposal
render, but the accept action stays "Copy proposal" (a harmless clipboard action) rather than any
kind of auto-add — accept→draft-library-entry is explicitly named as the next slice, not built
here, because building it would mean designing the confirm/audit/RBAC shape for mutating the
Builder's card palette, a meaningfully bigger decision than "expose a read."

### W3 — a Report tab, and a real honesty bug fix (commit `3d5a73d`)

The Report tab was scoped as "option A" from the start — build a per-run summary document
entirely over data already on the wire (`RunDetail`'s existing `cards` + `events`), rather than
standing up the full `api/report.py` projection + `ReportStore` + sign-off lifecycle the original
variant-interpretation design describes. This is a real, deliberate narrowing, not a shortcut
hidden as a full implementation: a page reload re-derives the same report from the same
already-decided cards, there's no persisted/signed artifact, and the sign-off footer states in
plain language that human sign-off is a labelled seam, not a button — bayleaf cannot mark a
report final on its own. `test_api.py` gained `test_downstream_artifact_stage_seams` pinning the
new filename→stage mapping; the route-to-human hero panel's ClinVar quote is separately asserted
verbatim by the E2E test below (`test_report_route_to_human_quotes_clinvar_verbatim`), not just
visually inspected.

The more interesting outcome of this pass was discovering and fixing a genuine lineage-honesty
bug while extending `PipelineStage` with `filter`/`review`/`share`. The Lineage DAG's honesty rule
had been "a stage with no artifact reads 'not run in this build'" — correct for a stage that
genuinely didn't run, but wrong for the route-to-human REVIEW stage on the `CLINVAR-RTH` fixture:
that fixture carries `variants.csv`, not a `.vcf`, so the review stage had zero artifacts even
though `VAR-RTH-001` had already fired and escalated the sample. The old rule would have rendered
the review node "skipped" on a run whose card literally says ESCALATE — a DAG lying about a
decision the rules already made, which is exactly the class of bug the honesty guardrails exist to
catch. The fix is a genuine reordering of the check, not a special case: a fired gate now wins
over the no-artifact default (`isNotRun()` checks `gateFired` before falling back to "no
artifacts"), so the review node reads whatever the gate actually decided. This generalizes
correctly — any future stage with a gate-but-no-artifact story gets the same honest treatment, not
just this one fixture.

### W4 — executor profiles, per-sample fan-out, full port wiring (commit `5f0d5ec`)

This was the largest single-commit change of the day, and the one most in need of precise, hedged
language in the docs. Three genuinely separate capabilities landed together because they're
mechanically coupled (per-sample fan-out changes the channel shape every process consumes, which
the executor-profile config sits downstream of):

1. **Executor profiles.** `standard` (local single-thread-serial — the conservative default) and
   `slurm` (env-driven queue/cluster-options/queue-size, one sbatch job per process). The driver
   auto-detects `sbatch` on `PATH` to choose. **The honest framing that mattered most here**: this
   sandbox has no `sbatch`, so only `standard` has ever actually executed. The `slurm` profile's
   Nextflow syntax has been read and reasoned through carefully, but "config-verified" and
   "cluster-verified" are genuinely different claims, and conflating them would be exactly the kind
   of overclaim the project's guardrails exist to prevent. Every doc this session touched that
   mentions the Slurm profile says "config-verified, not cluster-verified" in those or equivalent
   words, deliberately repeated rather than stated once and assumed remembered.
2. **Per-sample fan-out.** Every catalogued process now threads the nf-core `[meta, files]`
   convention and would run once per samplesheet row given a multi-row sheet; `MultiQC` is the one
   deliberate exception (a cross-sample aggregator, `per_sample=False`). HG002 stays a fan-out of
   one in practice — the compiler/pipeline-generation layer is ready for multiple samples, but the
   live driver has not been exercised with more than one.
3. **Full QC port wiring.** `fastp_html` and `samtools_stats` — both real commands the driver
   already ran — were previously modeled as "reserved" (documented but unwired) ports; they're now
   real, published, wireable outputs, and MultiQC ingests them plus the mosdepth byproducts (5
   streams total, was 3). This closes real gaps in two separate docs
   (`design/ui-conventions.md`, `design/builder-cards/README.md`) that had explicitly named
   `fastp_html`/`samtools_stats` as the examples of "still-unregistered reserved kinds" — both
   became stale the moment this commit landed, and both got fixed in this sweep (not left for a
   future session to notice the drift).

### E2E acceptance test (commit `2e9b4e5`)

The four increments above (W1, W2 narrower — no endpoint test needed since it's a thin read
wrapper — W3, W4) each had their own unit-level tests, but nothing threaded the actual demo
narrative end to end: sheet → intake → the approval gate → a report. `test_e2e_pipeline.py` closes
that gap deliberately offline and deterministic — the intake driver and the Builder-run background
executor are monkeypatched to no-ops, so the test asserts *wiring* (the compiled step order, the
409→submit→approve→202 transition, the honest processed/skipped split) rather than depending on a
real Nextflow install to pass in CI. One env-gated case (mirroring the existing Postgres-live and
Nextflow-live patterns) confirms the same approved graph is a genuinely valid Nextflow pipeline via
`-stub-run` when `nextflow` happens to be on `PATH` locally — skipping, never failing, in its
absence.

The seed script (`scripts/seed_approved_germline.py`) turned out to be dual-purpose: written first
as the W1 demo-gap fix, it's reused verbatim by the E2E test's approval-gate case, so "what the demo
seeds" and "what the test approves" are provably the same graph by construction — the same pattern
the reference-pipeline drift test already uses for "what the Builder emits" vs. "what's committed."

### Verification

`uv run pytest -q` → **465 passed, 6 skipped** in this sandbox (no `nextflow` on `PATH`);
`uv run pytest --collect-only -q` → **471 collected**; `git ls-files 'tests/*.py' | wc -l` → **33**.
Recomputed per-file test counts via `pytest --collect-only -q | grep '::' | sed 's/::.*//' | sort |
uniq -c` to ground the `evaluation.md` census table exactly, rather than trusting the commit
messages' self-reported numbers. ruff+mypy clean (per the commit messages; re-verified pytest
directly in this session). No verdict, gate, or confidence field was touched by any of this —
confirmed by reading `src/bayleaf/rules.py`'s diff (the P1-4 fix changes only a display-string
computation, not the underlying `MetricValue`/threshold comparison) and by the E2E test's own
assertion that `confidence` stays `None` on every card.

## Decisions

| Decision | Distilled to |
|---|---|
| The Builder's `POST /api/pipelines/run` must execute only an approver-blessed pipeline snapshot, never a raw posted graph — the draft→approve lifecycle (ADR-0017) now gates a real execution, not just config authoring. | [ADR-0017 Realized addendum (2026-07-11, W1)](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md#realized-addendum-2026-07-11-w1--the-draftapprove-lifecycle-now-gates-a-real-execution-not-just-config) |
| A non-local Nextflow executor profile (Slurm) is now declared and auto-selected, but must be labelled config-verified, not cluster-verified, until it actually runs against a real cluster — this narrows, but does not close, ADR-0003's compute-portability gap. | [ADR-0003 Realized (2026-07-11, W4)](../adr/ADR-0003-deployment-agnostic-ports.md#realized-2026-07-11-w4--an-executor-profile-layer-local-serial--slurm-config-verified-not-cluster-verified) |
| An authoring agent's contract is "metadata only, never a runnable command" — codified as a standing, citable document rather than left as an implicit convention, since the roster is expected to grow a 7th/8th agent. | [docs/design/agent-authoring-contract.md](../design/agent-authoring-contract.md) |
| A fired gate must win over "no artifact" when rendering a downstream provenance stage's status — the general honesty rule the CLINVAR-RTH fixture's review-node bug exposed. | [design/variant-interpretation.md §0 item 3](../design/variant-interpretation.md#0-build-status-update-2026-07-10-after-the-maintainers-d1d2d3-sign-off), realized in `frontend/src/components/provenance/Lineage.tsx` |

## Open questions & TODO

- Accept→draft-library-entry for the node-authoring agent (W2's deliberately deferred write path).
- A governed library store for authored node proposals, if/when the roster outgrows the flat
  11-card corpus.
- A per-agent conformance harness (`AgentManifest` + a parametrized test) making
  `agent-authoring-contract.md`'s invariants mechanically self-enforcing across the whole roster,
  not just this one agent.
- A true multi-sample driver run (N-row samplesheet → N parsed result dirs → N gate-able run
  dirs) — the compiler/pipeline generation is fan-out-ready (W4); the live driver has only ever
  been exercised with one sample.
- Cluster-verifying the `slurm` executor profile against a real Slurm allocation (currently
  config-verified only).
- P2/P3 audit findings (`audit/SYNTHESIS.md`) — the **12 P2s** (truthfulness relabels + egress
  hardening) were addressed in a follow-on batch (commit `5afaed9`, three parallel Fable-5 agents
  on disjoint files, each re-verifying currency vs post-W1-W4 code): Archivist/repair CTA + badge
  honesty, Submit Save-draft + BaseSpace-mock labels, SettingsModelTier persistence + metrics-agent
  Live-guard, Admin share-audit note, MonitoringSignature `types.ts` drift, safe_harbor AS-01/02/04
  egress fixes (+2 tests), the empty-graph run guard, and the real-GIAB `NOTE.md`. P2-1 was already
  resolved by W2; the audit's P2-7 env-var claim was itself stale (no change). The **14 P3s** remain
  open post-hackathon backlog by design, not silently dropped.
- Median-review-time KPI, a BaseSpace connector, and IB4 (Inbox external-notification cadence)
  remain the long-standing deferred items unrelated to this session's scope.

## Distilled into

- `CLAUDE.md` (Current code map — new session paragraph + the corrected `pipeline_run.py`
  approval-gate description)
- `docs/planning/tasks.md` (T-125–T-130)
- `docs/requirements/functional.md` (REQ-F-086–REQ-F-090 + Notes items 7/8/9 corrected)
- `docs/requirements/nonfunctional.md` (REQ-NF-060 addendum)
- `docs/design/nextflow-codegen.md` (executor profiles + per-sample fan-out + full port wiring
  sections, census refresh, Limitations narrowed)
- `docs/design/variant-interpretation.md` (§0 item 3 — RunReport now built)
- `docs/design/agents.md` (roster #5 row — endpoint wired)
- `docs/design/node-authoring-agent.md` (status header + item 5 corrected)
- `docs/design/ui-conventions.md` (UIC-16 fastp_html/samtools_stats correction, two places)
- `docs/design/builder-cards/README.md` (§5 item 4 narrowed)
- `docs/adr/ADR-0003-deployment-agnostic-ports.md` (Realized addendum, W4 executor profiles)
- `docs/adr/ADR-0017-identity-rbac-authoring-lifecycle.md` (Realized addendum, W1 approval gate)
- `docs/adr/ADR-0018-variant-interpretation-advisory-evidence.md` (Realized item — RunReport)
- `docs/quality/evaluation.md` (EVAL-007, EVAL-060, census refreshed, item 4 of "what we do not
  claim" corrected)
- `docs/TABLE_OF_CONTENTS.md` (registers `audit/` + `agent-authoring-contract.md`, a new
  Doc-update map row for audit runs)
