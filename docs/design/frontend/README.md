# PipeGuard — Frontend Prototype

| Field | Value |
|---|---|
| **Status** | Prototype (clickable mockup) |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | design / frontend |
| **Related** | [frontend-design-brief.md](../frontend-design-brief.md) · [README.md](../../../README.md) |

## What this is

A high-fidelity, **clickable** prototype of the PipeGuard operator UI — the visual +
interaction target for the eventual React frontend. It renders the six core screens
from the brief against the bundled `data/mock_run_01` scenario (S1–S3 proceed, **S4
escalate** on an index swap + missing `subject_id`, **S5 hold** on borderline QC).

It is design intent, not production code — but every number and citation on screen
traces to the real mock run, so it doubles as a spec for what the React views must show.

## How to view

Open **`PipeGuard.html`** in any browser. It is a single self-contained file (fonts,
styles, and rendering runtime inlined) — no build step, no server, works offline.

## Screens

1. **Runs** — run list with per-run verdict-count bars, "needs attention" flags, and light filters. The entry point.
2. **Decision cards** (the hero) — verdict badge, headline, rationale, recommended next steps, and a **cited-evidence table** (source · field · observed · expected). Three layout treatments to compare: **Split / Brief / Dense**.
3. **Review queue** — cards-as-tickets (open → in-review → resolved) with acknowledge / suppress-issue-class / escalate / resolve, plus reviewer-vs-approver gating (escalations lock resolve for a Reviewer).
4. **Provenance** — read-only intake → demux → QC → align → variant-call → gate DAG; click a stage to inspect its data I/O (inputs, outputs, hashes, real/synthetic origin tags).
5. **Agent triage** — advisory note (likely cause, suggested action) citing both the run's findings and a knowledge/experience corpus, with an offline/live toggle.
6. **Settings** — operator profile, Slack channel, model tiering, and the read-only runbook thresholds.

**States.** Loading / empty / error are wired throughout — preview them with the
**State** control in the top bar.

## Design system (as prototyped)

- **Type:** IBM Plex Sans (UI) + IBM Plex Mono (IDs, values, hashes, barcodes) — precision-forward, not flashy.
- **Verdict semantics:** proceed = green · hold = amber · rerun = orange · escalate = red. Finding severity: critical / warn / info.
- **First-class primitives:** evidence tables, citations, status badges, origin tags (real/synthetic).

## Not yet / out of scope

- **Confidence heuristic** intentionally omitted (not grounded in anything concrete yet).
- Data is **static mock**; there is no live API or synthesis call.
- Out of scope per the brief: editable pipeline builder, deep settings, data-platform integrations.

## Regenerating

`PipeGuard.html` is a bundled export of a Design Component (`PipeGuard.dc.html`, kept in
the design workspace). To change the prototype, edit the source there and re-export the
self-contained bundle over this file.
