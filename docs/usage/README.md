# bayleaf — Usage & Documentation

| Field | Value |
|---|---|
| **Status** | Living — the operator-facing usage/wiki home (seeded 2026-07-10) |
| **Audience** | lab operators / reviewers / approvers / admins |
| **Related** | [operator-guide.md](operator-guide.md), [design/ui-conventions.md](../design/ui-conventions.md), [design/frontend/README.md](../design/frontend/README.md), [requirements/functional.md](../requirements/functional.md), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) |

> **Why this section exists.** Per UI convention [UIC-1](../design/ui-conventions.md#uic-1--no-page-flavor-text-the-nav-names-the-page),
> the app itself carries no page "flavor text" — the explanatory prose that helps a new operator
> lives **here**, not in the page chrome. This is the wiki/usage home; link to it from a Help entry.
>
> **Format.** These are plain-markdown docs (the repo's native format). If we later want a rendered
> site, the same markdown compiles under **Quarto** (`quarto render docs/usage`) or MkDocs with no
> rewrite — the content is tool-agnostic on purpose.

## What bayleaf is (one paragraph)

bayleaf is an **AI-assisted provenance & QC decision gate** for genomics runs. Deterministic
**rules decide** a per-sample verdict (proceed / hold / rerun / escalate) from cited evidence; an
LLM only **narrates and advises** and is off the critical path ([ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md)).
It is a research/demo tool with production intent — **not** a clinical decision system, and it makes
no diagnostic or therapeutic claims.

## The operator workflow (the through-line)

```
Accession ─▶ Submit ─▶ (pipeline runs) ─▶ Intake gate ─▶ Decision cards ─▶ Review queue
   CRM        samplesheet                    preflight       per-sample        act on
 subjects    wetlab I/O                        QC             verdicts        escalations
                                                 └─▶ Provenance (lineage · event trail · artifacts)
                                                 └─▶ Monitoring (fleet trends · recurring issues)
                                                 └─▶ Inbox (personal triage: flag · schedule · notes)
```

Start each page's how-to in the [Operator guide](operator-guide.md).

## Page index

| Page | What it's for | Guide |
|---|---|---|
| **Inbox** | Personal triage of escalations/reruns/holds — flag, prioritize, schedule, note (off the gate) | [guide](operator-guide.md#inbox) |
| **Review queue** | Flagged samples become tickets — acknowledge, suppress, escalate, resolve | [guide](operator-guide.md#review-queue) |
| **Sample accessioning** | Register subjects + clinical/study metadata (the CRM step) before the wetlab samplesheet | [guide](operator-guide.md#sample-accessioning) |
| **Submit samplesheet** | Register a run + its samples (barcodes, study) before processing | [guide](operator-guide.md#submit-samplesheet) |
| **Intake gate** | Preflight: run-level sequencing QC + which samples are admitted | [guide](operator-guide.md#intake-gate) |
| **Decision cards** | The per-sample verdict + cited evidence + advisory narration | [guide](operator-guide.md#decision-cards) |
| **Runs** | The index of all runs and their status | [guide](operator-guide.md#runs) |
| **Provenance** | Lineage DAG · the append-only event trail · the artifact index | [guide](operator-guide.md#provenance) |
| **Agent triage** | The advisory QC-triage agent's read of a run (off the gate) | [guide](operator-guide.md#agent-triage) |
| **Monitoring** | Fleet-level verdict trends + recurring issue signatures | [guide](operator-guide.md#monitoring) |
| **Pipeline builder** | Compose/inspect the analysis pipeline graph (compose ≠ execute) | [guide](operator-guide.md#pipeline-builder) |
| **Settings** | Profile, theme/density, notifications, agent & model tiering | [guide](operator-guide.md#settings) |
| **Admin** | Governance: users & roles, page access, activity audit, system posture | [guide](operator-guide.md#admin) |

## Roles & page access (read this first)

- **Wire roles** (viewer / reviewer / approver) gate off-gate *writes* (approvals, tickets) — enforced
  by the API. **Admin** is a separate governance capability.
- **Page access** is a client-side *view gate* an admin assigns per user (Admin → Page access): it
  decides which pages appear in the nav. It is **not** authorization — the API still checks the wire
  role on every write. A floor of Runs + Decision cards is always visible.
- A single person can hold several roles/pages, so one platform serves accessioning, wetlab, review,
  and approval without switching tools.

## TODO (this doc is seeded, not finished)

- Fill each page's step-by-step in [operator-guide.md](operator-guide.md) (stubs are in place).
- Add screenshots once the flavor-text/tabs/hierarchy conventions ([UIC-1](../design/ui-conventions.md), [UIC-2](../design/ui-conventions.md), [UIC-3](../design/ui-conventions.md)) land.
- Decide render target (plain md vs Quarto/MkDocs) if we publish it.
