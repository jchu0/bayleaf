# Non-Functional Requirements

| Field | Value |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | software / all |
| **Related** | [functional.md](functional.md), [constraints.md](constraints.md), [quality/evaluation.md](../quality/evaluation.md), [quality/risks.md](../quality/risks.md), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md), [ADR-0011](../adr/ADR-0011-tooling-and-reproducibility.md) |

## Overview

Quality attributes the system must hold (**REQ-NF-NNN**) — the *how well*, alongside
the *what* in [functional.md](functional.md). These are the properties that make a
clinical-adjacent provenance tool trustworthy: determinism, auditability, security,
and graceful degradation. Where a requirement is verified, the check is named and
links to [evaluation.md](../quality/evaluation.md).

## Determinism & reproducibility

1. **REQ-NF-001 — Deterministic verdicts.** For fixed inputs and a pinned runbook /
   rule pack, the gate produces identical verdicts, findings, and content hashes on
   every run. *Verify:* the pinned offline demo scenario is test-locked (S1–S3
   proceed / S4 escalate / S5 hold) — [evaluation.md](../quality/evaluation.md).
2. **REQ-NF-002 — Reproducible environment.** Dependencies resolve from a single
   pinned source (`pyproject.toml` + `uv.lock`); the demo environment is
   reproducible. *Trace:* [ADR-0011](../adr/ADR-0011-tooling-and-reproducibility.md).
3. **REQ-NF-003 — Rebuildable projection.** The relational DB is a pure function of
   the event ledger; `rebuild-db` replays deterministically and is idempotent (a
   second rebuild yields the same projection). Byte-identical strict replay is a
   Phase-2 hardening. *Trace:* [provenance.md](../data/provenance.md), ADR-0002.
4. **REQ-NF-004 — Unit-stable gating.** QC metrics are normalized to canonical decimals
   through the metric registry before thresholding, so a source's raw-unit change (or a
   MultiQC key rename absorbed by the registry/mapping) cannot move a verdict. Introducing
   the registry on the critical path (T-024/T-025) left the pinned demo verdicts
   **byte-identical**. *Verify:* the offline suite + pinned scenario stayed green across
   T-024/T-025 — [metric_registry.md](../data/metric_registry.md),
   [schemas.md](../data/schemas.md) §QC (units contract).

## Provenance & auditability

1. **REQ-NF-010 — Event log is authoritative.** Every meaningful I/O and decision is
   recorded as an append-only event; the log — not the DB — is the source of truth.
   *Trace:* [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md).
2. **REQ-NF-011 — Traceable to source.** Every finding/card traces to Evidence
   anchored to an artifact + field (+ content hash where applicable), so a reviewer
   can audit any number back to its file. *Trace:* [schemas.md](../data/schemas.md)
   invariants.
3. **REQ-NF-012 — Tamper-evident records.** Immutable records (findings, cards,
   artifacts) carry a sha256 content hash; mutation of state happens only on separate
   mutable entities (IssueSignature / Ticket / ExperienceRecord). *Trace:*
   [schemas.md](../data/schemas.md).
4. **REQ-NF-013 — Origin provenance preserved.** The `real-giab` / `synthetic` /
   `contrived` origin label is never lost as data flows through the ledger and
   schemas. *Trace:* [strategy.md](../data/strategy.md).

## Security & privacy

1. **REQ-NF-020 — Secrets via env only.** No keys, tokens, credentials, or private
   URLs are hardcoded; the live-AI path reads its key from the environment. The live
   Slack notify path likewise reads its bot token + channel from env
   (`PIPEGUARD_SLACK_BOT_TOKEN` / `PIPEGUARD_SLACK_CHANNEL`) and stays disarmed unless
   `PIPEGUARD_SLACK_LIVE=1`, so a stray token cannot post. New required env vars are added
   to `.env.example`. *Trace:* CLAUDE.md Security, [architecture.md](../design/architecture.md)
   §Outbound notify seam.
