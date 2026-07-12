# ADR-0018 — Variant interpretation as advisory cited evidence, not a clinical decision engine

| Field | Value |
|---|---|
| **Status** | Accepted (maintainer sign-off 2026-07-10 MST; three open questions decided — see [Maintainer decisions](#maintainer-decisions-2026-07-10-sign-off)); D2 + D3 built end-to-end against a committed run, plus a narrower `RunReport` view and its per-variant evidence table — see [Realized (current status)](#realized-current-status) |
| **Date** | 2026-07-10 (MST) · updated 2026-07-11 (MST) |
| **Deciders** | maintainer (signed off 2026-07-10), design pass (4 parallel memos, 2026-07-10) |
| **Related** | [ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md) (rules decide / AI advises), [ADR-0013](ADR-0013-gate-architecture-verdict-policy.md) (three-gate model), [ADR-0004](ADR-0004-vcf-first-giab-substrate.md) (GIAB benchmark / no invented pathogenicity), [ADR-0003](ADR-0003-deployment-agnostic-ports.md) (compose ≠ execute), [ADR-0017](ADR-0017-identity-rbac-authoring-lifecycle.md) (RBAC + draft→approve), [ADR-0012](ADR-0012-agent-scoping-model-tiering.md) (advisory agent scoping), [ADR-0007](ADR-0007-ml-ready-structured-outputs.md) (self-contained records), [ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md) (`data.exported` event), [ADR-0016](ADR-0016-postgres-port.md) (pluggable-store family the share sink now matches), [qc_metrics-rare-disease.md](../data/qc_metrics-rare-disease.md), [data/provenance.md](../data/provenance.md), [design/variant-interpretation.md](../design/variant-interpretation.md), [HISTORY.md § ADR-0018](../HISTORY.md#adr-0018--variant-interpretation-what-landed-against-a-committed-run) (dated build chronology), [journal 2026-07-11 d2-d3](../journal/2026-07-11-d2-d3-share-egress.md), [journal 2026-07-11 share-store persistence](../journal/2026-07-11-share-store-persistence.md), [journal 2026-07-11 audit+W1-W4+E2E](../journal/2026-07-11-audit-hardening-w1-w4-e2e.md), [journal 2026-07-11 w-deferrals](../journal/2026-07-11-w-deferrals.md) |

## Context

The maintainer asked to extend bayleaf past variant **calling** into the rare-disease downstream chain —
**variant filtering/prioritization → annotation → interpretation → reporting** — and chose the fullest option
("full interpretation + report"). That ambition collides head-on with the repo's **life-science guardrails**
(CLAUDE.md): bayleaf is a *research/demo QC decision gate with production intent* and must make **no diagnostic,
therapeutic, or safety claims**; confidence is a heuristic, never calibrated; clinical variant claims stay grounded
in ClinVar/GIAB truth and **never invent pathogenicity** (ADR-0004). A naive "interpretation engine" that emits a
Pathogenic/Likely-Pathogenic call would cross directly into being a clinical decision system.

A four-facet design pass (clinical-safety boundary · stage/gate model · annotation grounding · reporting + PHI)
converged on a way to deliver real rare-disease value **without** crossing that line. This ADR records the boundary
and the phased approach so implementation can proceed safely; the architecture detail lives in
[design/variant-interpretation.md](../design/variant-interpretation.md).

The load-bearing insight: bayleaf's three gates (ADR-0013) answer *"can we trust this run / this call?"* — the
variant gate is a **call-quality** gate (DP/GQ/AB/caller-filters). Interpretation answers a **different** question:
*"what does the world already say about a trustworthy call, and in what order should a human review it?"* Those two
questions must stay separate.

## Decision

1. **The variant gate stays QC.** It remains a call-quality checkpoint (DP/GQ/AB/caller-filters; `variant.dp` is the
   one wired threshold today). It never becomes a clinical-significance gate. The interpretation layer never sets,
   overrides, or re-enters it (ADR-0001).

2. **A new, structurally off-gate advisory interpretation layer.** A framework-agnostic core
   `src/pipeguard/interpretation/` (never imported by `rules.py`/`run_gate`, like `triage/` and `pipeline_repair/`)
   surfaces, **per candidate variant, as cited evidence**: ClinVar classification **quoted verbatim** with its
   review-status/star rating + accession + DB version; gnomAD population/popmax allele frequency; a **mechanical**
   inheritance-fit against an operator-declared mode; and the variant-gate call-quality already computed. Plus a
   transparent, **config-driven heuristic review-ordering tier** (`REVIEW_FIRST | REVIEW | DEPRIORITIZED |
   INSUFFICIENT_EVIDENCE`) that always carries its contributing evidence — a *triage ordering*, **not** a
   pathogenicity call and **not** a probability.

3. **bayleaf authors no pathogenicity.** Every clinical-significance statement is a **quotation** of ClinVar (with
   accession + review status), never bayleaf's own determination. No ACMG-classification engine, no calibrated
   probability, no diagnosis, no therapeutic/actionability claim. ACMG evidence codes may be *surfaced as cited
   inputs* but never *emitted* as a final classification — and for the MVP that emission is **deferred entirely**.

4. **Structural clone of the Archivist (ADR-0012), not a new pattern.** The advisory artifact
   (`api/interpretation_agent.py`, an `InterpretationDigest`) pins `advisory: Literal[True] = True`, has **no
   verdict/decision/pathogenicity/confidence field to set**, carries a fixed disclaimer + citations, and refines
   **only** prose via an optional LLM. Stub-first ($0, offline), lazy `anthropic` import, degrade-to-stub on any
   error/refusal, `PIPEGUARD_INTERPRETATION_AGENT=stub|claude` (cheap tier default). AI is OFF by default (ADR-0006).

5. **A cited, human-signed run report.** `api/report.py` is a pure projection over already-decided `DecisionCard`s
   (like `card_readout.py`) — it authors no verdict. It renders provenance header + version pins, decision summary,
   findings-with-evidence (verbatim), the QC readout, an honest "variant gate — not run in this build" empty state
   until variant rules exist, and generated narration in a **visually separated** block (ADR-0001). It is **DRAFT
   until an approver signs off**, reusing the shipped draft→submit→approve lifecycle + `*_by` capture (ADR-0017).
   bayleaf can never mark a report "final" on its own.

6. **Data sharing is an explicit, review-gated, audited egress action — never automatic.** A Share surface composes
   one egress with a selectable **scope** (report / tabular export / artifacts), **location** (local staged dir by
   default; S3 seam off unless armed; Box/GCS/signed-link seams), and **security level** driving a de-identification
   policy, **defaulting to the most privacy-preserving option**. It always ends in an explicit `ConfirmDialog`,
   requires `approver` for external egress, and writes an audited `ShareEvent` to the Admin Activity feed. PHI-scrub
   reuses `api/deid.py` (drop operator PII; gate cohort keys by origin) and documents `DateShift` + free-text
   18-identifier redaction as **labelled seams** — it is a demo seam, explicitly **NOT** HIPAA de-identification.

7. **Compose ≠ execute (ADR-0003).** bayleaf **reads** an externally-produced annotated VCF; it never runs
   VEP/annotators. Reference data (ClinVar, gnomAD, a GIAB truth set) is fetched via accessions + a fetch script,
   never committed raw, origin-tagged (new git-ignored `real-clinvar`/`real-gnomad` origins).

8. **Honest provenance stages (P4).** The downstream stages appear in the provenance DAG with the same honest
   "not run in this build" treatment the align/variant stages already use, becoming real only when an annotated VCF
   is present. (The terminal gate already reads "partial lineage" when upstream stages didn't run — ADR-adjacent
   fix, commit `91cdd6d`.)

## Maintainer decisions (2026-07-10 sign-off)

The maintainer signed off on the boundary above and resolved three of the open questions. Two of
these **change** the "Proposed" recommendations; they are recorded here as the governing decisions.

**D1 — Report name (resolves Q1).** The report is **"QC Decision & Provenance Report"** (as
recommended). "Interpretation report" reads clinical and is not used.

**D2 — Route-to-human belongs ON the gate (resolves Q2; OVERRIDES the Proposed "off-gate for MVP"
recommendation).** The maintainer chose to add a route-to-human action on the gate, framed explicitly
as *"a role-based access gate for human review — the design is already built in."* This is the
single highest clinical-sensitivity call, so its scope is drawn tightly to stay inside ADR-0001 and
Decision 1 (the variant gate stays QC, never a clinical-significance gate):

- **A rule decides to ROUTE; a human decides the outcome.** The gate action is *"human review
  required"* — the most conservative direction (never auto-proceed, never auto-classify). bayleaf
  still authors **no pathogenicity**: the routing rule reads a variant's *already-present, verbatim-
  cited* significance field (e.g. an annotated VCF's `CLNSIG` with its ClinVar review status) as
  **evidence**, and emits an ESCALATE-gated `Finding` that says *"a ClinVar P/LP-flagged candidate is
  present — a human must review before release,"* quoting the source. The annotation never *sets* a
  verdict; a deterministic rule uses cited evidence to route, exactly as every other rule uses cited
  QC evidence. This is "rules decide, humans adjudicate" — not "annotation decides."
- **Not a clinical-significance gate.** The action space is only `{route-to-human}` — there is no
  Pathogenic/Benign verdict, no probability, no actionability. It escalates *toward* human judgment;
  it never renders a clinical determination. Decision 1 holds: the variant **QC** gate (DP/GQ/AB) is
  untouched; this is a distinct, additive review-routing rule.
- **Off by default, config-armed, RBAC-gated, reusing shipped infra.** The rule is an operator-owned
  runbook policy, **off by default** (like every illustrative threshold); when armed it routes via
  the existing review-queue + `require_role` + draft→approve lifecycle (ADR-0017) — a
  reviewer/approver clears the human-review hold. No new access pattern; the "design already built in"
  the maintainer referred to is this RBAC + review-queue seam.
- **Demo substrate honesty.** The only real sample is GIAB **HG002** (a consented benchmark, not a
  patient); any P/LP-flagged candidate that exercises this path is a clearly-labelled
  `origin=contrived` spiked fixture, never implying a real individual (ADR-0004).

**D3 — De-identification: most-conservative, HIPAA-Safe-Harbor-STYLE, as the default (resolves Q7;
strengthens Decision 6).** The maintainer chose the most conservative option (*"HIPAA compliance is so
key here"*). The share/report egress therefore defaults to a **Safe-Harbor-style scrub** that
mechanically removes the **§164.514(b) 18 identifier classes** (names, geographic subdivisions < state,
all date elements finer than year + ages > 89, contact numbers, IDs/accounts, device/biometric ids,
URLs/IPs, free-text catch-all, …), generalizes dates to year, and redacts free-text — the **most
privacy-preserving** policy is the default, and a less-strict policy is an explicit opt-down.
**Honesty guardrail (unchanged):** this is Safe-Harbor-**style** identifier removal, **not** a certified
or attested de-identification — no Expert Determination, no formal audit, no BAA/DUA. It makes **no
compliance claim** (CLAUDE.md life-science guardrail 1); the label says "conservative Safe-Harbor-style
scrub," never "HIPAA-compliant." Real patient data would still require a real, audited de-id program
before any external share.

## Assumptions

- Real rare-disease value comes from **surfacing existing evidence + ordering human review**, not from an automated
  classification the guardrails forbid.
- ClinVar (public/NIH) and gnomAD (open) are fetch-not-redistribute compatible (needs a verified-license table).
- GRCh38 is used consistently across GIAB / ClinVar / gnomAD (no liftover), so citations can't silently mis-align.
- The demo's only real substrate stays GIAB **HG002** — a publicly-consented benchmark, **not a patient**; any
  "positive" variant is a clearly-contrived spiked fixture (`origin=contrived`), never implying a real individual.
- A human approver is always in the loop before a report is final or data is shared externally.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| A full ACMG-classification / pathogenicity-calling engine | Crosses directly into a clinical decision system; forbidden by the biomedical guardrails; would "invent pathogenicity" (ADR-0004). |
| Make clinical significance a 4th **gate** that moves the verdict | Collapses interpretation into the QC gate and lets an annotation drive a decision — violates ADR-0001/0013; keeps the variant gate strictly QC instead. |
| Run the annotator (VEP) inside bayleaf | Violates compose ≠ execute (ADR-0003); bayleaf reads an annotated VCF a driver produced. |
| A calibrated pathogenicity probability | Confidence is a heuristic here (guardrail 2); a probability would misrepresent certainty — omitted, like `DecisionCard.confidence`. |
| Auto-release / auto-share reports | Removes the human sign-off + explicit-egress guarantees; every report is DRAFT-until-signed and every share is confirm-gated + audited. |

## Consequences

| | |
|---|---|
| **Gains** | Delivers rare-disease evidence surfacing + review ordering + a cited, signed report + a safe share seam — all reusing proven patterns (archivist advisory, card_readout projection, draft→approve lifecycle, deid policy, ConfirmDialog). Stays demonstrably *not* a clinical decision system. |
| **Costs** | Real reference data (ClinVar/gnomAD) + fetch scripts + a new core module + models + report/share endpoints + frontend — a multi-part build. PHI-scrub is only partial (labelled seams); external egress carries real privacy risk mitigated by role-gate + confirm + audit, not by compliance controls. |
| **Follow-ups** | Docs owed on build (qc_metrics.md Gate 3, metric_registry.md `variant.gnomad_af` + annotation-source registry, a new data/variant_annotation.md, schemas.md, a license table, data/README origins, ToC). The interpretation **agent**, trio/inheritance context, more annotation sources, `DateShift`/free-text redaction, real S3/Box egress, PDF, and a persisted ledger-anchored report are all **deferred seams**. |

## Realized (current status)

> Dated, commit-by-commit build chronology (D2 route-to-human, D3 share egress + persistence
> parity, the `RunReport` view, the per-variant table) lives in
> [HISTORY.md § ADR-0018](../HISTORY.md#adr-0018--variant-interpretation-what-landed-against-a-committed-run).
> This section is the current state + the honest limits. Verified against `api/main.py`,
> `api/share_store.py`, `tests/test_route_to_human.py`, `tests/test_share_egress.py`,
> `tests/test_run_variants.py`.

**Built end-to-end against a committed run** (2026-07-11):

1. **D2 route-to-human fires (`VAR-RTH-001`).** `api/main._active_runbook(run_id)` arms
   route-to-human **per run** from an optional `route_to_human` marker file in the run dir
   (comma-separated ClinVar significances); absent/empty stays the stock disarmed `DEFAULT_RUNBOOK`.
   The fixture `data/RUN-2026-07-11-CLINVAR-RTH/` (`origin=contrived`: clean QC + a single
   verbatim-cited ClinVar **Pathogenic** BRCA1 spike HG002 does not carry + the arming marker) makes
   HG002 **ESCALATE** through the API. The core default and pinned demo stay disarmed/untouched.
   bayleaf authors **no** pathogenicity — the rule quotes ClinVar and routes to a human (ADR-0001/0004).
2. **D3 Safe-Harbor-style share egress, narrower than the full Share window.**
   `POST /api/runs/{run_id}/share` (`require_role("approver")`) scrubs a run's decision rows via
   `api.safe_harbor.redact_record` → a `ShareBundle` + `ShareManifest` (`policy_id`, `n_rows`,
   `origin`, a sha256 `content_hash` of the exact emitted bytes, the 18 §164.514(b)(2) classes, the
   non-compliance disclaimer), and records a `DATA_EXPORTED` event to the separate, pluggable
   `api/share_store.py` sink (jsonl/sqlite/postgres, degrade-to-JSONL, ADR-0016;
   [provenance.md](../data/provenance.md#a-second-separate-sink-for-share-events-apishare_storepy)).
   Surfaced in Provenance as an approver-only, confirm-gated action. **Narrower than Decision 6:** no
   scope selector, no location choice, no security-level tier (the scrub is the only policy); the
   share audit lands in the run's own Event trail, not (yet) the Admin Activity feed. **Multi-worker
   store locking is a documented seam, not built.**
3. **A `RunReport` view** (`?view=report`, `RunReport.tsx`): verdict mix, a route-to-human hero
   quoting ClinVar VERBATIM, per-sample gate outcomes + cited evidence, a sign-off footer stating
   human sign-off is a labelled seam — built over already-wired `detail`, **not** the full
   `api/report.py`/`ReportStore`/sign-off lifecycle. A `GET /api/runs/{run_id}/variants` read-only
   endpoint (parsed via `pipeguard.parsers.parse_variant_calls`) powers a per-variant table (Sample ·
   Gene · HGVS · ClinVar significance VERBATIM · review status · accession) — only the `VariantCall`/D2
   fields, **no** gnomAD AF / inheritance-fit / call-quality join.

**Genuinely still unbuilt** (per [design/variant-interpretation.md §0](../design/variant-interpretation.md#0-build-status-update-2026-07-10-after-the-maintainers-d1d2d3-sign-off)):
the interpretation **agent**, the `api/report.py`/`ReportStore`/sign-off lifecycle, the full Share
window (scope/location/security-level), gnomAD AF / inheritance-fit evidence, the review-ordering
tier, and the ClinVar/gnomAD fetch scripts.

## Open questions

**Resolved by the maintainer (2026-07-10)** — see [Maintainer decisions](#maintainer-decisions-2026-07-10-sign-off):

1. ~~**Report framing/name**~~ → **DECIDED (D1):** "QC Decision & Provenance Report."
2. ~~**Does route-to-human belong on the gate?**~~ → **DECIDED (D2):** yes, ON the gate, as a
   role-based human-review routing rule (rule routes, human adjudicates; authors no pathogenicity;
   off by default). Overrides the earlier "off-gate for MVP" recommendation.
7. ~~**Dates/free-text de-id strictness**~~ → **DECIDED (D3):** most-conservative Safe-Harbor-style
   scrub as the default (18-identifier removal + date→year + free-text redaction), honestly labelled
   as **not** attested HIPAA de-identification. (PDF & persist-vs-re-render remain open below.)

**Still open (build-time / follow-up):**

3. **Reference-data licensing** verified table; the gene→inheritance source (open PanelApp vs paywalled OMIM).
4. **Transcript convention** (recommend MANE Select, surfaced explicitly) + **gnomAD version/slice** (panel-restricted).
5. **Report grain** — per-run (MVP) vs per-sample vs per-subject/family (trios).
6. **Egress destinations** — which to wire vs leave as seams + the security-level → de-id → destination mapping +
   raw-artifact egress default (recommend "disallow for guarded origins"). Role bar decided by D2's RBAC reuse
   (reviewer internal / approver external).
7. **PDF** — approve a rendering dependency or HTML-only + browser print? **Persist** the report or keep it a live
   re-render like `/api/export` (recommend live re-render for MVP)?

## Revisit when

- The maintainer signs off on the boundary + the open questions above, or asks to move any deferred seam into scope.
- Real patient data (not GIAB HG002) is ever ingested — at which point the PHI-scrub seams stop being forward-looking
  and must be built before any external share.
- A regulatory/clinical-use requirement appears — this ADR's "not a clinical decision system" boundary would need a
  formal re-evaluation, not an incremental change.
