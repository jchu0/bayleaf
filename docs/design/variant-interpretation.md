# Variant interpretation & reporting — design

| Field | Value |
|---|---|
| **Status** | Proposed (design; **two components now built**, see §0) |
| **Last updated** | 2026-07-10 (MST) |
| **Audience** | software / bioinformatics / reviewers |
| **Related** | [ADR-0018](../adr/ADR-0018-variant-interpretation-advisory-evidence.md) (the decision), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md), [ADR-0004](../adr/ADR-0004-vcf-first-giab-substrate.md), [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md), [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md), [qc_metrics-rare-disease.md](../data/qc_metrics-rare-disease.md), [qc_metrics.md](../data/qc_metrics.md) (§Route-to-human policy), [schemas.md](../data/schemas.md) (`VariantCall`), [architecture.md](architecture.md), [data-platform-and-archivist.md](data-platform-and-archivist.md), [journal/2026-07-10-wave6-route-to-human-deid.md](../journal/2026-07-10-wave6-route-to-human-deid.md) |

## 0. Build status update (2026-07-10, after the maintainer's D1/D2/D3 sign-off)

The maintainer signed off on ADR-0018 and its three open questions (see the ADR's
[Maintainer decisions](../adr/ADR-0018-variant-interpretation-advisory-evidence.md#maintainer-decisions-2026-07-10-sign-off)).
Two pieces of this design are now **BUILT** — everything else below (the interpretation agent,
`RunReport`, the Share window, the ClinVar/gnomAD fetch scripts, gnomAD AF surfacing,
inheritance-fit, review-ordering tier) remains design-only, not built:

1. **Route-to-human (D2) — BUILT.** `models.VariantCall` + `parsers.parse_variant_calls`
   (reads `variants.csv`) + `runbook.RouteToHumanPolicy` + `rules._check_route_to_human`
   (`VAR-RTH-001`) ship as described in §1/§2 below, **off by default** (9 tests,
   `tests/test_route_to_human.py`). This is narrower than the full `AnnotatedVariant`/
   `ClinVarEvidence`/`PriorityTier` model in §1 — only the ClinVar-significance routing slice
   landed, not gnomAD AF, inheritance-fit, or the review-ordering tier.
2. **De-identification default (D3) — PARTIALLY BUILT.** `api/safe_harbor.py`, a conservative
   Safe-Harbor-**style** scrub (direct-identifier drop, date→year, age-90+ cap, mechanical
   free-text redaction of the 18 §164.514(b)(2) classes), ships standalone and unit-tested
   (8 tests, `tests/test_safe_harbor.py`) — but **not yet wired to any egress endpoint**, because
   the report/Share window it is meant to default on (§4 below) is not yet built. `GET
   /api/export` still runs the separate, less-strict `api/deid.py` policy.
3. Sections §1/§3–§6 below describe the **full** design (interpretation agent, `RunReport`,
   Share window, fetch scripts, gnomAD/inheritance evidence) as originally proposed — still
   entirely unbuilt except for the two pieces above.

## Overview

The MVP-first architecture for extending PipeGuard past variant **calling** into an **advisory, cited,
off-gate** rare-disease evidence + review-ordering + reporting surface — the decision and boundary are in
[ADR-0018](../adr/ADR-0018-variant-interpretation-advisory-evidence.md); this doc is the how. Synthesized from a
four-facet design pass (2026-07-10). **Load-bearing rule:** the variant *gate* stays QC (call-quality); this layer
is a separate surface that reads the gate's trustworthy calls and surfaces what the world already says about them,
plus the order a human should review them — it decides nothing (ADR-0001).

## 1. Module map (mirrors the Archivist, ADR-0012)

1. **`src/pipeguard/interpretation/` — deterministic core, framework-agnostic** (like `synthetic/`; never imported
   by `rules.py`/`run_gate`, so it is *structurally* off the gate). Frozen pydantic types following the
   `Evidence`/`MetricValue` conventions in `models.py`:
   - `ClinVarEvidence` — `classification` (verbatim `CLNSIG`), `review_status` (`CLNREVSTAT` → stars), `accession`
     (VCV/RCV), `clinvar_version`/`release_date` **snapshotted onto the record** (self-contained, ADR-0007),
     `citation`.
   - `PopulationFrequency` — `gnomad_af`, `popmax_af`, `popmax_population`, `gnomad_version`, `citation`.
   - `InheritanceFit` — `declared_mode` (operator-provided), `observed_genotypes`, `fit ∈ {consistent, inconsistent,
     incomplete, unknown}`, `rationale` — a **mechanical** genotype-vs-mode check, not a causality claim.
   - `AnnotatedVariant` — joins the above + the variant-gate `call_quality`. **No PipeGuard-authored pathogenicity
     field.**
   - `PriorityTier` enum + a transparent `tier_of(variant, config)` returning the tier **plus its contributing
     evidence** (never a black-box score). Cutoffs (rare-disease AF, which ClinVar tiers count) are **config-driven,
     no hardcoded universals** (ADR-0005 profiles).
2. **`api/interpretation_agent.py` — advisory narration** (clone of `api/archivist.py`): `InterpretationDigest` with
   `advisory: Literal[True] = True` pinned, **no verdict/decision/pathogenicity/confidence field**, fixed
   `disclaimer`, `citations`, `generated_by` `stub`|`claude`; prose `summary` is the **only** LLM-refined field,
   grounded on the deterministic base. Stub-first ($0), lazy `anthropic`, degrade-to-stub on error/refusal.
   `PIPEGUARD_INTERPRETATION_AGENT=stub|claude` (cheap tier default). **Deferred seam** — MVP surfaces the
   deterministic evidence without the agent.
3. **`api/report.py` — the run-report projection** (sibling of `card_readout.py`): assembles an immutable `RunReport`
   from `_evaluate(run_id)` cards + the `card_readout` QC projection + artifact pointers. **Authors no verdict.**
4. **`api/report_store.py` — a fifth pluggable product store** (`PIPEGUARD_REPORT_STORE=jsonl|sqlite|postgres`,
   degrade-to-jsonl) joining feedback/pipeline/settings/review (ADR-0017); distinct from the decision `Repository`,
   never re-enters the gate.
5. **`api/routers/reports.py`** — read: `GET /api/runs/{id}/interpretation`, `GET /api/runs/{id}/report`; off-gate
   lifecycle writes: `POST /api/runs/{id}/report/submit` + `/approve` (`require_role("reviewer","approver")`,
   server-authored `*_by`).
6. **`api/share_target.py` / an `ArtifactSink.publish(bytes, ref)` port** — the downstream inverse of the upstream
   `ArtifactStore.fetch` (`src/pipeguard/artifacts/`); stages/pushes, never runs a tool. `POST /api/share`
   (`require_role("approver")` for external egress) → audited `ShareEvent`.
7. **`scripts/fetch_clinvar.py` + `scripts/fetch_gnomad_panel.py` + manifests** — mirror `fetch_giab_hg002.py`
   (accessions + a fetch script; never commit raw; new git-ignored `real-clinvar`/`real-gnomad` origins).
8. **Frontend** — a Report tab on `RunDetail` (sign-off bar reusing the draft→approve UI + `useConfirm` + `Toast`);
   a per-variant advisory evidence panel; the provenance `variant`/downstream stages become real when an annotated
   VCF is present (P4). A **Share** modal (scope · location · security-level · scrub preview · `ConfirmDialog`).

## 2. Gate & stage model

The downstream steps are **stages under the (unchanged) variant QC gate**, not new gates — so no annotation can move
a verdict (ADR-0001/0013). Any interpretation *issue* that ever fires is a cited, immutable `Finding` routed through
the existing verdict policy (a *route-to-human* ESCALATE), **never an AI-set verdict** — and that route-to-human
rule is now **BUILT** as `VAR-RTH-001` (§0), an **off-by-default, operator-armed config seam** per the maintainer's
2026-07-10 sign-off (ADR-0018 D2 — the earlier "pending sign-off" framing here is resolved). The broader
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
- **Share window** — scope (report / `GET /api/export` / artifacts) · location (local staged dir default; S3 seam
  off unless armed; Box/GCS/signed-link seams) · **security level** (L2 de-identified default → L1 pseudonymized →
  L0 internal/raw, local-only + approver-only) driving the `api/deid.py` policy · **scrub preview** via `redact()`
  · explicit `ConfirmDialog` → `POST /api/share` (`require_role("approver")` for external) → audited `ShareEvent`
  in the Admin Activity feed. **PHI-scrub is a demo seam, explicitly NOT HIPAA de-identification.** Field-class
  contract: drop operator PII; gate cohort keys (`subject_id`/`tissue`) by origin (built, `api/deid.py`); date
  generalization + free-text 18-identifier redaction are **now built standalone** (2026-07-10, `api/safe_harbor.py`,
  ADR-0018 D3, §0) but **not yet wired here** — the Share window itself doesn't exist yet to select it as the L2
  policy; `DateShift` (a *shift*, distinct from `safe_harbor.py`'s coarser year-only *generalization*),
  `sample_id` pseudonymization, and VCF-aware raw stripping remain **labelled seams**. Raw-artifact egress for
  guarded origins is **disallowed by default** (opaque bytes can't be scrubbed).

## 5. Phasing

**MVP slice (compose-only, cited, advisory — buildable over existing seams):**
1. Read an externally-produced **annotated VCF** → `AnnotatedVariant` (tolerant parser; a missing field is a signal).
2. Surface per-variant **cited evidence** (ClinVar verbatim + gnomAD AF + inheritance-fit + call-quality) in the
   variant provenance stage + an advisory panel; register `variant.gnomad_af`.
3. **Review-ordering tier** as labelled heuristic evidence — no classification, no gate movement.
4. `RunReport` projection + the draft→approve sign-off + HTML download.
5. Share window MVP: report/`/api/export` scope; local staged dir; the existing `deid.py` policy; scrub preview;
   confirm → audited `ShareEvent`.
6. Ground plumbing on real GIAB HG002; the flagged-variant demo on a contrived spiked variant.

**Deferred / labelled seams (documented, not built):** the interpretation **agent**;
trio/inheritance-aware context (de novo / comp-het / segregation — needs pedigree); more annotation sources
(SpliceAI/REVEL/MANE/popmax); raw-artifact scrubbing + real external egress (S3 live / Box / GCS / signed link);
PDF; a persisted ledger-anchored signed report; and **any emission of a final ACMG/pathogenicity classification**
(explicitly out of scope — ADR-0018). **Built, 2026-07-10 (§0), no longer deferred:** the route-to-human config
rule (`VAR-RTH-001`) and a conservative Safe-Harbor-style date-generalization + free-text-redaction module
(`api/safe_harbor.py`) — the latter is built but **not yet wired** to any egress endpoint, since the Share window
that would consume it (§4) is itself still unbuilt.

## 6. Open questions

See [ADR-0018 §Open questions](../adr/ADR-0018-variant-interpretation-advisory-evidence.md#open-questions)
— three of the seven were resolved by the maintainer's 2026-07-10 sign-off (report name D1;
route-to-human on the gate D2, **now built**, see §0; de-id conservatism D3, **partially built**,
see §0). The highest-sensitivity one, whether any ClinVar-driven *route-to-human* belongs on the
gate, is **resolved (D2, yes — off by default, RBAC-gated)**, overriding this doc's earlier "off
the gate for MVP" recommendation everywhere else it appears above. The remaining four
(reference-data licensing, transcript/gnomAD-version convention, report grain, egress
destinations + PDF/persist) stay open build-time questions.
