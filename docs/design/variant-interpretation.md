# Variant interpretation & reporting — design

| Field | Value |
|---|---|
| **Status** | Proposed (design; **four components now built end-to-end against a committed run**, see §0) |
| **Last updated** | 2026-07-13 (MST) — naming refresh only: **route-to-human → flag-for-review** (rule id `VAR-RTH-001 → VAR-FFR-001`, `RouteToHumanPolicy → FlagForReviewPolicy`, `_check_route_to_human → _check_flag_for_review`, the `route_to_human` field/marker + `route_to_human.json` stage key → `flag_for_review*`); no design change. Prior: 2026-07-11 (MST) |
| **Audience** | software / bioinformatics / reviewers |
| **Related** | [ADR-0018](../adr/ADR-0018-variant-interpretation-advisory-evidence.md) (the decision + [Realized](../adr/ADR-0018-variant-interpretation-advisory-evidence.md#realized-2026-07-11)), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md), [ADR-0004](../adr/ADR-0004-vcf-first-giab-substrate.md), [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md), [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md) (`data.exported`), [qc_metrics-rare-disease.md](../data/qc_metrics-rare-disease.md), [qc_metrics.md](../data/qc_metrics.md) (§Flag for review policy), [schemas.md](../data/schemas.md) (`VariantCall`, `GET /api/runs/{id}/variants`), [provenance.md](../data/provenance.md), [architecture.md](architecture.md), [data-platform-and-archivist.md](data-platform-and-archivist.md), [journal/2026-07-10-wave6-route-to-human-deid.md](../journal/2026-07-10-wave6-route-to-human-deid.md), [journal/2026-07-11-d2-d3-share-egress.md](../journal/2026-07-11-d2-d3-share-egress.md), [journal/2026-07-11-audit-hardening-w1-w4-e2e.md](../journal/2026-07-11-audit-hardening-w1-w4-e2e.md), [journal/2026-07-11-w-deferrals.md](../journal/2026-07-11-w-deferrals.md) |

## 0. Build status update (2026-07-11, after the maintainer's D1/D2/D3 sign-off)

The maintainer signed off on ADR-0018 and its three open questions (see the ADR's
[Maintainer decisions](../adr/ADR-0018-variant-interpretation-advisory-evidence.md#maintainer-decisions-2026-07-10-sign-off)).
Four pieces of this design are now **BUILT and demonstrated end-to-end against a committed run**
(2026-07-10 landed the rule/module in isolation; 2026-07-11 wired each to a real, runnable path,
and — same day, two further slices, W3 and its continuation — a Report tab and then a per-variant
evidence table shipped over the already-wired data) — everything else below (the interpretation
agent, the full Share window, the ClinVar/gnomAD fetch scripts, gnomAD AF surfacing,
inheritance-fit, the review-ordering tier) remains design-only, not built:

1. **Flag for review (D2) — BUILT, fires end-to-end (2026-07-11).** `models.VariantCall` +
   `parsers.parse_variant_calls` (reads `variants.csv`) + `runbook.FlagForReviewPolicy` +
   `rules._check_flag_for_review` (`VAR-FFR-001`) ship as described in §1/§2 below, **off by
   default** (10 tests, `tests/test_flag_for_review.py`). This is narrower than the full
   `AnnotatedVariant`/`ClinVarEvidence`/`PriorityTier` model in §1 — only the ClinVar-significance
   routing slice landed, not gnomAD AF, inheritance-fit, or the review-ordering tier. **New
   (2026-07-11):** `api/main._active_runbook(run_id)` arms the policy **per run** from an optional
   `flag_for_review` marker file in the run dir; the committed, `origin=contrived` fixture
   `data/RUN-2026-07-11-CLINVAR-RTH/` (a verbatim-cited ClinVar Pathogenic BRCA1 spike HG002 does
   not actually carry) now demonstrates the escalation live through the API — closing the
   "the rule has never fired end-to-end against a committed run" gap the 2026-07-10 sweep left
   open. Every unmarked run stays disarmed; the core default and the pinned demo scenario are
   unchanged.
2. **De-identification default (D3) — the scrub module is now WIRED to a real egress
   (2026-07-11), narrower than the full Share window in §4.** `api/safe_harbor.py`, the
   conservative Safe-Harbor-**style** scrub (direct-identifier drop, date→year, age-90+ cap,
   mechanical free-text redaction of the 18 §164.514(b)(2) classes), ships standalone and
   unit-tested (8 tests, `tests/test_safe_harbor.py`) and is now the default (and only) policy
   behind `POST /api/runs/{id}/share` (`require_role("approver")`; 5 tests,
   `tests/test_share_egress.py`) — an approver-gated egress that scrubs a run's decision rows and
   records a `DATA_EXPORTED` `ProvenanceEvent` (ADR-0002), surfaced live in the Provenance
   screen's Event trail via a "Share (de-identified)" header action
   (`frontend/src/screens/Provenance.tsx`). This is **not** the full Share window §4 describes —
   no scope selector, no location choice, no security-level tier; see §4 below for the precise
   gap. `GET /api/export` still runs the separate, less-strict `api/deid.py` policy (unchanged).
3. **A `RunReport` view — BUILT the same day (W3, commit `3d5a73d`), narrower than §1 item 3's
   `api/report.py` projection.** `RunDetail` gains a `?view=report` **Report** tab
   (`frontend/src/components/RunReport.tsx`): a per-run "QC Decision & Provenance Report" —
   verdict mix, a flag-for-review hero panel quoting ClinVar significance VERBATIM (no authored
   pathogenicity, ADR-0004/G3/G4), per-sample gate outcomes + cited evidence, and a sign-off
   footer stating human sign-off is a labelled seam, not a button. **What makes this "option A,"
   narrower than the design:** it is built entirely over `detail` (cards + events) already on the
   wire — no new `api/report.py` projection, no `ReportStore`, no draft→approve/sign-off write
   path, no persisted/immutable report artifact (a reload re-derives the same report from the
   same already-decided cards rather than reading back a signed snapshot). The same commit also
   fixed a real honesty bug in the Lineage DAG: a fired flag-for-review ESCALATE used to render the
   review node as "skipped" (no VCF artifact) even though the rules had already escalated the
   sample — a fired gate now wins over the no-artifact default. See
   [functional.md REQ-F-087/REQ-F-088](../requirements/functional.md),
   [tasks T-128](../planning/tasks.md).
4. **The per-variant evidence table — BUILT the same day, later (W3 continuation, commit
   `fec0f83`), closing the "no per-variant evidence table" gap item 3 above used to carry.** A
   new read-only `GET /api/runs/{run_id}/variants` (`api/main.py`) serves every `VariantCall` a
   run's `variants.csv` carries, parsed via the SAME `bayleaf.parsers.parse_variant_calls` the
   gate's flag-for-review rule already uses (404 unknown run, `[]` when no `variants.csv` — an
   honest empty state, not fabricated rows). `RunReport.tsx` renders it as a paginated table
   (Sample · Gene · HGVS · ClinVar significance quoted VERBATIM · review status · accession)
   beneath the flag-for-review hero, with its own disclaimer that bayleaf authors no
   pathogenicity and sets no verdict here. **This is still narrower than §1 item 1's full
   `AnnotatedVariant`:** the table surfaces only the `VariantCall` fields already in the D2
   model (ClinVar classification/review-status/accession/version) — there is no gnomAD
   population-frequency column, no inheritance-fit, and no call-quality join; a variant present
   in `variants.csv` but never armed against the flag-for-review policy still shows here (the
   table is unconditional on the rule firing, unlike the hero panel above, which shows only a
   fired flag-for-review hit). Live-verified: the committed `RUN-2026-07-11-CLINVAR-RTH` fixture's
   single BRCA1 `c.68_69del` row renders "Pathogenic" verbatim; `mock_run_01` (no `variants.csv`)
   renders the honest empty state. +3 tests (`tests/test_run_variants.py`). See
   [ADR-0018 Realized item 5](../adr/ADR-0018-variant-interpretation-advisory-evidence.md#realized-2026-07-11),
   [functional.md REQ-F-094](../requirements/functional.md),
   [tasks T-133](../planning/tasks.md),
   [journal/2026-07-11-w-deferrals.md](../journal/2026-07-11-w-deferrals.md).
5. Sections §1/§3–§6 below describe the **full** design (the interpretation agent, the
   `api/report.py`/`ReportStore`/sign-off lifecycle, the Share window, fetch scripts, gnomAD/
   inheritance evidence) as originally proposed — still entirely unbuilt except for the four
   narrower pieces above.

## Overview

The MVP-first architecture for extending bayleaf past variant **calling** into an **advisory, cited,
off-gate** rare-disease evidence + review-ordering + reporting surface — the decision and boundary are in
[ADR-0018](../adr/ADR-0018-variant-interpretation-advisory-evidence.md); this doc is the how. Synthesized from a
four-facet design pass (2026-07-10). **Load-bearing rule:** the variant *gate* stays QC (call-quality); this layer
is a separate surface that reads the gate's trustworthy calls and surfaces what the world already says about them,
plus the order a human should review them — it decides nothing (ADR-0001).

## 1. Module map (mirrors the Archivist, ADR-0012)

1. **`src/bayleaf/interpretation/` — deterministic core, framework-agnostic** (like `synthetic/`; never imported
   by `rules.py`/`run_gate`, so it is *structurally* off the gate). Frozen pydantic types following the
   `Evidence`/`MetricValue` conventions in `models.py`:
   - `ClinVarEvidence` — `classification` (verbatim `CLNSIG`), `review_status` (`CLNREVSTAT` → stars), `accession`
     (VCV/RCV), `clinvar_version`/`release_date` **snapshotted onto the record** (self-contained, ADR-0007),
     `citation`.
   - `PopulationFrequency` — `gnomad_af`, `popmax_af`, `popmax_population`, `gnomad_version`, `citation`.
   - `InheritanceFit` — `declared_mode` (operator-provided), `observed_genotypes`, `fit ∈ {consistent, inconsistent,
     incomplete, unknown}`, `rationale` — a **mechanical** genotype-vs-mode check, not a causality claim.
   - `AnnotatedVariant` — joins the above + the variant-gate `call_quality`. **No bayleaf-authored pathogenicity
     field.**
   - `PriorityTier` enum + a transparent `tier_of(variant, config)` returning the tier **plus its contributing
     evidence** (never a black-box score). Cutoffs (rare-disease AF, which ClinVar tiers count) are **config-driven,
     no hardcoded universals** (ADR-0005 profiles).
2. **`api/interpretation_agent.py` — advisory narration** (clone of `api/archivist.py`): `InterpretationDigest` with
   `advisory: Literal[True] = True` pinned, **no verdict/decision/pathogenicity/confidence field**, fixed
   `disclaimer`, `citations`, `generated_by` `stub`|`claude`; prose `summary` is the **only** LLM-refined field,
   grounded on the deterministic base. Stub-first ($0), lazy `anthropic`, degrade-to-stub on error/refusal.
   `BAYLEAF_INTERPRETATION_AGENT=stub|claude` (cheap tier default). **Deferred seam** — MVP surfaces the
   deterministic evidence without the agent.
3. **`api/report.py` — the run-report projection** (sibling of `card_readout.py`): assembles an immutable `RunReport`
   from `_evaluate(run_id)` cards + the `card_readout` QC projection + artifact pointers. **Authors no verdict.**
4. **`api/report_store.py` — a fifth pluggable product store** (`BAYLEAF_REPORT_STORE=jsonl|sqlite|postgres`,
   degrade-to-jsonl) joining feedback/pipeline/settings/review (ADR-0017); distinct from the decision `Repository`,
   never re-enters the gate.
5. **`api/routers/reports.py`** — read: `GET /api/runs/{id}/interpretation`, `GET /api/runs/{id}/report`; off-gate
   lifecycle writes: `POST /api/runs/{id}/report/submit` + `/approve` (`require_role("reviewer","approver")`,
   server-authored `*_by`).
6. **`api/share_target.py` / an `ArtifactSink.publish(bytes, ref)` port** — the downstream inverse of the upstream
   `ArtifactStore.fetch` (`src/bayleaf/artifacts/`); stages/pushes, never runs a tool. `POST /api/share`
   (`require_role("approver")` for external egress) → audited `ShareEvent`.
7. **`scripts/fetch_clinvar.py` + `scripts/fetch_gnomad_panel.py` + manifests** — mirror `fetch_giab_hg002.py`
   (accessions + a fetch script; never commit raw; new git-ignored `real-clinvar`/`real-gnomad` origins).
8. **Frontend** — a Report tab on `RunDetail` (sign-off bar reusing the draft→approve UI + `useConfirm` + `Toast`);
   a per-variant advisory evidence panel; the provenance `variant`/downstream stages become real when an annotated
   VCF is present (P4). A **Share** modal (scope · location · security-level · scrub preview · `ConfirmDialog`).

## 2. Gate & stage model

The downstream steps are **stages under the (unchanged) variant QC gate**, not new gates — so no annotation can move
a verdict (ADR-0001/0013). Any interpretation *issue* that ever fires is a cited, immutable `Finding` routed through
the existing verdict policy (a *flag-for-review* ESCALATE), **never an AI-set verdict** — and that flag-for-review
rule is now **BUILT** as `VAR-FFR-001` (§0), an **off-by-default, operator-armed config seam** per the maintainer's
2026-07-10 sign-off (ADR-0018 D2 — the earlier "pending sign-off" framing here is resolved), and as of 2026-07-11
**fires end-to-end** against the committed `data/RUN-2026-07-11-CLINVAR-RTH/` fixture via the per-run
`api.main._active_runbook` arming seam (§0). The broader
per-variant evidence surfacing (`rules._check_variant_annotation` / `AnnotatedVariant` §1) that would be
**surface-only** for the MVP — attaching cited evidence without gating — is **still unbuilt**. The `PipelineStage`
enum + the provenance DAG `STAGES` gaining filter/annotate/interpret/report entries shown honestly as "not run in
this build" until an annotated VCF is present (P4) is also **still unbuilt**.

## 3. Data & grounding

- **Truth sources:** GIAB **HG002** (real substrate, benchmark not patient); **ClinVar** + **gnomAD** as *displayed
  annotation only, never a runtime gate input*; a genotype truth VCF is a *genotype* set, not a pathogenicity
  annotation. Ground plumbing/faithfulness on real HG002; ground the flagged-variant demo on a **contrived spiked
  variant** (`origin=contrived`), never implying a patient.
- **Citations preserved end-to-end:** every record snapshots its DB version + accession; the report/exports carry the
  reproducibility pins already emitted (`rule_pack_version`, `metric_registry_version`, `origin`, `generated_by`,
  timestamp). GRCh38 throughout (no liftover).
- **New registry keys:** `variant.gnomad_af` + an annotation-source registry (the same units/drift shield the metric
  registry gives QC metrics).

## 4. Reporting & sharing (P2)

- **`RunReport`** sections: provenance header + version pins; decision summary (verdict + three-gate rollup,
  confidence omitted); findings + verbatim evidence (the cited core); QC readout with the illustrative-not-clinical
  disclaimer; variant section as an honest empty state until built; **separated** generated-narration block; a
  sign-off block (`draft|pending_review|approved` + `*_by` + `content_hash`). **DRAFT until an approver signs.**
  Download = self-contained HTML (stdlib); PDF is a seam (new dependency).
- **Share window (still design-only — a NARROWER single action shipped instead, 2026-07-11, §0)** — the
  full design remains: scope (report / `GET /api/export` / artifacts) · location (local staged dir
  default; S3 seam off unless armed; Box/GCS/signed-link seams) · **security level** (L2
  de-identified default → L1 pseudonymized → L0 internal/raw, local-only + approver-only) driving
  the `api/deid.py` policy · **scrub preview** via `redact()` · explicit `ConfirmDialog` → `POST
  /api/share` (`require_role("approver")` for external) → audited `ShareEvent` in the Admin
  Activity feed. **What actually shipped instead (2026-07-11):** `POST /api/runs/{id}/share` — one
  fixed action, no scope/location/security-level selection, always the `grain="decision"` rows,
  always the Safe-Harbor-style scrub (no L0/L1/L2 opt-down), the bundle returned directly to the
  caller (nothing staged to a location), and the audited event lands in the run's own Provenance ›
  Event trail (`data.exported`, ADR-0002) — **not** in the Admin Activity feed (`Admin.tsx`'s
  `FeedKind` has no `share` case yet). It is approver-gated + `ConfirmDialog`-gated in the frontend,
  matching the RBAC/confirm intent above, just over a narrower action surface. **PHI-scrub is a
  demo seam, explicitly NOT HIPAA de-identification.** Field-class contract: drop operator PII;
  gate cohort keys (`subject_id`/`tissue`) by origin (built, `api/deid.py`); date generalization +
  free-text 18-identifier redaction are **built and now wired** (2026-07-10 build, 2026-07-11
  wiring, `api/safe_harbor.py`, ADR-0018 D3, §0) to this one narrower action, not to the full L2
  tier of a Share window that doesn't exist yet; `DateShift` (a *shift*, distinct from
  `safe_harbor.py`'s coarser year-only *generalization*), `sample_id` pseudonymization, and
  VCF-aware raw stripping remain **labelled seams**. Raw-artifact egress for guarded origins is
  **disallowed by default** (opaque bytes can't be scrubbed) — moot today since the shipped action
  never touches raw artifacts at all (decision rows only).

## 5. Phasing

**MVP slice (compose-only, cited, advisory — buildable over existing seams):**
1. Read an externally-produced **annotated VCF** → `AnnotatedVariant` (tolerant parser; a missing field is a signal).
2. Surface per-variant **cited evidence** (ClinVar verbatim + gnomAD AF + inheritance-fit + call-quality) in the
   variant provenance stage + an advisory panel; register `variant.gnomad_af`. **A ClinVar-only slice of this —
   the `VariantCall` fields with no gnomAD/inheritance-fit/call-quality join — shipped 2026-07-11 as the
   RunReport's per-variant table (§0 item 4);** the fuller joined evidence panel stays deferred.
3. **Review-ordering tier** as labelled heuristic evidence — no classification, no gate movement.
4. `RunReport` projection + the draft→approve sign-off + HTML download.
5. Share window MVP: report/`/api/export` scope; local staged dir; the existing `deid.py` policy; scrub preview;
   confirm → audited `ShareEvent`.
6. Ground plumbing on real GIAB HG002; the flagged-variant demo on a contrived spiked variant — **done for
   flag-for-review** (2026-07-11): `data/RUN-2026-07-11-CLINVAR-RTH/` is exactly this — a real HG002 run with a
   contrived, clearly-labelled ClinVar spike, committed and test-pinned.

**Deferred / labelled seams (documented, not built):** the interpretation **agent**;
trio/inheritance-aware context (de novo / comp-het / segregation — needs pedigree); more annotation sources
(SpliceAI/REVEL/MANE/popmax); raw-artifact scrubbing + real external egress (S3 live / Box / GCS / signed link);
PDF; a persisted ledger-anchored signed report; the full Share window's scope/location/security-level selection
and its Admin-Activity-feed audit row; and **any emission of a final ACMG/pathogenicity classification**
(explicitly out of scope — ADR-0018). **Built, 2026-07-10 (§0), no longer deferred:** the flag-for-review config
rule (`VAR-FFR-001`) and a conservative Safe-Harbor-style date-generalization + free-text-redaction module
(`api/safe_harbor.py`). **Built end-to-end, 2026-07-11 (§0), no longer deferred:** flag-for-review now fires
against a committed run (`data/RUN-2026-07-11-CLINVAR-RTH/` + the `_active_runbook` per-run arming seam), and
`api/safe_harbor.py` is now wired — narrower than the full Share window above — to a single approver-gated
`POST /api/runs/{id}/share` action, recorded as a `data.exported` provenance event and surfaced in the
Provenance screen.

## 6. Open questions

See [ADR-0018 §Open questions](../adr/ADR-0018-variant-interpretation-advisory-evidence.md#open-questions)
— three of the seven were resolved by the maintainer's 2026-07-10 sign-off (report name D1;
flag-for-review on the gate D2, **now built and firing end-to-end**, see §0; de-id conservatism D3,
**the scrub module is built and now wired to a narrower egress than the full design**, see §0). The
highest-sensitivity one, whether any ClinVar-driven *flag-for-review* belongs on the gate, is
**resolved (D2, yes — off by default, RBAC-gated)**, overriding this doc's earlier "off the gate
for MVP" recommendation everywhere else it appears above. The remaining four (reference-data
licensing, transcript/gnomAD-version convention, report grain, egress destinations + PDF/persist)
stay open build-time questions — **egress destinations** narrows further now that one concrete
destination (an approver-gated JSON response, no location/staging) is real, but the fuller
scope/location/security-level Share window is still to design against real requirements.
