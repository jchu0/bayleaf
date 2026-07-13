# ADR-0023 — Agent taxonomy & action boundary: advisory agents vs. tool-agents

| Field | Value |
|---|---|
| **Status** | Proposed |
| **Date** | 2026-07-13 (MST) |
| **Deciders** | maintainer (James), Claude |
| **Related** | [ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md) (rules decide / AI advises), [ADR-0006](ADR-0006-ai-off-by-default-fallback.md) (AI off by default), [ADR-0012](ADR-0012-agent-scoping-model-tiering.md) (scoping/tiering), [ADR-0022](ADR-0022-agent-observation-binding.md) (observation binding), ADR-0024 (scope-by-wiring, proposed), ADR-0025 (versioned agent config, proposed), [design/agents.md](../design/agents.md) |

## Context

Every agent in bayleaf today is **advisory**: it narrates/suggests/cites but never acts — the
deterministic rule engine decides, and agents sit off the critical path (ADR-0001/0006). That
invariant has held because all six seams (synthesizer, QC-triage, pipeline-repair, node-author,
feedback, archivist) only *read* and *write prose*.

The proposed **monitoring agent** breaks this: it watches a pipeline *while it runs* and can
**auto-retry** transient failures (connectivity drops, file-not-found races on distributed
storage, I/O hiccups). Auto-retry is an **action**, not advice. We need an explicit rule for
whether — and how — an agent may act, without eroding the decision-gate guarantee that has made
the system trustworthy. The maintainer also scoped the monitoring agent as a **tool the operator
opts into by wiring it into the pipeline** (a graph node), not a system-wide fixture, and wants
its action policy **user-configured, dynamic, versioned, and reversible**.

## Decision

Introduce **two agent classes** with a hard boundary between them.

1. **Advisory agents** (unchanged): synthesizer, QC-triage, pipeline-repair, node-author,
   feedback, archivist. Off the critical path; read + emit cited prose/proposals; **never** set
   or alter a verdict, finding, confidence, or data artifact (ADR-0001/0006 preserved verbatim).

2. **Tool-agents** (new): an agent wired into the **pipeline graph as a node** the operator
   chooses to add (like any tool card). A tool-agent MAY take **bounded operational actions**
   on the *execution* of a run, governed by a per-issue-class policy on its tool card. The
   monitoring agent is the first tool-agent.

The boundary a tool-agent must never cross — the **action boundary**:

3. An operational action may only affect **pipeline execution resilience** (e.g. retry a failed
   task, pause, escalate). It must **never** touch a verdict, finding, confidence, decision card,
   or the *content* of a data artifact. Anything decision- or data-bearing stays with the
   deterministic gate + human review.

4. Every action is **logged as a structured issue record** (resolved or not) to an append-only
   **issue store** — timestamped, actor/agent-tagged, ML-structured (per the structure-for-ML
   principle) — and surfaced to the (advisory) **pipeline-repair** agent as its live corpus.

5. A tool-agent's action policy is **user-configured on its tool card**: a checklist of
   common issue classes (connectivity / file-not-found race / transient I/O / OOM / …) each set
   to **auto-retry** or **detect-and-report**, plus a free-text box to spec custom watch tasks
   that update the agent dynamically. Auto-retry is **capped** (max attempts) and prefers
   Nextflow's native `errorStrategy 'retry'`/`maxRetries` where the failure class allows it —
   the agent's value-add is *classify → log → escalate*, not reinventing retry.

6. The policy is **versioned and reversible** (see ADR-0025): every card-config change is a
   tagged revision that can be rolled back; the running agent always reflects a specific pinned
   revision, and the run's provenance records which one was in force.

7. Tool-agents remain **OFF by default** (ADR-0006): a pipeline without the node has no
   monitoring and no actions; a wired node with an empty policy only observes.

## Assumptions

- Retrying a failed *task* is safe because Nextflow tasks are designed to be idempotent/
  re-runnable; a retry re-executes compute, never edits a decision or data content.
- Operators want per-class control (some classes auto-heal, some must page a human) rather than
  one global "autonomous yes/no."
- The pipeline-repair agent (advisory) is the right consumer of the issue store — it already
  proposes cited remediations for recurring signatures.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Keep ALL agents advisory; monitoring only detects + reports, humans/Nextflow retry | Safest, but loses the auto-heal the maintainer wants for transient infra faults on long distributed runs; still viable as the per-class "detect-and-report" setting within this ADR. |
| Make monitoring a system-wide always-on service (not a graph node) | Contradicts the opt-in, per-pipeline scoping the maintainer specified; couples every run to a monitor it may not want. |
| One global "agent autonomy" switch in Settings | Too coarse; the maintainer wants per-issue-class, on-the-card granularity, and we are removing settings-based agent config in favor of on-graph config (ADR-0024). |

## Consequences

| | |
|---|---|
| **Gains** | A principled place for an agent that *acts*, without weakening the decision gate; auto-heal for transient infra faults; a structured issue trail that feeds pipeline-repair; opt-in, per-run, per-class control. |
| **Costs** | A genuinely new capability class to build + guard (bounded actions, caps, audit); a new issue store; the action boundary must be enforced in code + tested (an action must be *unable* to reach a verdict/finding/data path). |
| **Follow-ups** | ADR-0024 (scope-by-wiring gives the monitoring agent its file access); ADR-0025 (versioned/reversible card config); design docs for the monitoring tool-agent + the issue store schema; a test that proves a tool-agent action cannot mutate a verdict/finding/data artifact. |

## Revisit when

- A tool-agent needs to act on something that *is* decision- or data-bearing (that would be a
  new, larger decision — likely a rejection or a heavily-gated exception).
- Auto-retry proves unsafe for some task class (non-idempotent side effects) — tighten the
  whitelist or drop to detect-and-report for that class.
