# Journal — 2026-07-10 (MST) — Wave 6: variant interpretation design + ADR-0018 (+ P3 gate fix)

| Field | Value |
|---|---|
| **Focus** | Open the maintainer's biggest, most clinically-sensitive feedback item — extend PipeGuard past variant CALLING into filtering/prioritization → annotation → interpretation → reporting for rare disease ("full interpretation + report") — with a DESIGN pass + ADR rather than an improvised clinical-interpretation engine. Plus ship the one concrete, buildable piece (P3). |
| **Participants** | maintainer (chose "full interpretation + report"); a 4-facet parallel design workflow (opus, ~415k tokens) |
| **Outcome** | Design pass → **ADR-0018** (the boundary + phasing) + **design/variant-interpretation.md** (the architecture). One concrete fix shipped: **P3** — the provenance terminal gate reads "partial lineage" (neutral) instead of green when upstream align/variant didn't run (commit `91cdd6d`). The interpretation engine/report/share are designed, **not built** — gated on ADR-0018's open questions. |

## Discussion

### Why design-first
The maintainer asked for the fullest downstream chain, but the biomedical guardrails (CLAUDE.md 1–5) forbid PipeGuard becoming a clinical decision system (no diagnosis, no invented pathogenicity, confidence is a heuristic). Improvising a pathogenicity-calling engine at the tail of a build session would be irresponsible, so the wave opened with a 4-facet parallel design workflow: (1) clinical-safety boundary, (2) stage/gate model + provenance, (3) annotation/interpretation grounding, (4) reporting + data-sharing/PHI. Each read the real guardrails/ADRs/code and returned a grounded memo.

### The load-bearing decision
The memos converged (captured in ADR-0018): the variant **gate stays QC** (call-quality — DP/GQ/AB/caller-filters); a **new, structurally-off-gate advisory layer** surfaces per-variant **cited** evidence (ClinVar quoted verbatim + gnomAD AF + mechanical inheritance-fit) and a **config-driven heuristic review-ordering tier** — never a pathogenicity call, no ACMG verdict, no probability, no diagnosis. It is a **structural clone of the Archivist** (advisory=True pinned, no verdict/confidence field, deterministic base + optional LLM prose, stub-first, degrade-to-stub). A cited `RunReport` projection (like `card_readout.py`) is DRAFT-until-an-approver-signs; a review-gated, audited, explicit-confirm Share window (scope · location · security-level → `deid.py`, most-private default) handles P2; compose ≠ execute (reads an annotated VCF, never runs VEP). The provenance DAG gains the downstream stages honestly ("not run in this build") — P4.

### P3 (shipped)
Concrete, buildable, verifiable now: the Provenance terminal Decision-gate node rendered a confident green "Completed" whenever the overall verdict was Proceed — even when Alignment/Variant-calling are gray ("not run in this build"). A green terminal after gray mid-sequence stages reads as an end-to-end pass that never happened. Added a muted `partial` status: proceed + skipped upstream ⇒ "Decided on partial lineage" (neutral, not green) with an explanatory note. Escalate/hold gate states unchanged. Verified live on RUN-2026-06-05-GIAB-A.

## Decisions

| Decision | Distilled to |
|---|---|
| Variant interpretation is advisory cited evidence + heuristic review-ordering, NOT a clinical decision engine; the variant gate stays QC | [ADR-0018](../adr/ADR-0018-variant-interpretation-advisory-evidence.md) |
| The architecture (module map, models, phasing, data grounding, reporting/share) | [design/variant-interpretation.md](../design/variant-interpretation.md) |
| Terminal provenance gate must not read green while upstream stages are skipped | commit `91cdd6d` (P3); ADR-0018 §Decision 8 |

## Open questions & TODO

- **ADR-0018 open questions need a maintainer decision before/while building** — esp. whether any ClinVar/gnomAD-driven *route-to-human* belongs on the gate (recommend: off the gate for MVP, advisory only), report naming, reference-data licensing, egress role bar + destinations, PHI-scrub depth (dates/free-text as seams vs a minimal redactor now), PDF dependency, persist-vs-live-render.
- The interpretation core/agent/report/share + ClinVar/gnomAD fetch scripts + P4 stage additions + P2 PHI seams are **implementation, not yet built** (T-104).

## Distilled into

- [docs/adr/ADR-0018-variant-interpretation-advisory-evidence.md](../adr/ADR-0018-variant-interpretation-advisory-evidence.md) — new.
- [docs/design/variant-interpretation.md](../design/variant-interpretation.md) — new.
- [docs/TABLE_OF_CONTENTS.md](../TABLE_OF_CONTENTS.md) — ADR-0018 row.
- [docs/planning/tasks.md](../planning/tasks.md) — T-104.
- P3 shipped in `frontend/src/screens/Provenance.tsx` (commit `91cdd6d`).
