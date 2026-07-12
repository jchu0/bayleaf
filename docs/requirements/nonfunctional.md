# Non-Functional Requirements

| Field | Value |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-07-12 (MST) |
| **Audience** | software / all |
| **Related** | [functional.md](functional.md), [constraints.md](constraints.md), [quality/evaluation.md](../quality/evaluation.md), [quality/risks.md](../quality/risks.md), [HISTORY.md](../HISTORY.md) (archived wave/batch narrative), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md), [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md), [ADR-0011](../adr/ADR-0011-tooling-and-reproducibility.md), [ADR-0016](../adr/ADR-0016-postgres-port.md), [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md), [ADR-0018](../adr/ADR-0018-variant-interpretation-advisory-evidence.md), [ADR-0020](../adr/ADR-0020-operator-authored-custom-processes.md), [ADR-0021](../adr/ADR-0021-operator-gated-scheduled-pipeline-processing.md), [design/frontend/README.md](../design/frontend/README.md), [journal 2026-07-10 wave9](../journal/2026-07-10-frontend-wave9.md), [journal 2026-07-10 wave10](../journal/2026-07-10-wave10-node-author-uic.md), [journal 2026-07-11](../journal/2026-07-11-d2-d3-share-egress.md), [journal 2026-07-11 nextflow](../journal/2026-07-11-nextflow-codegen-execution.md), [journal 2026-07-11 P3 backlog](../journal/2026-07-11-p3-backlog.md), [journal 2026-07-11 fleet](../journal/2026-07-11-fleet.md), [journal 2026-07-11 custom-script-io](../journal/2026-07-11-custom-script-io.md), [journal 2026-07-12 builder-agent-hardening](../journal/2026-07-12-builder-agent-hardening.md), [design/ui-conventions.md](../design/ui-conventions.md), [design/nextflow-codegen.md](../design/nextflow-codegen.md) |

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
5. **REQ-NF-005 — Per-run resolved-version capture (provenance, not a re-pin).** Every driver
   run (`scripts/run_giab_pipeline.py`) writes `versions.txt` into the run dir — a best-effort
   snapshot of the resolved Nextflow/fastp/bwa-mem2/samtools/mosdepth/bcftools/multiqc versions
   actually on `PATH` at run time. This does **NOT** pin or change any container/conda tag (the
   module catalog stays floating tags + a version floor, deliberately, to keep re-pinning out of
   scope — a Medium-risk change per the audit); "deterministic reruns" for this project mean
   wiring + gate re-derivation (REQ-NF-001), not bitwise-identical tool output. A version-probe
   failure is recorded, never fatal. *Trace:* [functional.md REQ-F-093](functional.md),
   [design/nextflow-codegen.md](../design/nextflow-codegen.md),
   [tasks T-131](../planning/tasks.md), [journal 2026-07-11 P3 backlog](../journal/2026-07-11-p3-backlog.md).

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
   deployments route through de-id. **Two de-id modules exist today, at different
   conservatism levels:** `api/deid.py` (salted-hash pseudonymization, wired into
   `GET /api/export`) and, as of 2026-07-10, `api/safe_harbor.py` — a more conservative
   Safe-Harbor-**style** scrub (direct-identifier drop, date→year generalization, age
   capping, mechanical free-text redaction of the §164.514(b)(2) classes; ADR-0018 D3, the
   maintainer's most-conservative choice). Neither makes a certified/attested compliance
   claim — both are explicitly labelled **not** HIPAA-compliant de-identification (no
   Expert Determination, no audit, no BAA/DUA). **`safe_harbor.py` is now wired to a real egress
   (2026-07-11):** an approver-gated `POST /api/runs/{id}/share` (ADR-0018
   [Realized](../adr/ADR-0018-variant-interpretation-advisory-evidence.md#realized-2026-07-11))
   runs it as the default (and only) policy and records the egress as an audited `DATA_EXPORTED`
   provenance event. This is **narrower** than the full report/share surface ADR-0018 §5–6
   describes — one fixed action, no scope/location/security-level selection — so this requirement
   is satisfied for that one narrower egress path, while the fuller Share window remains
   unbuilt. **A third, frontend-only instance of the same pattern landed 2026-07-10
   (Wave 9, T-117, REQ-F-082):** the new Sample-accessioning screen (`/accession`) composes
   subject id / tissue / collection metadata entirely **client-side** — no `api` call exists in
   `screens/Accession.tsx` or `lib/accession.ts`, and `POST /api/runs`'s `SubmitRunIn`/`SampleIn`
   (`api/routers/intake.py`) reject an unknown field via `extra="forbid"`, so there is currently no
   wire path for this data to reach the server even accidentally. DOB/MRN are deliberately not
   modeled as fields at all (PHI). This reinforces, rather than satisfies, this requirement: real
   subject/PII persistence for accessioned data remains gated on the same not-yet-built
   de-identification precondition. *Trace:* [scope-and-wishlist.md](scope-and-wishlist.md) #14,
   [schemas.md](../data/schemas.md) §Sample,
   [ADR-0018](../adr/ADR-0018-variant-interpretation-advisory-evidence.md) D3,
   [quality/evaluation.md](../quality/evaluation.md) EVAL-050,
   [functional.md REQ-F-082](functional.md).
5. **REQ-NF-024 — A frontend page-access view-gate is not server-side authorization.** As of
   2026-07-10 (Wave 9, T-117, REQ-F-082), `frontend/src/access.ts` + `context/AccessContext.tsx`
   let Admin assign each user a bundle of page-access profiles that filter which screens their nav
   shows (`canSee(page)`), mirroring the pre-existing `isAdmin` capability. **This gates client-side
   navigation only** — verified against the actual guard: `api/auth.py`'s `Role`/`Actor`/
   `require_role` primitive (ADR-0017) is unmodified by the change, remains the sole real
   authorization boundary, and continues to check every off-gate write server-side regardless of
   what the frontend nav shows. The editor UI itself states this in a persistent banner ("gates
   VIEWS, not API enforcement"). A production deployment would need a server-side page/read-access
   check to close this gap — not yet built, a labelled seam. *Trace:*
   [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md),
   [design/frontend/README.md](../design/frontend/README.md) §11,
   [functional.md REQ-F-082](functional.md),
   [journal 2026-07-10 wave9](../journal/2026-07-10-frontend-wave9.md).
6. **REQ-NF-025 — Sample-identity join requires explicit human approval before submit.** Because a
   sample identity mixup is the highest-consequence error in the intake path, Submit's
   `sample_metadata.csv` is **required, not optional** (2026-07-10, "Wave 10," UIC-11, commit
   `6b571a4`): the samplesheet's identity is corroborated against it on `Sample_ID` **plus at least
   one more column** (never a single-column match, to resist a 1-index-off mixup — verified in
   `lib/accession.ts`'s `computeIdentityJoin()`), and `Submit.tsx`'s `canSubmit` is `false` until a
   human explicitly approves the join. Approval is bound to a **signature** over the join result, so
   any edit afterward (re-attaching a different metadata sheet, adding/removing a sample row)
   silently invalidates a prior approval and forces re-confirmation — an operator cannot carry a
   stale "approved" state across an edited join. Every join action is appended to a client-side
   audit log (`SubmitAuditEntry`). **Scope**: this is a UI-level data-safety gate over client-parsed
   files; it does not yet extend server-side (`POST /api/runs` still carries no subject field,
   REQ-NF-023) and is not a cryptographic/formal identity-matching guarantee. *Trace:*
   [functional.md REQ-F-083c](functional.md), [design/ui-conventions.md UIC-11](../design/ui-conventions.md#uic-11--submit-samplesheet),
   [journal 2026-07-10 wave10](../journal/2026-07-10-wave10-node-author-uic.md).
7. **REQ-NF-026 — Dev-shim auth is loudly labelled; de-id/redaction matching is case-insensitive;
   the untrusted-text boundary is bounded (2026-07-11, audit P3-11 / AS-03/AS-05/AS-07/AS-08).**
   Four related agent-safety hardenings, none changing a default behavior: (a) `api/auth.py`'s
   `current_actor()` logs a single loud warning on first use that the header-trust dev shim is
   active (any caller can self-assert any role via `X-PipeGuard-Role`) — logged, never raised, so
   it cannot break the offline demo; a new opt-in `PIPEGUARD_AUTH_STRICT` (OFF by default) defaults
   a **header-less** request to `viewer` instead of the permissive `approver` — the header itself is
   still trusted either way, only the no-header fallback changes, and the demo's default behavior
   is byte-for-byte unchanged. (b) `api/deid.py`/`api/safe_harbor.py` field-name matching is now
   **case-insensitive** (trim + lower-case the lookup key) — a differently-cased column (`Tissue`)
   used to silently fall through to `PASSTHROUGH` and egress un-redacted; it now resolves its
   policy action like its lower-case form. (c) `synthesis/claude.py`'s system prompt now states
   explicitly that `log_excerpts`/`finding.detail` are UNTRUSTED pipeline/rule-authored text, never
   an instruction to follow, and caps what reaches the model (8 excerpts × 300 chars) — defense in
   depth on top of the structural guarantee that the verdict is computed and fixed BEFORE the model
   call (ADR-0001; the model can at worst mislead the labelled-advisory prose, never re-decide a
   sample). (d) `safe_harbor.py`'s 18 §164.514(b)(2)-class manifest gains a note that the class list
   is "classes the scrub *considers*," not "18 actively-running detectors" — several (vehicle,
   device, biometric, photo) are documented no-detector seams because the class does not appear in
   this data model; the egress endpoint's disclaimer already states the scrub is uncertified. *Trace:*
   REQ-NF-020, REQ-NF-023, [architecture.md](../design/architecture.md) §Swappable seams (Auth /
   identity row), [tasks T-131](../planning/tasks.md),
   [journal 2026-07-11 P3 backlog](../journal/2026-07-11-p3-backlog.md).
8. **REQ-NF-027 — The server-side file browser is allowlisted and traversal-hardened (`GET
   /api/files`, 2026-07-11, branch `feat/custom-script-io`, ADR-0020).** `api/routers/files.py`
   lists directory metadata for the Builder's "Browse…" data picker (REQ-F-099) with two hard
   boundaries, both pinned by `tests/test_files_api.py`: (a) **allowlist, not free filesystem
   access** — `root` is a *key* into a small configured map (`PIPEGUARD_BROWSE_ROOTS`, default
   `{"data": <repo>/data}`), never a raw path, so a caller can only ever browse a root an operator
   deliberately exposed; an unknown key is a 404. (b) **traversal-hardening**, mirroring the
   pre-existing artifact-download idiom in `api/main.py`: a `..` path component or a leading `/`
   (absolute path) is rejected **before** the filesystem is touched (400); the requested
   `root/path` is then `resolve()`-d and asserted to remain inside the resolved root — a symlink
   *inside* the root that points *outside* it (a case the pre-checks cannot see, since the path
   spelling itself is clean) is caught only at this resolve-and-assert step and rejected (403).
   Every rejection path is asserted to **provably never leak** the out-of-root content (the test
   suite plants a sentinel file outside the sandboxed root and asserts it never appears in any
   response body, including the 400/403 error detail). The endpoint returns metadata only
   (name/size/an extension-inferred kind) — it never reads or serves file bytes, never runs a
   tool, and never touches a verdict/finding/confidence (ADR-0001/0003). Auth is the lowest role
   (`viewer` and above) — allowlisted browsing is read-only, but not anonymous. *Trace:*
   [functional.md REQ-F-099](functional.md), [ADR-0020](../adr/ADR-0020-operator-authored-custom-processes.md),
   [journal 2026-07-11 custom-script-io](../journal/2026-07-11-custom-script-io.md).
9. **REQ-NF-028 — An agent's node-log observation grant is de-identified before it leaves the
   machine (2026-07-12, T-142).** The scoped node-observation read (REQ-F-101,
   `GET /api/runs/{id}/nodes/{node}/observations`) treats a tool's `.command.log`/`.command.err`
   as free text that can carry PII (a tool can echo a subject id into a path or a log line), so the
   opt-in `grants=logs` tail is routed through `api/deid.py`'s new `scrub_text()` **before** it is
   returned — NEVER the raw stream. Two conservative transforms, pinned by
   `tests/test_node_observations.py::test_logs_opt_in_and_deidentified`: (a) every KNOWN sensitive
   literal (the run's subject ids read from `sample_metadata.csv`, longest-first so a substring
   can't pre-empt a longer id) is replaced with a salted, non-reversible pseudonym; (b) generic
   email and 6+-digit runs (MRN/DOB/accession shape — a 6-digit floor keeps small metric integers
   readable) are redacted with a fixed marker. The test plants a subject id, an email, and an
   MRN-shaped number and asserts all three are absent from the returned tail while non-sensitive
   content survives (targeted, not a blackout). This is the **same honesty posture** as the other
   two scrubs (REQ-NF-023) — a demo heuristic explicitly labelled **NOT** HIPAA de-identification
   and **not** a validated NLP PHI scrubber (which stays documented-only). It is an egress text
   transform only: it never reads, sets, or overrides a verdict/finding/confidence (ADR-0001), and
   `logs` is off by default (least-privilege, ADR-0012). *Trace:* REQ-NF-023,
   [functional.md REQ-F-101](functional.md),
   [ADR-0022](../adr/ADR-0022-agent-observation-binding.md),
   [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md),
   [quality/evaluation.md EVAL-052](../quality/evaluation.md),
   [journal 2026-07-12](../journal/2026-07-12-builder-agent-hardening.md).

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
4. **REQ-NF-043 — Execution jobs survive a backend restart (2026-07-11, T-131, audit P3-2/P3-8).**
   `api/job_store.py` persists each background execution job (intake, Builder-run) so a backend
   restart cannot strand a poller on `running` forever — a restart-recovered job resolves to
   `complete` (result dir on disk) or the new terminal status `lost` (owning process gone, no
   result). Run-id reservation is atomic (the run-dir-exists check and the in-flight-job-set check
   happen under one lock), closing a race where two concurrent submits of the same run id could
   both proceed. *Trace:* [functional.md REQ-F-091](functional.md),
   [ADR-0016](../adr/ADR-0016-postgres-port.md) item 8,
   [journal 2026-07-11 P3 backlog](../journal/2026-07-11-p3-backlog.md).
5. **REQ-NF-044 — External-pipeline preflight fails loud, before launch (2026-07-11, T-131, audit
   P3-3/P3-4/P3-5/P3-7).** `scripts/run_giab_pipeline.py` validates FASTQ pairing/format,
   reference↔panel-BED contig naming, and reference-index sidecar presence BEFORE handing off to
   Nextflow — a bad input fails in milliseconds with an actionable message rather than burning a
   full launch or (worse) silently yielding a wrong result (e.g. a `20`/`chr20` naming mismatch
   would otherwise silently yield ~0% panel breadth). The shared driver-launch path
   (`api/job_store.run_driver()`) also now reaps the WHOLE process group on a timeout
   (`os.killpg`, `start_new_session=True`), not just the direct child, so a timed-out run leaves no
   orphaned Nextflow/JVM/tool subtree — both routers now share one `DRIVER_TIMEOUT_S` (was 900s
   intake / 1800s Builder-run, diverged). *Trace:* [functional.md REQ-F-092](functional.md),
   [design/nextflow-codegen.md](../design/nextflow-codegen.md),
   [journal 2026-07-11 P3 backlog](../journal/2026-07-11-p3-backlog.md).
6. **REQ-NF-045 — Multi-sample publish-dir parse fails loud, never fabricates a sample
   (2026-07-11, W4 continuation).** `scripts/run_giab_pipeline.py`'s `discover_samples`/
   `parse_publish_dir` treat a partial per-sample output set (a sample missing one of its four
   required published files) and an empty publish dir as hard `sys.exit` errors, naming the
   sample and the missing pattern — never a silently-dropped sample, never a fabricated metric.
   Sample-id matching is dot-prefix-anchored + `glob.escape`d so a shared-prefix pair (`S1`/`S10`)
   can never cross-capture another sample's files. Offline-verified against fixture publish dirs
   (`tests/test_run_giab_multisample.py`, 7 cases); the live multi-sample Nextflow run this guard
   would protect has not itself been exercised (see [functional.md REQ-F-095](functional.md)).
   *Trace:* [design/nextflow-codegen.md §Multi-sample driver
   parse](../design/nextflow-codegen.md#multi-sample-driver-parse-2026-07-11-w4-continuation),
   REQ-NF-041, [tasks T-134](../planning/tasks.md),
   [journal 2026-07-11](../journal/2026-07-11-w-deferrals.md).
7. **REQ-NF-046 — The Nextflow compiler is hostile-input-robust: compile correctly or fail loud,
   never silently wrong (2026-07-12, T-140, commit `37e54a8`).** Six verified robustness fixes turn
   off-golden-path/hostile graphs that used to emit a silently-wrong or unparseable bundle into ones
   that either compile correctly or raise a `CompileError`: (a) two distinct tools sharing a process
   name are rejected, not merged; (b) a `File input` source of a data kind wires to the right
   channel and a novel-kind source becomes a params channel (was a zero-input dangling process);
   (c) fan-in / duplicate-emit / port-drift guards catch a graph whose edges no longer match a
   node's declared ports; (d) operator-supplied strings (labels, `script:` bodies, ADR-0020) are
   injection-escaped so a quote/`$`/backtick cannot break out of the generated Groovy. The germline
   byte-for-byte drift guard + the custom-script tests stay green — these fixes touch only hostile
   inputs. Pure text codegen (compose ≠ execute — no tool runs). 17 cases
   (`tests/test_nextflow_robustness.py`, one per fix). *Trace:*
   [design/nextflow-codegen.md](../design/nextflow-codegen.md),
   [ADR-0020](../adr/ADR-0020-operator-authored-custom-processes.md),
   [quality/evaluation.md EVAL-017](../quality/evaluation.md), [tasks T-140](../planning/tasks.md).

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
5. **REQ-NF-054 — The frontend type-check actually runs on push (2026-07-12, T-143).** A
   `frontend-tsc` **pre-push** hook (`.pre-commit-config.yaml`) runs `tsc -b` in `frontend/`, at the
   same heavy-check-on-push cadence as the pytest hook. This closes a real no-op gap: the root
   `tsconfig` is references-only, so the earlier `tsc --noEmit` invocation type-checked nothing and
   a type error reached `main` uncaught; `tsc -b` builds the project references and fails the push
   on any type error. Mirrors the backend `mypy`/`ruff` gate (REQ-NF-051) for the TypeScript side.
   *Trace:* REQ-NF-051, [ADR-0011](../adr/ADR-0011-tooling-and-reproducibility.md),
   [journal 2026-07-12](../journal/2026-07-12-builder-agent-hardening.md).

## Portability

1. **REQ-NF-060 — Deployment-agnostic seams.** Persistence (Repository port),
   synthesis, and triage are swappable; SQLite→Postgres and local→Slurm/cloud paths
   are open via ports & adapters and Nextflow for compute. **Update (2026-07-11):** the Nextflow
   half of this is no longer only "open via" — it is **built and live-verified**: a card-graph →
   Nextflow compiler (`src/pipeguard/nextflow/`) plus a Nextflow-first intake driver
   (`scripts/run_giab_pipeline.py`) run the real germline chain locally via `nextflow run
   -profile conda` end to end. **Update (2026-07-11, W4):** an executor-profile layer now
   exists — the generated `nextflow.config` also declares `standard` (local single-thread-serial,
   the demo default) and `slurm` (env-driven `PIPEGUARD_SLURM_QUEUE`/`_CLUSTER_OPTIONS`/
   `_QUEUE_SIZE`, one sbatch job per process instance), with `run_giab_pipeline.py` auto-detecting
   `sbatch` on `PATH` to pick between them. **Honest scope: CONFIG-verified, not
   CLUSTER-verified** — no `sbatch` exists in this sandbox, so only the local-serial branch has
   actually executed; the Slurm profile has never run against a real cluster, and AWS-Batch/
   HealthOmics executor config is fully unbuilt. What remains open is now narrower still: a
   *cluster-verified* Slurm run and the two cloud executors — not "is a non-local profile even
   declared." *Trace:*
   [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md) (Realized 2026-07-11, incl. the W4
   addendum), [design/nextflow-codegen.md](../design/nextflow-codegen.md),
   [architecture.md](../design/architecture.md) §Deployment. Cloud/IaC executor config is still
   *wishlist*.

## Accessibility

1. **REQ-NF-070 — Baseline screen-reader + keyboard-trap support on shared components
   (2026-07-11, T-132, audit S1/UIUX-05/UIUX-08).** Two shared primitives every screen composes
   through gain a baseline a11y contract: `components/Toast.tsx`'s container carries
   `role="status" aria-live="polite"`, with an individual error toast additionally carrying
   `role="alert"` (assertive) so a failure interrupts a screen reader rather than waiting for a
   pause; `components/ConfirmDialog.tsx`'s panel carries `role="dialog" aria-modal="true"` +
   `aria-labelledby`/`aria-describedby`, focuses its primary (confirm) button on open, and traps
   Tab within the panel (wraps first↔last focusable) so keyboard/AT users cannot tab out to the
   page behind the overlay. **Scope**: this is a baseline for these two shared components, not a
   full WCAG audit of the app — no automated a11y test/CI gate exists yet, and this requirement
   does not claim AA/AAA conformance anywhere else in the UI. *Trace:*
   [design/ui-conventions.md](../design/ui-conventions.md) UIC-19,
   [journal 2026-07-11 P3 backlog](../journal/2026-07-11-p3-backlog.md).
2. **Update (2026-07-11, T-136, REQ-F-097, commit `4427ec2`) — the baseline extends to the shared
   view-selector/pagination/toggle primitives + form labels.** `components/Tabs.tsx` gains
   roving-tabindex + Arrow/Home/End keyboard nav (tab roles already existed); `components/
   Pager.tsx`'s page-button row is now a `nav aria-label="Pagination"` landmark with
   `aria-current="page"` + a per-page `aria-label`; `components/SegmentedControl.tsx` gains
   `role="radiogroup"`/`role="radio"` + `aria-checked` + an optional accessible group `label`;
   `components/RunSelector.tsx` gains the ARIA combobox/listbox pattern (`role="combobox"`,
   `aria-expanded`/`aria-controls`/`aria-activedescendant`, ArrowUp/ArrowDown to move the
   highlighted option, Enter to pick it). `screens/Submit.tsx`/`Accession.tsx`/`Settings.tsx` form
   inputs gain `htmlFor`/`id` label↔input association, `aria-label` on grid-row inputs whose column
   headers are visual-only, and `aria-describedby` on hint text. **Verdict-token contrast was
   verified, not assumed**, to pass WCAG AA: all 8 fg/bg token pairings measure 5.5–9:1 contrast, so
   `index.css` (the Builder-shared theme) needed no change. This is still not a full WCAG audit —
   the scope caveat above holds; it narrows which components/screens the baseline covers, it does
   not newly claim app-wide AA conformance. *Trace:*
   [design/ui-conventions.md](../design/ui-conventions.md) UIC-19,
   [functional.md REQ-F-097](functional.md), [tasks T-136](../planning/tasks.md),
   [journal 2026-07-11 fleet](../journal/2026-07-11-fleet.md).

---

*Marker legend:* **Fact** · **Assumption** · **Decision** · **TODO**. Requirements
marked *(Assumption)* / *Flag* are not yet measured — see [risks.md](../quality/risks.md).
