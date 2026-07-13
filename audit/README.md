# Audit — release-hardening reviews (point-in-time snapshots)

| Field | Value |
|---|---|
| **Status** | Archive — point-in-time snapshots, not routinely maintained |
| **Audience** | contributors, reviewers, and the curious |
| **Registered in** | [docs/TABLE_OF_CONTENTS.md](../docs/TABLE_OF_CONTENTS.md#audit-release-hardening-review-repo-root--not-under-docs) |

**What this is.** These are *internal* release-hardening reviews of bayleaf — a structured
multi-agent audit (2026-07-11) plus grounded gap analyses and wishlist design panels. They are
**evidence of how the project was reviewed and hardened**, kept for anyone who wants to see the
rigor behind the build. They are honest by design: several files candidly enumerate where a
"confident surface" ran ahead of "thin wiring." That candor is the point — the findings were then
**acted on**, tracked as rows in [docs/planning/tasks.md](../docs/planning/tasks.md) and closed by
code/doc changes.

**What this is not.** Not a live doc set. Unlike the canonical docs under `docs/`, an audit file is
a snapshot of what was true when it was written — it does not get routine upkeep. Read it for the
reasoning and the review discipline, not as current-state truth (the canonical docs and the code
carry that). A finding here that reads as a gap may well be closed; follow it to its `tasks.md` row.

## Contents

| Path | What it is |
|---|---|
| [AUDIT_PLAN.md](AUDIT_PLAN.md) | The release-hardening audit plan — two tracks (hardening findings, wishlist feasibility), 10 read-only specialist agents |
| [SYNTHESIS.md](SYNTHESIS.md) | The consolidated, adversarially re-verified findings (P0–P3; CONFIRMED/UNVERIFIED/REFUTED) + the pre-recording go/no-go checklist |
| `{ui-ux, data-lineage, journeys, integration, reliability, agent-safety, science-repro, demo-readiness, contract, truthfulness}.md` | The 10 individual specialist reports `SYNTHESIS.md` consolidates |
| [gap_analysis/](gap_analysis/) | Grounded, source-cited "confident surface vs. thin wiring" workstream fix plans (WS-01…WS-10) + their living tracker |
| [wishlist/](wishlist/) | 3-approach design panels on four wishlist items, feeding `tasks.md` (T-126–T-130) |
