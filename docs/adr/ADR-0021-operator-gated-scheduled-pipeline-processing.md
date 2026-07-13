# ADR-0021 — Operator-gated, scheduled sample processing on authored pipelines

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-12 (MST) |
| **Deciders** | bayleaf maintainers |
| **Related** | ADR-0003 (deployment-agnostic ports / Nextflow), ADR-0014 (approval gate), ADR-0019 (pipeline versioning + run pinning), ADR-0020 (operator-authored custom processes); `api/routers/intake.py`, `api/routers/pipeline_run.py`, `api/authored_pipeline.py`, `api/job_store.py` |

## Context

Two gaps sat in the sample-processing (intake) execution path — `POST /api/runs`, the endpoint the
Submit screen hands a samplesheet to and which fires the Nextflow driver:

1. **Intake ignored authored pipelines.** `POST /api/runs` always ran the committed
   `germline-panel` reference (the driver's HG002 defaults). The *Builder-Run* path
   (`POST /api/pipelines/run`, ADR-0014) already resolves + compiles + runs an operator-**authored**,
   approver-blessed pipeline by name — but a sample-processing run could not target one. An operator
   who composed and approved a panel-specific pipeline had no way to actually process real samples
   through it.

2. **A sequencer finishing force-processed the run.** Registration and driver launch were one
   atomic act: the instant a run was submitted, the driver fired. There was no way for an operator
   to gate processing — to stage a run and release it deliberately, or to schedule it for later
   (off-peak compute, waiting on a dependency, a review window). A finishing sequencer should not
   compel immediate processing; an operator should decide *when*.

Both are execution-boundary concerns, off the deterministic decision gate. The **compose ≠ execute**
boundary (ADR-0003) must hold: the core (`src/bayleaf/`) still never runs a tool; only the
out-of-core driver shells out to Nextflow.

## Decision

**1. Sample processing runs operator-authored, approved pipelines.** `SubmitRunIn` gains an optional
`pipeline` name (+ optional `pipeline_version`). When present, intake resolves and compiles that
pipeline via the **same approval gate** the Builder-Run path uses — factored into a shared
`api/authored_pipeline.py` (`resolve_approved` + `compile_record` + `materialize_bundle`), so both
routers share ONE gate and ONE compile path and neither ever runs a raw client-posted graph. A name
with no approver-blessed (`emitted`) version is a **409**, exactly as `POST /api/pipelines/run` gives
(ADR-0014). When absent, intake runs the committed `germline-panel` reference as before
(backward-compatible — for that pipeline the compiled bundle *is* the committed reference,
drift-proven, so behavior is byte-preserved). Running a non-default authored pipeline requires
reviewer/approver — the endpoint's existing `require_role` gate.

**2. A processing gate: immediate / hold / schedule.** `SubmitRunIn` gains a `mode`:

- `immediate` (default) — fire the driver now (unchanged behavior).
- `hold` — register the run + job in a new **`held`** state; do **not** fire the driver.
- `schedule` — store `scheduled_at` (an ISO-8601 timestamp, required) and register in a new
  **`scheduled`** state; do not fire the driver.

`POST /api/runs/{id}/release` (reviewer/approver) transitions a `held` or `scheduled` run → `running`
and fires the driver, reading the driver params (platform / run-date / submitted-by / the compiled
authored `pipeline_path`) from the persisted job record so the release fires the driver identically
to an immediate submit. A run not in a parked state is a **409**; an unknown run a **404**.

**A time-based auto-release scheduler is a DEFERRED seam — deliberately not built.** `scheduled`
behaves as `hold` plus a stored `scheduled_at` and an honest note; the operator releases it manually.
No background thread, cron, or timer wakes a scheduled run. This is called out in
`api/job_store.py` (`HELD_STATUSES`) and the `release_run` docstring so it is not mistaken for a
live scheduler.

## State machine

```
                 submit (mode)
                      │
       ┌──────────────┼───────────────────────┐
   immediate         hold                   schedule
       │              │                        │
    queued          held ───────────┐    scheduled ──── (stores scheduled_at)
       │              │  release     │        │  release
       │              └──────────────┼────────┘
       ▼                             ▼
    running  ◄───────────────────────┘
       │
   ┌───┴────────────┐
complete          failed
       │
   (lost = owner process died mid-run with no result dir — reconcile only)
```

- `queued | running` are in-flight (an `immediate` submit or a `release` reserved the run id in the
  in-process `_active` set and launched a driver thread).
- `held | scheduled` are **operator-parked** (`HELD_STATUSES`): registered without a thread. The
  durable-job-store **reconcile** logic (restart recovery) is kept intact but must treat these as
  parked — a held/scheduled job whose process never started stays parked, and is **never**
  mis-reconciled to `lost` the way a genuinely died-mid-run `queued`/`running` job is.
- `complete | failed | lost` are terminal (`TERMINAL_STATUSES`, unchanged).

## Assumptions

- The single-node, single-worker durability model of the job store (ADR-0016) holds: same-process
  duplicate-submit is guarded by the in-memory `_active` set plus a check for a persisted **parked**
  job of the same run id (a parked run has no data dir and is not in `_active`, so it needs the
  store check to be dedup-safe). Multi-worker locking remains the documented job-store seam.
- An operator, not a timer, decides when a parked run processes. Deferring the auto-scheduler is
  acceptable for the demo and keeps the execution surface free of a background process to reason
  about.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Build the time-based auto-release scheduler now | A background timer/cron adds a live process with restart/timezone/missed-window semantics to get right — out of scope for the MVP. Manual release delivers the operator-gating value; the scheduler is a clean follow-up seam. |
| Let intake accept a raw posted graph to run | Breaks the approval gate (ADR-0014). Intake resolves an approved *name* only, same as Builder-Run. |
| A separate "staging" endpoint distinct from `POST /api/runs` | Duplicates registration/dedup/driver-launch logic. A `mode` field on the existing submit keeps one execution boundary. |
| Block a fresh resubmit whenever ANY persisted non-terminal job shares the run id | Would strand a run id on a stale `queued`/`running` job left by a dead process — `_reconcile` already resolves those to complete/lost. The dedup check is scoped to **parked** jobs only. |

## Consequences

| | |
|---|---|
| **Gains** | Sample processing can run an operator-authored approved pipeline (parity with Builder-Run, one shared gate). An operator can stage or schedule a run instead of a sequencer force-processing it. Driver params are durable, so a manual release survives a restart and fires identically. |
| **Costs** | Two new non-terminal states (`held`, `scheduled`) that reconcile must special-case. `scheduled` is honest-but-inert (no auto-fire) until the scheduler seam is built — a UI must label it as operator-released, not auto-released. A new release endpoint to wire. |
| **Follow-ups** | The time-based auto-release scheduler (a background process that releases a `scheduled` run at `scheduled_at`). Multi-worker job-store locking (shared with ADR-0016). Per-sample fan-out of a non-germline authored pipeline against real reads (only HG002 has reads on disk today). |

## Revisit when

- A deployment needs unattended scheduled processing (build the auto-release scheduler).
- The execution path moves to multi-worker/multi-node (harden the job-store dedup + reconcile).
- Intake needs operator-selected inputs per authored pipeline (today it uses the driver's committed
  HG002 defaults; the Builder-Run path already selects I/O by catalog key).
