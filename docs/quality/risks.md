# Risks

| Field | Value |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-07-11 (MST) |
| **Audience** | all |
| **Related** | [evaluation.md](evaluation.md), [requirements/constraints.md](../requirements/constraints.md), [data/strategy.md](../data/strategy.md), [data/schemas.md](../data/schemas.md), [data/metric_registry.md](../data/metric_registry.md), [demo/demo_plan.md](../demo/demo_plan.md), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md), [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md), [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md), [ADR-0016](../adr/ADR-0016-postgres-port.md), [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md), [journal/2026-07-09-frontend-batch3.md](../journal/2026-07-09-frontend-batch3.md), [journal/2026-07-10-provenance-qc-builder-auth.md](../journal/2026-07-10-provenance-qc-builder-auth.md), [journal/2026-07-10-batch5-builder-card-admin-prefs.md](../journal/2026-07-10-batch5-builder-card-admin-prefs.md), [journal/2026-07-10-confirm-dialog-audit-gate.md](../journal/2026-07-10-confirm-dialog-audit-gate.md), [journal/2026-07-10-frontend-wave9.md](../journal/2026-07-10-frontend-wave9.md), [journal/2026-07-11-p3-backlog.md](../journal/2026-07-11-p3-backlog.md) |

## Overview

What could go wrong, ranked by exposure, with the concrete mitigation already in place
(or the trigger that would make us act). Each entry is `RISK-NNN` with category,
likelihood, and impact. This is a living list; the highest-value ones are the **demo**
and **domain-safety** risks, because they are the failure modes a judge or a downstream
clinician would actually feel.

## Technical

### RISK-001 — Parser normalization drift silently moves a verdict

| Field | Value |
|---|---|
| **Category** | Technical |
| **Likelihood** | Medium |
| **Impact** | High |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** MultiQC reports percentages (`pct_*`, ×100) while fastp reports fractions
(0–1). Mixing them shifts a borderline sample across a threshold with no error.

**Mitigation.** **Now mitigated by the units contract** ([schemas.md §6](../data/schemas.md)):
the canonical [metric registry](../data/metric_registry.md) is **on the QC critical path** —
rules compare each metric's `normalized_value` against a runbook threshold stored in the same
`canonical_unit`, and normalization keys on the *declared* `raw_unit` (never the field name),
so a `pct_*` percentage can't be silently read as a fraction. This is verified byte-identical
to the pre-registry path ([evaluation.md](evaluation.md) EVAL-005), with the registry's
normalize/denormalize round-trip (EVAL-004) and the pinned borderline S5 demo values (EVAL-001)
locking any residual drift to a test failure.

**Owner / revisit trigger.** Any new parser or metric source keying on an unregistered metric —
add the registry entry + re-pin a case.

### RISK-002 — Content-hash instability from non-canonical serialization

| Field | Value |
|---|---|
| **Category** | Technical |
| **Likelihood** | Low |
| **Impact** | High |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** If findings/cards were hashed over non-canonical JSON (key order, datetime
format), "immutable" hashes would churn and reproducibility (EVAL-002) would break.

**Mitigation.** `content_hash` hashes canonical JSON; `model_dump(mode="json")` is used
consistently. A real datetime-serialization bug here already caused a demo 500 and is now
regression-tested ([evaluation.md](evaluation.md) EVAL-021).

**Owner / revisit trigger.** Any change to a frozen model's fields or the hash input.

### RISK-003 — No measured performance envelope

| Field | Value |
|---|---|
| **Category** | Technical |
| **Likelihood** | Low |
| **Impact** | Low |
| **Status** | Accepted |
| **Added** | 2026-07-08 (MST) |

**Risk.** No throughput/latency benchmark exists; a large real run could be slower than
the interactive demo suggests.

**Mitigation.** Explicitly *not claimed* ([nonfunctional.md](../requirements/nonfunctional.md)
REQ-NF-032); demo is mock-scale. Accepted for the hackathon.

**Owner / revisit trigger.** First real-data run at panel/exome scale.

## Data

### RISK-010 — Committing PHI or raw reads

| Field | Value |
|---|---|
| **Category** | Data / Security |
| **Likelihood** | Low |
| **Impact** | High |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** Accidentally committing raw reads, PHI, or a large artifact into the repo.

