# Operator Guide — per-page how-to

| Field | Value |
|---|---|
| **Status** | Draft — stub sections (seeded 2026-07-10, Wave 10 sweep); fill in as each screen stabilizes |
| **Last updated** | 2026-07-10 (MST) |
| **Audience** | lab operators / reviewers / approvers / admins |
| **Related** | [usage/README.md](README.md) (the page index this guide answers), [design/ui-conventions.md](../design/ui-conventions.md) (UIC-1: this is where page explanatory prose lives instead of the app chrome), [requirements/functional.md](../requirements/functional.md) |

## Overview

One section per operator screen, in the order [usage/README.md](README.md#page-index) links
them. Each stub names what the screen is for and the one or two things an operator most needs
to know; fill in the step-by-step as the screen's behavior settles (a screen still in active
UI iteration is not worth writing a stale walkthrough for — see
[DOCUMENTATION_HABITS.md](../DOCUMENTATION_HABITS.md) principle 5).

## Inbox

Personal, off-gate triage workspace (flag / prioritize / schedule / note escalations, reruns,
holds). Per-operator, `localStorage`-persisted. TODO: step-by-step.

## Review queue

Flagged samples become tickets here — acknowledge, escalate, resolve, suppress. Escalation is
role/access-gated (UIC-10). TODO: step-by-step + the run/sample checkbox hierarchy (UIC-3).

## Sample accessioning

Register subjects + clinical/study metadata (the CRM step) **before** the wetlab samplesheet.
Everything on this screen stays client-side (no PII/PHI transmitted) — see
[REQ-NF-023](../requirements/nonfunctional.md). TODO: step-by-step.

## Submit samplesheet

Register a run + its samples. `sample_metadata.csv` is **required** and its identity join against
the samplesheet needs an explicit human "Approve join" before submit — sample-identity mixups are
the highest-consequence error this screen guards against (UIC-11,
[REQ-NF-025](../requirements/nonfunctional.md)). TODO: step-by-step.

## Intake gate

Preflight: run-level sequencing QC and which samples are admitted downstream. TODO: step-by-step.

## Decision cards

The per-sample verdict, cited evidence, and advisory AI narration (framed as a distinct block
under the evidence tables, never mixed with it — UIC-8, ADR-0001). TODO: step-by-step.

## Runs

The index of all runs and their status. TODO: step-by-step.

## Provenance

Lineage DAG, the append-only event trail, and the artifact index (with download + a full-digest
reveal, UIC-9). TODO: step-by-step.

## Agent triage

The advisory QC-triage agent's read of a flagged card — off the gate, cited, heuristic (not a
calibrated probability). TODO: step-by-step.

## Monitoring

Fleet-level verdict trends and recurring issue signatures. TODO: step-by-step.

## Pipeline builder

Compose/inspect the analysis pipeline graph — compose ≠ execute, it never runs a tool. TODO:
step-by-step; note the "Author a tool node" advisory-agent entry point once wired (see
[design/node-authoring-agent.md](../design/node-authoring-agent.md)).

## Settings

Profile, theme/density, notifications, and the agent & model tiering table. TODO: step-by-step.

## Admin

Governance: users & roles, page access, activity audit, system posture. Off the deterministic
gate. "Act as" requires re-authentication and is written to an append-only audit log (UIC-13).
TODO: step-by-step.

---

*Marker legend — distinguish claim types where confusion is likely:*
**Fact** · **Assumption** · **Decision** · **TODO**.
