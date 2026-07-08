# PipeGuard — Frontend Prototype

| Field | Value |
|---|---|
| **Status** | Prototype (clickable mockup) — v2.1 (alignment review incorporated) |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | design / frontend |
| **Related** | [frontend-design-brief.md](./frontend-design-brief.md) (v2, incorporated) · [README.md](../../../README.md) |

## What this is

A high-fidelity, **clickable** prototype of the PipeGuard operator UI — the visual +
interaction target for the eventual React frontend. It renders the core screens from
the brief against the bundled `data/mock_run_01` scenario (S1–S3 proceed, **S4 escalate**
on an index swap + missing `subject_id`, **S5 hold** on borderline depth/callability).

It is design intent, not production code — but every number and citation on screen
traces to the real mock run, so it doubles as a spec for what the React views must show.

## How to view

Open **`PipeGuard.html`** in any browser. It is a single self-contained file (fonts,
styles, and rendering runtime inlined) — no build step, no server, works offline.

## Screens

1. **Runs** — run list with per-run verdict-count bars, "needs attention" flags, light filters.
2. **Intake gate** — the **preflight** checkpoint: run-level sequencing QC (PhiX, PF, Q30, error rate) + per-sample admission with a **manual override** to admit a genuinely-sparse sample.
3. **Decision cards** (the hero) — per-gate result strip (Preflight / QC / Variant, each with its own verdict + one-line rationale), then a **columnar QC readout by gate** (Metric · Observed · Threshold · Status, flagged-first with a per-gate rollup). Identity leads the QC gate — **NGSCheckMate genotype concordance** (sarek default) next to sex concordance, with FREEMIX demoted to an optional non-sarek-default extra. Depth vs breadth (callability, zero-cov, fold-80) are distinct signals; variant-gate metrics (DP/GQ/Ti-Tv/gnomAD/ClinVar) included. A context rail carries sample, run, the linked swap-pair, and narration source. Three layout treatments: **Split / Brief / Dense**.
4. **Review queue** — cards-as-tickets (open → in-review → resolved); acknowledge, suppress, escalate, resolve; **recurring-signature detection** that escalates to a **pipeline-repair agent** with per-instance (see-one/fix-one) and class-level fix approvals; reviewer-vs-approver (RBAC) gating.
5. **Provenance** — read-only intake → demux → QC → align → variant-call → gate DAG, with the three **gate checkpoints** labelled; click a stage for data I/O (hashes, origin tags real-giab / synthetic / contrived).
6. **Agent triage** — advisory note citing both the run's findings and a knowledge/experience corpus; offline/live toggle.
7. **Monitoring** — run throughput, verdicts-over-time, gate pass rates, and recurring-issue signatures.
8. **Settings** — operator profile, Slack, model tiering, and **editable runbook thresholds keyed on assay × sample type**.

**States.** Loading / empty / error are wired throughout — preview them with the
**State** control in the top bar.

**Interactions.** Back navigation (top bar), expand/collapse decision cards, verdict filters, run switcher, the Intake manual-override toggle, queue actions (acknowledge / suppress / escalate / resolve / repair-agent), an **Ask-the-agent** chat on the triage panel, and editable settings config — all clickable.

## Design system (as prototyped)

- **Type:** IBM Plex Sans (UI) + IBM Plex Mono (IDs, values, hashes, barcodes).
- **Verdict semantics:** proceed = green · hold = amber · rerun = orange · escalate = red. **RERUN is reserved for operational / file-system failures; a data-quality problem is a HOLD.**
- **Gates:** preflight · QC · variant — every finding and verdict is labelled with the gate it came from.
- **First-class primitives:** gate-grouped evidence tables, `source_kind` chips (artifact / metric / trace / …), citations, status badges, origin tags (real-giab / synthetic / contrived), sample-type-aware thresholds.

## Incorporated since v1 (per ADR-0013)

Three-gate model + intake gate; RERUN-vs-HOLD verdict philosophy; depth vs breadth as
distinct signals; richer QC evidence (breadth/callability, FREEMIX, sex/identity,
variant-level); recurring-issue escalation to the pipeline-repair agent with fix-one /
fix-class approvals; sample-type-aware thresholds; operator-adjustable config; a light
monitoring view. **Confidence stays omitted** until it is grounded.

**Alignment-review pass (per ADR-0013 grading):** identity gate with NGSCheckMate as the primary swap signal (FREEMIX demoted); a per-gate `GateResult` strip on each card; `operational` retagged to the `qc` gate with `cat: pipeline`; `source_kind` on evidence rows; origin tokens `real-giab` / `contrived`; FREEMIX ≤ 3% with a 1.5–3% band; added zero-cov targets, % mapped, fold-80 uniformity, % target ≥ 30×; barcodes split into i7 / i5 rows with mismatched bases highlighted; QC readout reorganised into a columnar table. Schema tokens match `schemas.md` so the React port maps 1:1.

## Regenerating

`PipeGuard.html` is a bundled export of a Design Component (`PipeGuard.dc.html`, kept in
the design workspace). To change the prototype, edit the source there and re-export the
self-contained bundle over this file.