**Mitigation.** Policy is accessions + fetch script, never raw reads
([strategy.md](../data/strategy.md), [nonfunctional.md](../requirements/nonfunctional.md)
REQ-NF-021); demo data is public/synthetic/contrived only; every artifact carries an
origin label (`real-giab` / `synthetic` / `contrived`).

**Owner / revisit trigger.** Adding the GIAB real-data track (T-013/T-017) — verify the
fetch-script pattern holds.

### RISK-011 — Synthetic data diverges from real artifact shapes

| Field | Value |
|---|---|
| **Category** | Data |
| **Likelihood** | Medium |
| **Impact** | Medium |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** The synthetic generator could emit a dialect the production parsers accept but
real instruments never produce, making green tests misleading.

**Mitigation.** Generated runs are asserted to parse with the *existing* parsers
([evaluation.md](evaluation.md) EVAL-010); field names mirror nf-core/sarek + MultiQC
conventions ([nf-core-conventions.md](../data/nf-core-conventions.md)). Real GIAB data is
the eventual cross-check (EVAL-030).

**Owner / revisit trigger.** First real-data comparison; any generator feature.

## Product / domain safety

### RISK-020 — Overclaiming clinical or diagnostic capability

| Field | Value |
|---|---|
| **Category** | Product |
| **Likelihood** | Medium |
| **Impact** | High |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** The tool is read as a clinical decision system, or a verdict/confidence is
taken as a diagnostic or pathogenicity claim.

**Mitigation.** Hard guardrails: no diagnostic/therapeutic/pathogenicity claims;
confidence omitted until grounded and labelled a heuristic; thresholds labelled
illustrative/per-assay; conservative language ([constraints.md](../requirements/constraints.md)
REQ-C-030..034). Rules decide, AI only advises (ADR-0001).

**Owner / revisit trigger.** Any UI/demo copy change; any move toward real deployment.

### RISK-021 — AI narration contradicts or appears to set the verdict

| Field | Value |
|---|---|
| **Category** | Product |
| **Likelihood** | Low |
| **Impact** | High |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** A viewer believes the LLM chose the verdict, eroding the core safety story;
or the model emits a number that looks authoritative.

**Mitigation.** The triage note type has no verdict/confidence field
([evaluation.md](evaluation.md) EVAL-020); the UI badges output `ADVISORY · STUB/CLAUDE`;
citations and addressed findings stay deterministic even on the claude path (EVAL-021).

**Owner / revisit trigger.** Any expansion of the agent's output schema.

## Demo

### RISK-030 — Live-AI path flaky or rate-limited mid-demo

| Field | Value |
|---|---|
| **Category** | Demo |
| **Likelihood** | Medium |
| **Impact** | Medium |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** The "flip AI on live" moment errors, times out, or is safety-refused in front
of judges.

**Mitigation.** Any error/refusal degrades to the stub — same structure, templated prose,
$0 ([demo_plan.md](../demo/demo_plan.md) §Fallbacks, EVAL-021). The default demo never
calls the API.

**Owner / revisit trigger.** Rehearsal; API status on demo day.

### RISK-031 — React/API stack fails on the demo machine

| Field | Value |
|---|---|
| **Category** | Demo |
| **Likelihood** | Low |
| **Impact** | Medium |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** Node/Vite/port issues (we already hit an :8000 Docker clash → moved to :8010)
break the React UI during setup.

**Mitigation.** The dev port is now **pinned** (`strictPort` on :5173, `frontend/vite.config.ts`) so
a port clash fails loudly at startup instead of silently drifting to :5174 — off the port the app's
CORS allowlist and `/metrics` swap assume. The full stack runs **offline** (stub-first, $0, no live
service to fail mid-demo). If the React UI still won't come up → recorded walkthrough/screenshots
([demo_plan.md](../demo/demo_plan.md) §Fallbacks; [nonfunctional.md](../requirements/nonfunctional.md)
REQ-NF-042).

**Owner / revisit trigger.** Dry run on the actual demo machine.

### RISK-032 — Budget exhaustion from accidental live-AI usage

| Field | Value |
|---|---|
| **Category** | Demo / Security |
| **Likelihood** | Low |
| **Impact** | Medium |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** Live Claude left on during dev burns the fixed **~$200** budget before the demo.

**Mitigation.** AI is off by default; every seam is stub-first and $0; live is opt-in per
env var and flipped on only for the demo moment ([constraints.md](../requirements/constraints.md)
REQ-C-010/011; MEMORY: conserve-API-credits).

