# Design Handoff — Prototype Alignment & Freshness (2026-07-07)

| Field | Value |
|---|---|
| **Status** | Active |
| **Date** | 2026-07-07 (MST) |
| **From → To** | Alignment review (Claude Code) → design |
| **Graded** | `bayleaf.html` prototype vs the final schema/QC design |
| **Related** | [frontend-design-brief.md](../frontend-design-brief.md), [schemas.md](../../../data/schemas.md), [qc_metrics.md](../../../data/qc_metrics.md), [metric_registry.md](../../../data/metric_registry.md) |

## Context

An adversarial review graded the prototype against the now-final data spine
([schemas.md](../../../data/schemas.md)), QC runbook ([qc_metrics.md](../../../data/qc_metrics.md)),
and metric vocabulary ([metric_registry.md](../../../data/metric_registry.md)). The prototype
is **broadly faithful** — the work is preserving what is right and closing two real gaps.

## Keep — do not regress

1. Four verdicts `proceed / hold / rerun / escalate`; three gates `preflight → qc →
   variant`; breadth-first coverage (`% target ≥ 20×`, callable gaps); saliva/whole-blood
   sample-type; provenance canvas with I/O hashes + origin tags; the Source · Field ·
   Observed · Expected evidence surface.
2. **No confidence value is shown — this is correct and deliberate** (see Traps).

## Change (P1)

1. **Identity gate.** Add a **Sample-identity / swap** card whose *primary* signal is
   **NGSCheckMate genotype concordance** (`identity.ngscheckmate_match`, from
   `ngscheckmate_matched.txt`), shown next to sex-vs-coverage concordance. Demote
   **Contamination · FREEMIX** to an *optional, explicitly non-sarek-default* extra — not an
   always-on co-equal tile.
   *Why:* a tube/label swap that preserves barcodes passes on index + sex alone;
   NGSCheckMate is what catches it and is the sarek default. FREEMIX/VerifyBamID2 is a
   separate optional contamination step.
2. **Per-gate results on the card.** Add a strip showing **Preflight / QC / Variant**, each
   with its own verdict badge + severity + one-line rationale + the findings that drove it.
   Today the card shows one dominant-gate tag + a fleet pass-rate; the schema models a
   `GateResult` per gate per card ([schemas.md](../../../data/schemas.md)).
   *If too heavy for MVP, say so and we will scope `GateResult` out of the schema — but it is
   the "which gate, and why" story, so it is worth showing.*

## Polish (P2)

1. Retag the `operational` gate value → a real gate (`preflight`|`qc`) with `cat: 'pipeline'`
   — the gate enum is only `preflight|qc|variant`.
2. Add a `source_kind` chip to evidence rows
   (`artifact|metric|multiqc_source|execution_trace|params|human_note`); optionally split
   `threshold` from `expected`.
3. Origin tokens: `real` → `real-giab` (and use `contrived` where apt).
4. FREEMIX default → **3% fail with a 1.5–3% borderline band** (prototype hardcodes ≤ 2%, no
   band), or annotate 2% as a deliberate override.
5. Add **zero-coverage targets** (`qc.zero_cov_targets`) as its own card metric; where the
   assay warrants, add **% mapped**, **fold-80 uniformity**, **% target ≥ 30×**.

## Traps

1. **Do not add a confidence %, meter, or bar.** Policy is "omit until grounded"
   ([schemas.md](../../../data/schemas.md), `DecisionCard.confidence`); a heuristic bar would
   misrepresent certainty in a clinical-adjacent tool. The prototype's omission is intentional.
2. Keep the prototype's data using the exact schema tokens (verdicts, gates, origin,
   `source_kind`) — the eventual React port then maps 1:1 to the typed models instead of
   needing a translation layer.

## Verify

The prototype is a single-file minified bundle — open it in a browser and click through to
confirm which metric cards actually render before finalizing this list.