2. **REQ-NF-021 — No PHI in the repo.** No raw reads, PHI, or large artifacts are
   committed; accessions + a fetch script are committed instead. The demo uses
   public/synthetic/contrived data only. *Trace:* CLAUDE.md Data handling,
   [strategy.md](../data/strategy.md), [scope-and-wishlist.md](scope-and-wishlist.md).
3. **REQ-NF-022 — No secrets in output.** Secrets never appear in logs, test output,
   or errors; a pre-commit secret scan guards against leakage. *Trace:* CLAUDE.md
   Security, [ADR-0011](../adr/ADR-0011-tooling-and-reproducibility.md).
4. **REQ-NF-023 — De-identification is a precondition for real PHI.** Any future
   real-patient integration is gated on a configurable de-identification module
   *(wishlist #14)*; note that `subject_key` is not PHI-free by construction and real
   deployments route through de-id. *Trace:* [scope-and-wishlist.md](scope-and-wishlist.md),
   [schemas.md](../data/schemas.md) §Sample.

## Performance & cost

1. **REQ-NF-030 — Offline, $0 by default.** With AI off (the default), the core,
   tests, and demo run offline at no API cost. *Trace:* [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md).
2. **REQ-NF-031 — Bounded live-AI cost.** Live AI is opt-in and model-selectable so
   cost/quality is tunable within a fixed API budget. *Trace:* ADR-0006,
   [constraints.md](constraints.md).
3. **REQ-NF-032 — Demo-scale responsiveness.** *(Assumption)* The gate runs a mock
   run end-to-end fast enough for an interactive demo; no throughput/latency SLA is
   claimed at this stage. *Flag:* no benchmark measured — see
   [risks.md](../quality/risks.md).

## Reliability & degradation

1. **REQ-NF-040 — AI failure degrades gracefully.** Disabled, errored, or
   safety-refused AI calls fall back to the deterministic stub; the demo cannot break
   on the AI path. *Trace:* [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md),
   [demo_plan.md](../demo/demo_plan.md).
2. **REQ-NF-041 — Tolerant parsing at boundaries.** Parsers treat a missing field as
   a *signal*, not a crash; malformed/partial artifacts are handled without aborting
   the run. *Trace:* CLAUDE.md Data handling, [architecture.md](../design/architecture.md).
3. **REQ-NF-042 — Layered demo fallback.** Live AI → stub; React/API → Streamlit;
   else recorded walkthrough. *Trace:* [demo_plan.md](../demo/demo_plan.md) §Fallbacks.

## Maintainability, type-safety & testing

1. **REQ-NF-050 — Framework-agnostic core.** `src/pipeguard/` imports no
   Streamlit/FastAPI/React; delivery layers depend on the core, not vice versa.
   *Trace:* [architecture.md](../design/architecture.md) invariants, ADR-0003.
2. **REQ-NF-051 — Strict typing.** Type hints across the board, enforced by strict
   mypy; ruff lints/formats. *Trace:* [ADR-0011](../adr/ADR-0011-tooling-and-reproducibility.md),
   `pyproject.toml`.
3. **REQ-NF-052 — Offline test suite stays green.** Changes to parsers or rules must
   keep the offline suite green and the pinned demo intact; tests run without an API
   key. *Trace:* CLAUDE.md Testing, [evaluation.md](../quality/evaluation.md).
4. **REQ-NF-053 — Docs move with code.** Behavior changes update the relevant docs in
   the same change (dated ISO-8601 MST); a doc-drift habit, not a gate. *Trace:*
   [DOCUMENTATION_HABITS.md](../DOCUMENTATION_HABITS.md).

## Portability

1. **REQ-NF-060 — Deployment-agnostic seams.** Persistence (Repository port),
   synthesis, and triage are swappable; SQLite→Postgres and local→Slurm/cloud paths
   are open via ports & adapters and Nextflow for compute. *Trace:* [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md),
   [architecture.md](../design/architecture.md) §Deployment. Cloud/IaC is *wishlist*.

---

*Marker legend:* **Fact** · **Assumption** · **Decision** · **TODO**. Requirements
marked *(Assumption)* / *Flag* are not yet measured — see [risks.md](../quality/risks.md).