**Owner / revisit trigger.** Any session that sets `BAYLEAF_*=claude`.

### RISK-033 — Live Slack post is a real outbound side effect

| Field | Value |
|---|---|
| **Category** | Demo / Security |
| **Likelihood** | Low |
| **Impact** | Medium |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** The notify port (ADR-0010) can post a decision card to a real Slack channel — data
leaving the machine. An accidental, mis-targeted, or premature send (wrong channel, dev noise,
sensitive content) during development or the demo.

**Mitigation.** Off by default: the `stub` adapter builds and records the payload but sends
nothing ($0, offline). A live post is armed **only** by explicit `BAYLEAF_SLACK_LIVE=1`
**and** `BAYLEAF_NOTIFIER=slack` **and** a bot token + channel read from env (never hardcoded;
`.env.example` documents them). The actionable-only policy means no all-clear spam; any missing
cred, missing Slack SDK, or Slack error degrades to the stub. EVAL-041 pins that it never sends
unless armed, and `notification.emitted` records the result and **no secret**
([evaluation.md](evaluation.md) EVAL-040/041; [demo_plan.md](../demo/demo_plan.md) §"wow"
moment 3). Demo content is synthetic/contrived, not PHI.

**Owner / revisit trigger.** Any session that sets `BAYLEAF_SLACK_LIVE`; demo rehearsal
against the live workspace; any move toward real (PHI-bearing) data.

### RISK-034 — Submit's execution boundary depends on an external toolchain on PATH

| Field | Value |
|---|---|
| **Category** | Demo / Technical |
| **Likelihood** | Medium |
| **Impact** | Medium |
| **Status** | Mitigating |
| **Added** | 2026-07-09 (MST) |

