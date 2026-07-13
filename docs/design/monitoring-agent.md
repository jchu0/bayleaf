# Monitoring agent — a pipeline tool-agent for runtime resilience

| Field | Value |
|---|---|
| **Status** | Proposed (design) |
| **Last updated** | 2026-07-13 (MST) — initial design |
| **Audience** | software / design / reviewers |
| **Related** | [ADR-0023](../adr/ADR-0023-agent-taxonomy-and-action-boundary.md) (tool-agent class + action boundary), [ADR-0024](../adr/ADR-0024-scope-by-wiring.md) (its file access), [ADR-0025](../adr/ADR-0025-versioned-reversible-agent-config.md) (versioned card config), [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md) (Nextflow portability), [agent-capabilities.md](agent-capabilities.md) (feeds pipeline-repair), [agents.md](agents.md) |

## Why

Long pipeline runs on distributed storage hit **transient, non-decision faults**: connectivity
drops, file-not-found races, I/O hiccups, OOM. Today these fail a run and wait for a human. The
maintainer wants an agent that **watches a run as it executes** and, within operator-set bounds,
**auto-heals** the transient ones — and logs everything (resolved or not) as structured data the
(advisory) **pipeline-repair** agent can learn from.

Crucially, this is a **tool-agent** (ADR-0023): the operator **opts in by wiring it into the
pipeline graph**, not a system-wide fixture. It is the first agent allowed to *act*, under a hard
**action boundary**.

## What it does

1. **Observes** a running pipeline — reads the driver/job state and the logs/outputs of the tools
   it is wired to (`pipeline.log`, `.nextflow.log`, work-dir status), scoped by ADR-0024 and
   de-identified.
2. **Classifies** each anomaly into an **issue class** (connectivity / file-not-found race /
   transient I/O / OOM / non-pipeline / unknown). Deterministic keyword/pattern match is the
   stub; live Claude refines ambiguous cases (stub-first, ADR-0006).
3. **Acts or reports, per the card policy** (below): auto-retry the class, or detect-and-report it.
4. **Logs every issue** — resolved or not — as a structured record to the **issue store**, which
   pipeline-repair consumes (ADR-0023 §4).

## Action boundary (hard)

Per ADR-0023: an action may only affect **execution resilience** (retry / pause / escalate). It
**never** touches a verdict, finding, confidence, decision card, or data-artifact content. Retry
re-runs an idempotent task; it does not edit results. This must be enforced in code and covered by
a test that proves the monitoring path *cannot* reach a verdict/finding/data write.

## Tool-card configuration (operator-owned, versioned)

The card is the control surface (no Settings involvement — ADR-0024):

1. **Issue-class checklist** — common classes pre-populated; each set to **auto-retry** or
   **detect-and-report**. Unset classes are report-only by default (conservative).
2. **Free-text watch specs** — a chat box where the operator describes additional things to watch
   ("alert if a step exceeds 2× its usual wall-time"); the agent updates dynamically from this.
3. **Retry caps** — max attempts + backoff per auto-retry class.
4. **Versioned + reversible** (ADR-0025) — every edit is a tagged revision; the run pins the exact
   revision in force, so an auto-retry is always attributable to a recoverable policy.

## Relationship to Nextflow (don't reinvent retry)

Nextflow already offers `errorStrategy 'retry'` + `maxRetries` per process, and the repo's durable
**job store** (`api/job_store.py`) already reconciles `running → complete/lost` across restarts. The
monitoring agent's value-add is **classification + escalation + the issue trail**, not a new retry
engine: where a class maps cleanly to a Nextflow directive, prefer emitting/compiling that directive
(ADR-0003 keeps compute in Nextflow); the agent handles the cross-task, cross-run judgment and the
structured logging Nextflow doesn't do.

## Issue store (structured, ML-minable)

Off-gate store (`base_store.py` pattern). Record:
`{issue_id, run_id, node_id, ts, class, signature, detail, action: retried|reported|escalated,
attempts, resolved: bool, resolved_at?, policy_tag}` — timestamped, run/node-tagged, retained for
ML. This store is exactly pipeline-repair's issues+resolutions corpus (agent-capabilities.md §2).

## Invariants

1. **Opt-in** — no node wired → no monitoring, no actions (ADR-0006).
2. **Action boundary** — resilience only; never decision/data (ADR-0023).
3. **Least-privilege** — reads only wired tools' outputs/logs, de-identified (ADR-0024).
4. **Auditable + reversible** — policy versioned; every action logged + attributable (ADR-0025).
5. **Stub-first** — deterministic classifier works AI-off; live Claude only when enabled.

## Open questions

- Does the agent poll the job store/logs, or subscribe to an event stream? (Poll is simpler given
  the existing job store; a loop cadence needs a cap.)
- OOM auto-retry usually needs a *resource bump* to succeed — is bumping resources within the
  action boundary, or does it become detect-and-report (a config change a human approves)?
- How to bound live-Claude cost on a long run (classify only novel/ambiguous errors; cache class
  decisions by signature).