**Risk.** `POST /api/runs` ([`api/routers/intake.py`](../../api/routers/intake.py), T-057)
triggers `scripts/run_giab_pipeline.py` as a background subprocess that shells out to
`fastp`/`bwa-mem2`/`samtools`/`mosdepth`/`bcftools`. If the API process wasn't started with
`BAYLEAF_BIOCONDA_BIN` prepended to `PATH` (a plain `uv run uvicorn` doesn't have it), every
live Submit silently fails at the driver — the job flips to `failed` with a truncated stderr tail,
but a demo operator who didn't set the env var first would hit this **live**. It also takes
**~15s** end to end (fastp → bwa-mem2 → markdup → gate), a real timing risk if demoed live vs.
pre-seeded data. Scope is intentionally narrow: only `HG002` has real panel reads on disk (a
server-side fixture registry), so any other submitted sample is honestly reported *skipped*, not
silently dropped or fabricated.

**Mitigation.** `.env.example` documents `BAYLEAF_BIOCONDA_BIN`; the seeded demo data
(`scripts/seed_giab_demo.py`, ~24 runs) and the pinned `data/RUN-2026-07-08-GIAB-HG002/` fixture
(T-063) mean the demo does **not need** a live Submit to show every other screen — Submit can be
demoed once, pre-verified, or skipped in favor of the pre-seeded runs if the toolchain isn't
confirmed on the demo machine. `GET /api/runs/{id}/intake-status` surfaces `failed` + an error
tail rather than hanging silently. **Extended 2026-07-11 (T-131):** two related gaps this risk's
scope always implied are now closed — (1) a backend restart mid-run used to strand
`intake-status` on `running` forever (the old in-memory `_jobs` dict); the durable
`api/job_store.py` now recovers a restarted job to `complete` or the new `lost` status instead.
(2) A mismatched/swapped/malformed FASTQ pair, a reference/panel-BED contig-naming mismatch, or a
missing reference index used to fail deep inside Nextflow (or, worse for a contig mismatch,
silently yield ~0% coverage) rather than failing fast at the API boundary; four pre-flight guards
now `sys.exit` before the Nextflow launch with an actionable message. Neither closes the
underlying toolchain-on-PATH dependency this risk is about — they harden the failure/recovery
paths around it. See [ADR-0016](../adr/ADR-0016-postgres-port.md) item 8,
[nextflow-codegen.md §Pre-flight guards](../design/nextflow-codegen.md#pre-flight-guards--version-capture-2026-07-11-t-131).

**Owner / revisit trigger.** Demo rehearsal on the actual demo machine with a live Submit;
confirm `BAYLEAF_BIOCONDA_BIN` is set in the API's launch env before any live Submit demo.

### RISK-035 — The demo login gate is client-side only and is not real access control

| Field | Value |
|---|---|
| **Category** | Demo / Security |
| **Likelihood** | Low |
| **Impact** | Medium |
| **Status** | Mitigating |
| **Added** | 2026-07-10 (MST) |

**Risk.** `frontend/src/auth.ts` (T-081) gates every route behind a login screen, but the check
is a **synchronous, client-side** credential compare against a hardcoded roster + a single shared
password (`bayleaf`), the "session" is `{id, role}` in `localStorage` with **no token**, and the
CAPTCHA on the login screen is a labelled placeholder that gates submit but verifies nothing. A
viewer could read the bundled JS, learn the roster/password, or edit `localStorage` directly to
mint any role — including `admin` — with no server round trip. **The backend is unaffected**:
`api/auth.py`'s header dev-shim (already RISK-adjacent, [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md))
is the actual (also non-production) authorization boundary, and it was not changed by this login
screen — the login only decides which `Actor` headers the frontend *sends*.

**Mitigation.** Explicitly labelled throughout as a **demo gate, not production auth** — every
production seam (OAuth/OIDC, server-side argon2/bcrypt password hashing, an httpOnly/Secure/
SameSite session cookie or JWT+refresh, a real CAPTCHA, signed reset links, TLS) is named inline
in `auth.ts`'s own comments and on the login screen's security-posture footer, per the maintainer's
explicit choice ("demo gate over wiring real auth" — [tasks T-081](../planning/tasks.md)). No PHI
or real patient data is ever in scope (demo data is `real-giab`/`synthetic`/`contrived` only,
[strategy.md](../data/strategy.md)), so a bypassed login exposes only the demo dataset, not
sensitive data. The generic "Incorrect email or password" message avoids a user-enumeration leak
at least at the UI layer.

**Owner / revisit trigger.** Any move toward a real multi-tenant deployment (swap `current_actor`
per ADR-0017's Follow-ups, then also replace `auth.ts` with a real OIDC/session flow before any
non-demo audience sees the app); any session that hardens `api/auth.py`.

**Related hardening (2026-07-10, T-092, commit `5774143`):** the Admin panel's "Users & roles"
tab (still the same client-mock roster this risk describes) now stages a role change into a
draft behind an explicit Save/Discard bar, and "Act as" confirms before impersonating — this
makes the **legitimate** UI path deliberate/auditable but does **not** change the underlying
posture above (a viewer can still bypass the UI entirely via `localStorage`).

**Related, distinct client-side gate (2026-07-10, Wave 9, T-117, commit `66b14e4`).** A second,
separate capability landed with the same shape and the same posture: a page-access **view-gate**
(`frontend/src/access.ts` + `context/AccessContext.tsx`) lets Admin assign a per-user bundle of
page-visibility profiles. Same exposure class as this risk (a viewer can edit `localStorage` to
grant themselves every page, or flip `enforce` off), but **narrower blast radius** — it only hides
nav items/routes client-side, and unlike the login gate it was never presented as any form of
access control: the editor UI carries its own persistent banner ("gates VIEWS, not API
enforcement") and `api/auth.py`'s `require_role` — the actual, unaffected authorization boundary
for every real write — is verified unchanged in the diff. Not tracked as a separate RISK-NNN
(same category/likelihood/impact/mitigation posture as this one, and it is explicitly labelled at
the point of use rather than a hidden gap) — see [functional.md
REQ-F-082](../requirements/functional.md) and [nonfunctional.md
REQ-NF-024](../requirements/nonfunctional.md).

**Further hardening (2026-07-10, T-102, commit `d65c9c1`):** Act-as's confirm now uses the same
reusable, branded `ConfirmDialog`/`useConfirm()` gate the review queue adopted (replacing the
native `window.confirm` T-092 shipped) — a UI-consistency/polish change only, still naming the
impersonation target + role before switching. Does not change the posture above: still the same
client-mock roster, still bypassable via `localStorage`, `api/auth.py` unchanged.

---

*Marker legend:* **Fact** · **Assumption** · **Decision** · **TODO**. Likelihood/impact
are judgement calls for this sprint, not measured probabilities.
